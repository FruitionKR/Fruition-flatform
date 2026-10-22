// meeting-ws: 회의 실시간 받아쓰기 WebSocket의 접속 경로(회의 생성 → 일회용 ticket → WS 접속 → ready → finish)만 확인한다.
// 기본으로 오디오를 보내지 않는다. 다만 접속하면 서버가 AI 실시간 전사 연결을 열고 크레딧을 예약하므로
// (Document meetings.md) MEETING_WS_ENABLED=1 일 때만 실행되며, 동시 접속 수를 작게 둔다.
import { check, sleep } from 'k6';
import { Counter, Trend } from 'k6/metrics';
import { WebSocket } from 'k6/websockets';
import { BASE_URL, envNumber } from './lib/config.js';
import { request, json, uuid, ensureAccessCookie } from './lib/http.js';
import { token } from './lib/auth.js';
import { seed, cleanup } from './lib/fixtures.js';
import { myFixture } from './lib/flows.js';
import { thresholds } from './lib/thresholds.js';

if (__ENV.MEETING_WS_ENABLED !== '1') {
  throw new Error('meeting-ws.js는 AI 실시간 전사 연결(비용)을 엽니다. 확인했다면 MEETING_WS_ENABLED=1 을 지정하세요.');
}

const READY_TIMEOUT_MS = 15000;
const FINISH_TIMEOUT_MS = 15000;
// 0이면 오디오를 보내지 않는다. 1 이상이면 그 초만큼 무음 PCM16(24 kHz mono) 1초 프레임을 보낸다(전사 비용 발생).
const AUDIO_SECONDS = envNumber('MEETING_AUDIO_SECONDS', 0);
const FRAME_BYTES = 48000;

const wsReady = new Trend('ws_ready_ms', true);
const wsOutcome = new Counter('ws_outcome');

export const options = {
  scenarios: {
    meeting_ws: {
      executor: 'per-vu-iterations',
      vus: envNumber('MEETING_VUS', 1),
      iterations: envNumber('MEETING_ITERATIONS', 1),
      maxDuration: '5m',
    },
  },
  thresholds: thresholds({
    ws_ready_ms: ['p(95)<8000'],
    'ws_outcome{result:finished}': ['count>0'],
  }),
  setupTimeout: '3m',
  teardownTimeout: '3m',
};

export function setup() {
  return seed({ chat: false });
}

function liveUrl(meetingId, ticket) {
  return `${BASE_URL.replace(/^http/, 'ws')}/api/meetings/${meetingId}/live?ticket=${encodeURIComponent(ticket)}`;
}

export default function (data) {
  const fx = myFixture(data);
  const t = token();
  ensureAccessCookie();
  const meeting = json(request('POST', `/api/workspaces/${fx.workspaceId}/meetings`, {
    ep: 'meeting', name: 'POST meeting', token: t, expect: [201],
    headers: { 'Idempotency-Key': uuid() }, body: { display_name: 'k6 회의', source: 'live' },
  }), {});
  if (!meeting.meeting_id) return;
  const ticket = json(request('POST', `/api/workspaces/${fx.workspaceId}/meetings/${meeting.meeting_id}/live-tickets`, {
    ep: 'meeting', name: 'POST live ticket', token: t,
  }), {});
  if (ticket.ticket) runSocket(meeting.meeting_id, ticket.ticket);
  request('DELETE', `/api/workspaces/${fx.workspaceId}/meetings/${meeting.meeting_id}`, {
    ep: 'meeting', name: 'DELETE meeting', token: token(), expect: [200, 204, 404],
  });
  sleep(1);
}

function runSocket(meetingId, ticket) {
  const startedAt = Date.now();
  let result = 'timeout';
  // 서버는 허용된 Origin만 받는다(CORS_ALLOWED_ORIGINS = 화면 주소). WAF 접근 코드 쿠키도 같이 보낸다.
  const ws = new WebSocket(liveUrl(meetingId, ticket), null, {
    headers: { Origin: BASE_URL },
    tags: { ep: 'meeting_ws' },
  });
  const readyTimer = setTimeout(() => ws.close(), READY_TIMEOUT_MS);

  ws.onmessage = (event) => {
    if (typeof event.data !== 'string') return;
    const msg = JSON.parse(event.data);
    if (msg.type === 'ready') {
      clearTimeout(readyTimer);
      wsReady.add(Date.now() - startedAt);
      sendAudio(ws);
      ws.send(JSON.stringify({ type: 'finish' }));
      setTimeout(() => ws.close(), FINISH_TIMEOUT_MS);
    } else if (msg.type === 'finished') {
      result = 'finished';
    } else if (msg.type === 'error') {
      result = `error_${msg.code}`;
    }
  };
  ws.onerror = () => {
    result = result === 'timeout' ? 'socket_error' : result;
  };
  ws.onclose = () => {
    clearTimeout(readyTimer);
    wsOutcome.add(1, { result });
    check(result, { 'meeting ws finished': (r) => r === 'finished' });
  };
}

function sendAudio(ws) {
  if (AUDIO_SECONDS <= 0) return;
  const silence = new ArrayBuffer(FRAME_BYTES);
  for (let i = 0; i < AUDIO_SECONDS; i += 1) ws.send(silence);
  ws.send(JSON.stringify({ type: 'commit' }));
}

export function teardown(data) {
  cleanup(data);
}
