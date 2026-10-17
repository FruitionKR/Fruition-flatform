// 공통 요청 도우미: 엔드포인트 묶음 태그(ep), 기대 상태 코드, WAF 차단 감지.
import http from 'k6/http';
import { check } from 'k6';
import { Counter } from 'k6/metrics';
import { sha256 } from 'k6/crypto';
import { BASE_URL, ACCESS_CODE } from './config.js';

// WAF가 막은 응답(접근 코드 403, rate-based 429). 하나라도 늘면 시험 설계가 WAF 한도와 어긋났다는 뜻이다.
export const wafBlocks = new Counter('waf_blocks');
// 공동 편집 충돌(409)·편집 잠금 경합(423)은 실패가 아니라 정상 동작이라 따로 센다.
export const editContention = new Counter('edit_contention');

// 프론트엔드 hashAccessCode와 같은 값: 앞뒤 공백을 뺀 코드의 소문자 hex SHA-256.
const ACCESS_COOKIE_VALUE = ACCESS_CODE ? sha256(ACCESS_CODE, 'hex') : '';
let accessCookieSet = false;

export function ensureAccessCookie() {
  if (!ACCESS_COOKIE_VALUE || accessCookieSet) return;
  http.cookieJar().set(BASE_URL, 'fruition_access', ACCESS_COOKIE_VALUE, { path: '/' });
  accessCookieSet = true;
}

function isWafBlock(res) {
  if (res.status === 429) return true;
  if (res.status !== 403) return false;
  const body = typeof res.body === 'string' ? res.body : '';
  return body.includes('접근 코드');
}

/**
 * @param {string} method
 * @param {string} path  BASE_URL 뒤 경로(/api/...)
 * @param {object} opts  { ep, token, body, headers, expect: number[], name }
 */
export function request(method, path, opts = {}) {
  ensureAccessCookie();
  const expect = opts.expect || [200];
  const headers = Object.assign({}, opts.headers || {});
  if (opts.token) headers.Authorization = `Bearer ${opts.token}`;
  let body = opts.body;
  if (body !== undefined && body !== null && typeof body === 'object' && !opts.multipart) {
    body = JSON.stringify(body);
    headers['Content-Type'] = 'application/json';
  }
  const res = http.request(method, `${BASE_URL}${path}`, body === undefined ? null : body, {
    headers,
    tags: { ep: opts.ep, name: opts.name || `${method} ${opts.ep}` },
    responseCallback: http.expectedStatuses(...expect),
  });
  if (isWafBlock(res)) wafBlocks.add(1, { ep: opts.ep });
  check(res, { [`${opts.ep} 상태 ${expect.join('/')}`]: (r) => expect.includes(r.status) }, { ep: opts.ep });
  return res;
}

export function json(res, fallback = null) {
  try {
    return res.json();
  } catch (_) {
    return fallback;
  }
}

export function uuid() {
  // crypto.randomUUID가 없는 런타임을 위해 직접 만든다(테스트용 멱등 키라 암호 강도는 필요 없다).
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    return (c === 'x' ? r : (r & 0x3) | 0x8).toString(16);
  });
}
