// load: 평소 예상 부하. 트리 70 / 문서 열기·저장 20 / 업로드 티켓 5 / 채팅 5(LLM_SHARE로 제한).
// 기본값은 WAF 기본 한도(IP당 5분 3000건 ≈ 10 req/s, 전체 API 5분 6000건 ≈ 20 req/s) 안쪽이다.
import { seed, cleanup } from './lib/fixtures.js';
import { mixedUser } from './lib/flows.js';
import { thresholds, SUMMARY_TREND_STATS } from './lib/thresholds.js';
import { envNumber } from './lib/config.js';

const RATE = envNumber('LOAD_RATE', 3); // 초당 사용자 행동 수(행동 1회 ≈ 요청 1~4건)

export const options = {
  scenarios: {
    load: {
      executor: 'ramping-arrival-rate',
      startRate: 0,
      timeUnit: '1s',
      preAllocatedVUs: envNumber('LOAD_VUS', 20),
      maxVUs: envNumber('LOAD_MAX_VUS', 50),
      stages: [
        { target: RATE, duration: '2m' },
        { target: RATE, duration: __ENV.LOAD_HOLD || '10m' },
        { target: 0, duration: '1m' },
      ],
    },
  },
  thresholds: thresholds(),
  setupTimeout: '5m',
  teardownTimeout: '5m',
  summaryTrendStats: SUMMARY_TREND_STATS,
};

export function setup() {
  return seed({ chat: true });
}

export default function (data) {
  mixedUser(data);
}

export function teardown(data) {
  cleanup(data);
}
