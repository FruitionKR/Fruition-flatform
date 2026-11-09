// 사용자 행동 단위. 각 함수는 실제 화면이 부르는 순서를 따른다.
import http from 'k6/http';
import { sleep } from 'k6';
import { Counter } from 'k6/metrics';
import { request, json, uuid, editContention } from './http.js';
import { token } from './auth.js';
import { accountForVu, LLM_SHARE, LLM_MAX_PER_VU, QUERY_PROVIDER, QUERY_MODEL, THINK_MIN_S, THINK_MAX_S } from './config.js';

export const llmQueries = new Counter('llm_queries');
const QUERY_POLL_INTERVAL_S = 2;
const QUERY_POLL_MAX = 30; // 최대 60초 대기
const QUERY_DONE = ['completed', 'failed', 'cancelled', 'canceled', 'error'];

let treeEtag = null;
let llmSent = 0;

export function think() {
  sleep(THINK_MIN_S + Math.random() * Math.max(THINK_MAX_S - THINK_MIN_S, 0));
}

/** 이 VU가 쓸 시드 데이터. setup() 반환값에서 계정별로 찾는다. */
export function myFixture(data) {
  const fixture = data.byEmail[accountForVu(__VU).email];
  if (!fixture || !fixture.workspaceId) throw new Error('시드 데이터가 없습니다. setup 로그를 확인하세요.');
  return fixture;
}

function pick(list) {
  return list[Math.floor(Math.random() * list.length)];
}

/** 70%: 탐색 트리 폴링(ETag/304)과 가끔 워크스페이스 목록. */
export function browseTree(fx) {
  const t = token();
  if (Math.random() < 0.2) request('GET', '/api/workspaces', { ep: 'workspaces', token: t });
  const headers = treeEtag ? { 'If-None-Match': treeEtag } : {};
  const res = request('GET', `/api/workspaces/${fx.workspaceId}/document-tree`, {
    ep: 'tree', token: t, headers, expect: [200, 304],
  });
  if (res.status === 200 && res.headers.Etag) treeEtag = res.headers.Etag;
  if (fx.folderId && Math.random() < 0.3) {
    request('GET', `/api/workspaces/${fx.workspaceId}/folders/${fx.folderId}/children`, { ep: 'tree', token: t });
  }
}

/** 20%: 문서 열기 → 편집 잠금 → 본문 저장 → 잠금 해제. 저장은 Kafka edit event만 내고 LLM은 부르지 않는다. */
export function openAndSave(fx) {
  if (fx.docIds.length === 0) return;
  const t = token();
  const docId = pick(fx.docIds);
  const base = `/api/workspaces/${fx.workspaceId}/documents/${docId}`;
  const detail = json(request('GET', base, { ep: 'doc_read', token: t }), {});
  if (typeof detail.markdown !== 'string') return;

  const lock = request('POST', `${base}/edit-lock`, { ep: 'doc_lock', token: t, expect: [200, 423] });
  if (lock.status === 423) {
    editContention.add(1, { kind: 'lock' });
    return;
  }
  think();
  const revision = detail.edit_revision !== undefined ? detail.edit_revision : detail.current_version;
  const markdown = `${detail.markdown.slice(0, 20000)}\n- k6 ${__VU}-${__ITER} ${Date.now()}\n`;
  const save = request('PUT', `${base}/content`, {
    ep: 'doc_save', token: t, expect: [200, 409], multipart: true,
    body: {
      markdown: http.file(markdown, 'content.md', 'text/plain;charset=UTF-8'),
      base_revision: String(revision),
      revision_write_id: uuid(),
    },
  });
  if (save.status === 409) editContention.add(1, { kind: 'save' });
  request('DELETE', `${base}/edit-lock`, { ep: 'doc_lock', token: t, expect: [200, 204] });
}

/** 5%: 대용량 PDF 직접 업로드 티켓만 발급하고 바로 중단한다. S3에 조각을 올리지 않는다. */
export function uploadTicketOnly(fx) {
  const t = token();
  const start = json(request('POST', `/api/workspaces/${fx.workspaceId}/documents/uploads`, {
    ep: 'upload_ticket', token: t,
    body: { filename: `k6-${__VU}-${__ITER}.pdf`, size: 1048576, folder_id: fx.folderId || undefined },
  }), {});
  if (!start.ticket) return;
  request('POST', `/api/workspaces/${fx.workspaceId}/documents/uploads/abort`, {
    ep: 'upload_ticket', name: 'POST upload abort', token: t, expect: [204], body: { ticket: start.ticket },
  });
}

/** 5%: 채팅. LLM_SHARE 확률(그리고 VU당 상한 이내)일 때만 실제 질의를 보내고, 아니면 채팅 기록 조회만 한다. */
export function chat(fx) {
  const t = token();
  const sessionPath = `/api/workspaces/${fx.workspaceId}/chat/sessions`;
  request('GET', sessionPath, { ep: 'chat_read', token: t });
  if (!fx.chatSessionId) return;
  request('GET', `${sessionPath}/${fx.chatSessionId}/messages`, { ep: 'chat_read', token: t });
  if (!(llmSent < LLM_MAX_PER_VU && Math.random() < LLM_SHARE)) return;

  llmSent += 1;
  llmQueries.add(1);
  const body = { question: '이 워크스페이스의 문서를 한 문장으로 요약해 주세요.', allow_web_search: false };
  if (QUERY_PROVIDER) body.provider = QUERY_PROVIDER;
  if (QUERY_MODEL) body.model = QUERY_MODEL;
  const run = json(request('POST', `${sessionPath}/${fx.chatSessionId}/query/runs`, {
    ep: 'query_start', token: t, expect: [202], body,
  }), {});
  if (!run.request_id) return;
  // 화면은 SSE(/events)를 구독하지만, 부하 시험은 같은 상태를 조회 API 폴링으로 확인한다.
  for (let i = 0; i < QUERY_POLL_MAX; i += 1) {
    sleep(QUERY_POLL_INTERVAL_S);
    const status = json(request('GET', `/api/query/runs/${run.request_id}`, { ep: 'query_poll', token: token() }), {});
    if (QUERY_DONE.includes(status.status)) return;
  }
}

/** load/stress/spike/soak 공통 행동 비율: 트리 70 / 문서 20 / 업로드 티켓 5 / 채팅 5. */
export function mixedUser(data) {
  const fx = myFixture(data);
  const roll = Math.random() * 100;
  if (roll < 70) browseTree(fx);
  else if (roll < 90) openAndSave(fx);
  else if (roll < 95) uploadTicketOnly(fx);
  else chat(fx);
}
