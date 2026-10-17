// stress: 도착률을 계단식으로 올려 한계(HPA 상한 4·노드 상한·RDS)를 찾는다.
// WAF 기본 한도를 넘으므로 README의 "WAF 한도 임시 상향" 없이 실행하면 waf_blocks 임계값으로 즉시 멈춘다.
import { seed, cleanup } from './lib/fixtures.js';
import { mixedUser } from './lib/flows.js';
import { thresholds, SUMMARY_TREND_STATS } from './lib/thresholds.js';
import { envNumber } from './lib/config.js';

const START = envNumber('STRESS_START_RATE', 5);
const STEPS = envNumber('STRESS_STEPS', 5);
const STEP_HOLD = __ENV.STRESS_STEP_HOLD || '3m';

function stages() {
  const out = [];
  for (let i = 0; i < STEPS; i += 1) {
    const target = START * 2 ** i; // 5 → 10 → 20 → 40 → 80
    out.push({ target, duration: '1m' }, { target, duration: STEP_HOLD });
  }
  out.push({ target: 0, duration: '2m' });
  return out;
}

export const options = {
  scenarios: {
    stress: {
      executor: 'ramping-arrival-rate',
      startRate: 1,
      timeUnit: '1s',
      preAllocatedVUs: envNumber('STRESS_VUS', 50),
      maxVUs: envNumber('STRESS_MAX_VUS', 400),
      stages: stages(),
    },
  },
  // stress는 한계를 찾는 시험이라 p95 목표 미달은 기록만 하고, 오류율·WAF·3초 초과에서만 멈춘다.
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
