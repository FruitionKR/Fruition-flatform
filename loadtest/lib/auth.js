// VU별 로그인과 access token 갱신.
// refresh 토큰은 회전하며 같은 토큰으로 동시에 갱신하면 하나만 성공한다(Access auth.md).
// 그래서 VU마다 자기 로그인 세션(자기 cookie jar의 refresh 쿠키)을 갖고 순서대로만 갱신한다.
import { request, json } from './http.js';
import { accountForVu } from './config.js';

const REFRESH_MARGIN_MS = 60 * 1000;
let session = null; // { token, expiresAt }

function store(res) {
  const body = json(res, {});
  if (!body.access_token) return null;
  const ttlMs = (body.expires_in || 900) * 1000;
  session = { token: body.access_token, expiresAt: Date.now() + ttlMs };
  return session.token;
}

export function login(account) {
  const res = request('POST', '/api/auth/login', {
    ep: 'auth_login',
    body: { email: account.email, password: account.password },
  });
  if (res.status !== 200) throw new Error(`로그인 실패(${res.status}) ${account.email}`);
  return store(res);
}

function refresh() {
  const res = request('POST', '/api/auth/refresh', { ep: 'auth_refresh', expect: [200, 401] });
  return res.status === 200 ? store(res) : null;
}

/** 현재 VU의 유효한 access token. 만료 1분 전이면 refresh, 실패하면 다시 로그인한다. */
export function token() {
  if (!session) return login(accountForVu(__VU));
  if (Date.now() < session.expiresAt - REFRESH_MARGIN_MS) return session.token;
  return refresh() || login(accountForVu(__VU));
}
