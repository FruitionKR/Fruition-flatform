// spike: 평소 도착률에서 10초 만에 10배로 뛰었다가 돌아온다.
// ALB는 트래픽에 맞춰 점진적으로 확장하므로 5분 안에 2배를 넘는 급증에는 503/지연이 생길 수 있다(README "ALB 확장" 참고).
// 이 시험은 그 상태(그리고 HPA 30초 안정화·Pod 기동 시간)를 보려는 것이라 LCU 예약 없이 먼저 돌린다.
import { seed, cleanup } from './lib/fixtures.js';
import { mixedUser } from './lib/flows.js';
import { thresholds, SUMMARY_TREND_STATS } from './lib/thresholds.js';
import { envNumber } from './lib/config.js';

const BASE = envNumber('SPIKE_BASE_RATE', 2);
const PEAK = BASE * envNumber('SPIKE_MULTIPLIER', 10);

export const options = {
  scenarios: {
    spike: {
      executor: 'ramping-arrival-rate',
      startRate: BASE,
      timeUnit: '1s',
      preAllocatedVUs: envNumber('SPIKE_VUS', 40),
      maxVUs: envNumber('SPIKE_MAX_VUS', 300),
      stages: [
        { target: BASE, duration: '2m' },
        { target: PEAK, duration: '10s' },
        { target: PEAK, duration: __ENV.SPIKE_HOLD || '2m' },
        { target: BASE, duration: '10s' },
        { target: BASE, duration: '3m' }, // 회복 구간: 지연·오류가 원래대로 돌아오는지 본다
        { target: 0, duration: '30s' },
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
