# 실행 스크립트

로컬 개발 환경을 준비하고 서비스별로 시작·종료하는 명령을 보관한다.

- `dev-up.sh` / `dev-down.sh`: 전체 개발 환경
- `front-up.sh` / `front-down.sh`: 프론트엔드
- `back-up.sh` / `back-down.sh`: 백엔드
- `back-test.sh`: Java 21을 찾아 백엔드 Gradle 테스트 실행
- `ai-up.sh` / `ai-down.sh`: Pipeline API와 AI 워커
- `bootstrap.sh`: 필수 도구와 의존성 준비
- `lib/`: 스크립트 공용 함수

상세 사용법은 [`docs/script.md`](../docs/script.md)를 참고한다.
