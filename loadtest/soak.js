// soak: 보통 부하를 1~2시간 유지해 메모리 누수, DB 연결 고갈, burstable 인스턴스(t3/t4g) CPU 크레딧 소진을 본다.
// access token(15분)은 VU마다 refresh 쿠키로 갱신되므로 토큰 회전 경로도 함께 검증된다.
import { seed, cleanup } from './lib/fixtures.js';
import { mixedUser } from './lib/flows.js';
import { thresholds, SUMMARY_TREND_STATS } from './lib/thresholds.js';
import { envNumber } from './lib/config.js';

const RATE = envNumber('SOAK_RATE', 2);

export const options = {
  scenarios: {
    soak: {
      executor: 'constant-arrival-rate',
      rate: RATE,
      timeUnit: '1s',
      duration: __ENV.SOAK_DURATION || '90m',
      preAllocatedVUs: envNumber('SOAK_VUS', 15),
      maxVUs: envNumber('SOAK_MAX_VUS', 40),
    },
  },
  thresholds: thresholds({ 'http_req_duration{ep:auth_refresh}': ['p(95)<800'] }),
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
