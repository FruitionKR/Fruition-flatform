# Markdown 문서 공유 작업 계획

## 1. 문서 정보

- 상태: Draft
- 작성일: 2026-07-23
- 기능 SDD: [`markdown-document-sharing.md`](../markdown-document-sharing.md)

## 2. 실행 원칙

- 각 TASK의 실패 테스트를 구현보다 먼저 작성한다.
- token 원문과 Markdown을 로그·DB에 남기지 않는다.
- 이메일 전달과 권한 부여를 분리한다.
- 기존 문서 owner/member 권한과 asset 접근의 회귀를 함께 검증한다.

## 3. 작업 계획

### TASK-S001 공유 데이터 모델과 migration

- 관련 요구사항: `REQ-S001`, `REQ-S004`, `REQ-S007`, `REQ-S012`, `REQ-S014`, `REQ-S020`
- 작업:
  - workspace·guest 초대와 guest 접근 테이블
  - 웹 공유와 partial unique index
  - 이메일 outbox와 감사 로그
  - token hash index와 FK·삭제 정책
- 완료 조건:
  - [ ] migration·schema 검증 통과
  - [ ] 같은 범위의 `PENDING` 초대 중복 차단
  - [ ] 문서당 `ACTIVE` 웹 공유 한 건
  - [ ] token 원문 저장 컬럼 없음

### TASK-S002 member 초대·수락

- 관련 요구사항: `REQ-S001`~`REQ-S003`, `REQ-S007`
- 작업:
  - owner 권한과 이메일 정규화
  - 초대 생성·조회·재전송·취소
  - 로그인 이메일 일치 수락과 membership 생성
- 완료 조건:
  - [ ] owner가 아닌 member의 초대 `403`
  - [ ] 다른 이메일 계정 수락 거절
  - [ ] 만료·취소 token `410`
  - [ ] 중복 수락에서 membership 한 건

### TASK-S003 guest 초대·접근

- 관련 요구사항: `REQ-S004`~`REQ-S006`
- 작업:
  - 문서 owner 권한 기반 초대
  - guest 수락·조회·제거
  - 문서 하나의 읽기 권한 filter
- 완료 조건:
  - [ ] 같은 폴더의 다른 문서·원본 자료 접근 차단
  - [ ] guest의 CRUD·이동·AI·내보내기 차단
  - [ ] 제거 다음 요청부터 접근 차단
  - [ ] 재초대에서 새 접근·token 생성

### TASK-S004 이메일 outbox worker

- 관련 요구사항: `REQ-S008`
- 작업:
  - 초대와 outbox 원자적 생성
  - batch 잠금·전송·지수 backoff
  - 전달 상태와 재전송
- 완료 조건:
  - [ ] DB rollback 시 이메일 작업 없음
  - [ ] 일시 실패 재시도
  - [ ] 최종 실패에도 권한 미부여
  - [ ] worker 중복 실행에서 상태 일관성 유지

### TASK-S005 문서·workspace 소유권

- 관련 요구사항: `REQ-S009`~`REQ-S011`
- 작업:
  - 문서 소유권 이전과 AI proposal 무효화
  - member 제거 시 소유 문서 일괄 이전
  - workspace owner 이전과 마지막 owner 보호
- 완료 조건:
  - [ ] guest·대기 사용자 이전 대상 거절
  - [ ] 문서 이전 시 본문·버전·적용 이력 유지
  - [ ] member 제거 중 실패 시 전체 rollback
  - [ ] 마지막 owner 탈퇴 `409`

### TASK-S006 웹 공유 수명주기

- 관련 요구사항: `REQ-S012`~`REQ-S015`, `REQ-S018`
- 작업:
  - 활성화·조회·만료 변경·해제·재발급
  - token hash 조회와 요청 시점 만료 판정
  - 최신 저장본 공개 응답과 `no-store`
