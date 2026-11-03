// 시험 데이터 준비(setup)와 정리(teardown).
// 계정마다 이번 실행 전용 워크스페이스(k6-loadtest-<RUN_ID>)를 만들고 그 안에만 문서를 만든다.
// 정리는 그 워크스페이스만 지운다(소프트 삭제 → 휴지통). 다른 워크스페이스는 건드리지 않는다.
import { request, json, uuid } from './http.js';
import { login } from './auth.js';
import { ACCOUNTS, RUN_ID, SEED_DOCS, WORKSPACE_PREFIX } from './config.js';

const SEED_MARKDOWN = `# 부하 시험 문서\n\n${'부하 시험용 본문 문장입니다. '.repeat(40)}\n\n- 항목 1\n- 항목 2\n`;

function uniqueAccounts() {
  const seen = new Set();
  return ACCOUNTS.filter((a) => (seen.has(a.email) ? false : seen.add(a.email)));
}

function seedAccount(account, opts) {
  const token = login(account);
  const ws = json(request('POST', '/api/workspaces', {
    ep: 'seed', name: 'seed workspace', token, expect: [201],
    body: { name: `${WORKSPACE_PREFIX}${RUN_ID}` },
  }), {});
  if (!ws.id) throw new Error(`워크스페이스 생성 실패: ${account.email}`);

  const folder = json(request('POST', `/api/workspaces/${ws.id}/folders`, {
    ep: 'seed', name: 'seed folder', token, expect: [201],
    headers: { 'Idempotency-Key': uuid() }, body: { name: 'k6' },
  }), {});

  const docIds = [];
  for (let i = 0; i < SEED_DOCS; i += 1) {
    const doc = json(request('POST', `/api/workspaces/${ws.id}/documents/markdown`, {
      ep: 'seed', name: 'seed document', token, expect: [201],
      headers: { 'Idempotency-Key': uuid() },
      body: { display_name: `k6 문서 ${i + 1}`, folder_id: folder.id || undefined, markdown: SEED_MARKDOWN },
    }), {});
    if (doc.id) docIds.push(doc.id);
  }

  let chatSessionId = null;
  if (opts.chat) {
    const chat = json(request('POST', `/api/workspaces/${ws.id}/chat/sessions`, {
      ep: 'seed', name: 'seed chat session', token, expect: [201], body: { title: 'k6 부하 시험' },
    }), {});
    chatSessionId = chat.id || null;
  }
  return { workspaceId: ws.id, folderId: folder.id || null, docIds, chatSessionId };
}

/** setup()에서 부른다. 반환값은 모든 VU에 전달된다(비밀번호는 넣지 않는다). */
export function seed(opts = { chat: true }) {
  const byEmail = {};
  uniqueAccounts().forEach((account) => {
    byEmail[account.email] = seedAccount(account, opts);
  });
  return { runId: RUN_ID, byEmail };
}

function deleteWorkspace(token, workspaceId) {
  request('DELETE', `/api/workspaces/${workspaceId}`, {
    ep: 'cleanup', name: 'delete workspace', token, expect: [200, 404],
    headers: { 'Idempotency-Key': uuid() },
  });
}

/** teardown()에서 부른다. 이번 실행이 만든 워크스페이스만 지운다. */
export function cleanup(data) {
  if (!data || !data.byEmail) return;
  uniqueAccounts().forEach((account) => {
    const seeded = data.byEmail[account.email];
    if (!seeded || !seeded.workspaceId) return;
    deleteWorkspace(login(account), seeded.workspaceId);
  });
}

/** 중단된 실행의 잔여물 정리: 이름이 k6-loadtest- 로 시작하는 워크스페이스만 지운다. */
export function cleanupLeftovers() {
  uniqueAccounts().forEach((account) => {
    const token = login(account);
    const list = json(request('GET', '/api/workspaces', { ep: 'cleanup', name: 'list workspaces', token }), {});
    (list.workspaces || [])
      .filter((w) => typeof w.name === 'string' && w.name.startsWith(WORKSPACE_PREFIX))
      .forEach((w) => deleteWorkspace(token, w.id));
  });
}
