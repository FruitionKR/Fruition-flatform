// 환경 변수와 테스트 계정 파일을 읽는다. 비밀(비밀번호·접근 코드)은 저장소에 두지 않는다.
const env = __ENV;

function required(name) {
  const value = (env[name] || '').trim();
  if (!value) throw new Error(`${name} 환경 변수가 필요합니다. loadtest/README.md의 환경 변수 표를 보세요.`);
  return value;
}

function number(name, fallback) {
  const raw = env[name];
  if (raw === undefined || raw === '') return fallback;
  const value = Number(raw);
  if (!Number.isFinite(value)) throw new Error(`${name}=${raw} 는 숫자가 아닙니다.`);
  return value;
}

export const BASE_URL = required('BASE_URL').replace(/\/+$/, '');
const TARGET_HOST = BASE_URL.replace(/^https?:\/\//, '').split('/')[0].split(':')[0];
const IS_LOCAL = TARGET_HOST === 'localhost' || TARGET_HOST === '127.0.0.1';

// 잘못된 호스트(운영·타사 엔드포인트)를 실수로 때리지 않도록, 로컬이 아니면 같은 호스트를 한 번 더 적게 한다.
if (!IS_LOCAL && (env.CONFIRM_TARGET || '').trim() !== TARGET_HOST) {
  throw new Error(`로컬이 아닌 대상(${TARGET_HOST})입니다. 확인했다면 CONFIRM_TARGET=${TARGET_HOST} 를 함께 지정하세요.`);
}

export const ACCESS_CODE = (env.ACCESS_CODE || '').trim();
// 0이면 LLM을 부르는 질의를 전혀 보내지 않는다(기본값). 0~1 사이 비율.
export const LLM_SHARE = Math.min(Math.max(number('LLM_SHARE', 0), 0), 1);
// VU 하나가 테스트 동안 보낼 수 있는 LLM 질의 상한. 전체 상한 = VU 수 × 이 값.
export const LLM_MAX_PER_VU = number('LLM_MAX_PER_VU', 1);
export const QUERY_PROVIDER = (env.QUERY_PROVIDER || '').trim();
export const QUERY_MODEL = (env.QUERY_MODEL || '').trim();
export const SEED_DOCS = number('SEED_DOCS', 10);
export const RUN_ID = (env.RUN_ID || `${Date.now()}`).trim();
export const WORKSPACE_PREFIX = 'k6-loadtest-';
export const THINK_MIN_S = number('THINK_MIN_S', 1);
export const THINK_MAX_S = number('THINK_MAX_S', 3);
export { number as envNumber };

function resolveAccountsPath(path) {
  // open()은 이 모듈(loadtest/lib) 기준 상대 경로를 쓴다. 상대 경로는 loadtest/ 기준으로 맞춘다.
  return path.startsWith('/') ? path : `../${path}`;
}

function loadAccounts() {
  const inline = (env.ACCOUNTS_JSON || '').trim();
  const text = inline || open(resolveAccountsPath(env.ACCOUNTS_FILE || 'accounts.json'));
  const accounts = JSON.parse(text);
  if (!Array.isArray(accounts) || accounts.length === 0) {
    throw new Error('계정 파일은 [{"email":"...","password":"..."}] 형식의 비어 있지 않은 배열이어야 합니다.');
  }
  accounts.forEach((a, i) => {
    if (!a.email || !a.password) throw new Error(`계정 ${i}에 email/password가 없습니다.`);
  });
  return accounts;
}

// init 단계에서 한 번 읽는다(VU마다 복사본).
export const ACCOUNTS = loadAccounts();

export function accountForVu(vu) {
  return ACCOUNTS[(vu - 1) % ACCOUNTS.length];
}
