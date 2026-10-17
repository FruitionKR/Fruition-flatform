// 합격 기준과 자동 중단 조건.
// abortOnFail은 안전장치다: 오류율 급증·WAF 차단이 보이면 부하를 더 넣지 않고 멈춘다.

const ABORT = { abortOnFail: true, delayAbortEval: '30s' };

/** 엔드포인트 묶음(ep 태그)별 p95 목표(ms). */
export const P95_MS = {
  workspaces: 500,
  tree: 500,
  doc_read: 500,
  doc_lock: 500,
  doc_save: 1000,
  upload_ticket: 800,
  chat_read: 500,
  query_start: 1000,
  query_poll: 500,
};

export function thresholds(extra = {}) {
  const t = {
    // 합격 기준: 전체 실패율 1% 미만, check 99% 이상.
    http_req_failed: [{ threshold: 'rate<0.01' }, Object.assign({ threshold: 'rate<0.05' }, ABORT)],
    checks: ['rate>0.99'],
    // WAF가 한 번이라도 막으면 결과가 WAF 한도를 잰 것이 되므로 바로 멈춘다.
    waf_blocks: [Object.assign({ threshold: 'count<1' }, { abortOnFail: true })],
    // 전체 p95가 3초를 넘으면 사용자 체감 장애로 보고 멈춘다.
    http_req_duration: ['p(95)<1000', Object.assign({ threshold: 'p(95)<3000' }, ABORT)],
  };
  Object.keys(P95_MS).forEach((ep) => {
    t[`http_req_duration{ep:${ep}}`] = [`p(95)<${P95_MS[ep]}`];
  });
  return Object.assign(t, extra);
}

/** 요약에 표시할 응답 시간 통계. */
export const SUMMARY_TREND_STATS = ['avg', 'p(90)', 'p(95)', 'p(99)', 'max'];
