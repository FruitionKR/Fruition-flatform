// smoke: 1~2 VU, 1분. 계정·접근 코드·WAF·시드·정리가 맞는지 먼저 확인한다.
// 실행: k6 run smoke.js  (환경 변수는 README 참고)
import { seed, cleanup } from './lib/fixtures.js';
import { myFixture, browseTree, openAndSave, uploadTicketOnly, chat, think } from './lib/flows.js';
import { thresholds, SUMMARY_TREND_STATS } from './lib/thresholds.js';
import { envNumber } from './lib/config.js';

export const options = {
  scenarios: {
    smoke: {
      executor: 'constant-vus',
      vus: envNumber('SMOKE_VUS', 1),
      duration: __ENV.SMOKE_DURATION || '1m',
    },
  },
  thresholds: thresholds(),
  setupTimeout: '3m',
  teardownTimeout: '3m',
  summaryTrendStats: SUMMARY_TREND_STATS,
};

export function setup() {
  return seed({ chat: true });
}

// smoke는 비율 대신 모든 행동을 한 번씩 순서대로 돈다(LLM 질의는 LLM_SHARE가 0이면 보내지 않는다).
export default function (data) {
  const fx = myFixture(data);
  browseTree(fx);
  think();
  openAndSave(fx);
  think();
  uploadTicketOnly(fx);
  think();
  chat(fx);
  think();
}

export function teardown(data) {
  cleanup(data);
}
