# 설정 화면 백엔드 신설 API 제안

작성일: 2026-09-07. 설정 모달(Figma 963:8660 / 963:8257 / 771:18800 / 981:10091 / 987:10705) 구현 과정에서
확인한 프론트엔드 미배선 항목 중, 백엔드 API 신설 없이는 구현할 수 없는 기능 목록이다.
전부 access-svc 소관이다.

현황 요약:

- 서버 API가 있어 이미 배선한 것: 워크스페이스 이름 변경(PATCH), LLM Provider, 스킬 목록·토글·작성·게시·수정
- 프론트만으로 처리한 것: 비밀번호 변경(기존 password-reset 흐름 연결), 자동 저장 영속화(localStorage),
  스킬 필터·검색(클라이언트 필터링)
- 알림 설정은 Discord와 동일하게 **기기별 저장(localStorage)** 정책으로 확정 — 서버 API 대상에서 제외

## 1. 사용자 프로필

| API | 용도 | 비고 |
|---|---|---|
| `PATCH /api/users/me` | 닉네임(display_name) 변경 | body `{display_name}`. 설정 모달 닉네임 필드 배선 대상 |

## 2. 이메일 변경

인증 필수. 기존 `email-verifications` 인프라 재사용 가능.

| API | 용도 |
|---|---|
| `POST /api/users/me/email-change` | 새 이메일로 인증코드 발송. 기존 `POST /api/auth/email-verifications`에 `purpose: "email_change"` 추가로 갈음 가능 |
| `PUT /api/users/me/email` | `verification_token`으로 이메일 확정 변경 |

## 3. 로그인 상태 비밀번호 변경

| API | 용도 | 비고 |
|---|---|---|
| `PUT /api/users/me/password` | body `{current_password, new_password}` | 현재는 비로그인 password-reset으로 우회 중. 변경 성공 시 다른 세션의 refresh token 무효화 권장 |

## 4. 계정 보안

| API | 용도 | 비고 |
|---|---|---|
| `POST /api/users/me/mfa` / `DELETE /api/users/me/mfa` | 다단계 인증 등록·해제 | TOTP면 secret 발급 → 코드 검증 2단계 |
| `GET /api/users/me/sessions` | 로그인된 기기 목록 | refresh token 세션 기반 |
| `DELETE /api/users/me/sessions/{session_id}` | 특정 기기 로그아웃 | - |

## 5. 멤버 관리

현재 멤버십 조회는 internal 전용(`GET /internal/authz/...`)뿐이라 public API가 전무하다.

| API | 용도 | 권한 |
|---|---|---|
| `GET /api/workspaces/{id}/members` | 멤버 목록(사용자·역할) | 멤버 |
| `POST /api/workspaces/{id}/invitations` | 이메일 초대 | OWNER |
| `PATCH /api/workspaces/{id}/members/{user_id}` | 역할 변경 | OWNER |
| `DELETE /api/workspaces/{id}/members/{user_id}` | 멤버 제거/탈퇴 | OWNER 또는 본인 |

## 6. 워크스페이스 아이콘

| API | 용도 | 비고 |
|---|---|---|
| `PUT /api/workspaces/{id}/icon` | 이미지 업로드(multipart) 또는 이모지 설정 | 저장은 기존 MinIO 재사용. `GET /api/workspaces` 응답에 `icon_url` 필드 추가 필요 |

## 7. 기존 API 결함 수정 (신설 아님)

### Skill publish의 코드펜스 거부 — author↔publish 검증 비대칭

- 증상: `POST /skills/author`가 생성한 초안의 `instructions_markdown`에 마크다운 코드펜스(```)가
  포함된 경우, 그 초안을 **수정 없이 그대로** `POST /skills/author/publish`로 보내면
  `400 SKILL_REQUEST_REJECTED`로 거부된다.
- 재현(2026-09-07, curl 확정): 같은 본문에서 코드펜스 블록만 제거하면 publish 200 성공.
  참고 문서를 포함한 author가 "고정 출력 템플릿"을 코드펜스로 감싼 초안을 자주 만들기 때문에
  실사용에서 게시 실패가 재발한다.
- 기대 동작: author가 통과시킨 초안은 publish의 안전 검증도 통과해야 한다.
  (코드펜스가 실제로 위험하다면 author 단계에서 issues로 걸러야 한다.)
- 위치 추정: `services/backend/document-svc` skill 게시 검증 로직 (skill_markdown 재조립 시
  frontmatter/중첩 코드펜스 파싱 관련으로 추정).

## 우선순위 추천

**5(멤버) > 1(닉네임) > 3(비밀번호) > 6(아이콘) > 2(이메일) > 4(보안)**

멤버 관리가 화면 대비 기능 공백이 가장 크고, 닉네임·비밀번호 변경은 구현 비용이 가장 작다.
