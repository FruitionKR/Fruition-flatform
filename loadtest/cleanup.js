// 중단된 실행이 남긴 시험 워크스페이스(k6-loadtest-*)만 지운다. 부하를 만들지 않는다.
// 실행: k6 run cleanup.js
import { cleanupLeftovers } from './lib/fixtures.js';

export const options = { vus: 1, iterations: 1 };

export default function () {
  cleanupLeftovers();
}