- 완료 조건:
  - [ ] 활성 링크 재조회에서 같은 URL
  - [ ] 재발급·재활성화에서 새 token
  - [ ] 이전 token 영구 차단
  - [ ] 삭제·만료·해제 응답 구분 노출 없음

### TASK-S007 공개 이미지

- 관련 요구사항: `REQ-S016`, `REQ-S018`
- 선행 작업: [`markdown-document-assets-tasks.md`](markdown-document-assets-tasks.md)의 저장·참조 모델
- 작업:
  - 로그인 guest의 문서·asset 참조 검증 endpoint
  - 공유 token 기반 asset endpoint
  - 최신 Markdown 참조 확인
  - 내부 storage URL 비노출과 보안 header
- 완료 조건:
  - [ ] 미참조·다른 문서 asset 차단
  - [ ] guest가 공유받은 문서의 참조 이미지만 조회
  - [ ] 공유 상태 변경 즉시 이미지 차단
  - [ ] `nosniff`·`no-store` 적용
  - [ ] 내부 asset·storage URL 미노출

### TASK-S008 공개 renderer

- 관련 요구사항: `REQ-S015`, `REQ-S017`
- 작업:
  - 읽기 전용 공개 화면
  - raw HTML·MDX 비실행
  - URL scheme sanitize와 외부 링크 `rel`
  - CSP, `Referrer-Policy`, `noindex`, `nofollow`
- 완료 조건:
  - [ ] XSS fixture 무실행
  - [ ] 댓글·편집·AI·복제·다운로드 UI 없음
  - [ ] 내부 링크 권한 안내
  - [ ] 외부 이동 시 공유 token referrer 미전송
  - [ ] 모바일 읽기 최소 대응

### TASK-S009 rate limit·감사 로그

- 관련 요구사항: `REQ-S019`, `REQ-S020`
- 작업:
  - 초대·재발급·공개 조회 제한
  - `Retry-After`
  - 공유 작업 append-only 감사 로그
  - gateway·access log 공유 token 마스킹
  - owner 전용 cursor 조회와 filter
- 완료 조건:
  - [ ] 각 제한 경계와 window reset 검증
  - [ ] 감사 action·결과 누락 없음
  - [ ] 애플리케이션·gateway·access log에 token·Markdown·이메일 본문 부재
  - [ ] 일반 member 감사 로그 조회 차단

### TASK-S010 frontend 공유 UI

- 관련 요구사항: `REQ-S001`~`REQ-S006`, `REQ-S009`~`REQ-S015`
- 작업:
  - member·guest 초대와 상태
  - 소유권 이전·member 제거 확인
  - 웹 링크 복사·만료·해제·재발급
  - 전달 실패 재전송과 오류 안내
- 완료 조건:
  - [ ] 권한별 control 노출
  - [ ] 위험 작업 재확인
  - [ ] 만료·해제 상태 반영
  - [ ] token을 client log에 기록하지 않음

### TASK-S011 계약·보안·회귀 검증

- 관련 요구사항: 전체 공유 요구사항
- 작업:
  - API 문서와 요구사항–테스트 추적표
  - member/guest/web 권한 matrix E2E
  - Core·Assets·AI·Hierarchy 회귀 테스트
- 완료 조건:
  - [ ] 전체 backend·frontend 테스트 통과
  - [ ] 공개 endpoint 인증 예외 범위 최소화
  - [ ] 기존 member 읽기·이동과 owner CRUD 회귀 없음
  - [ ] `git diff --check` 통과

## 4. 실행 순서

```text
TASK-S001 → TASK-S002 ─┬→ TASK-S004
                       ├→ TASK-S005
            TASK-S003 ─┘
TASK-S001 → TASK-S006 → TASK-S007
                       └→ TASK-S008
TASK-S002/003/005/006 → TASK-S009 → TASK-S010
전체 완료 → TASK-S011
```

## 5. 검증 명령

```sh
cd backend
./gradlew test
./gradlew flywayValidate

cd ../frontend
npm test
```
