# ADR-0022: 음성 기능의 서비스 책임과 실시간 전사 연결

상태: 제안. 구현 전이며 Vercel·ALB에서의 WebSocket 동작은 검증 대기.

## 맥락

AI 서비스에는 음성 파일 전사(`POST /speech/transcriptions`), 실시간 전사(`WS /speech/transcriptions/live`), 회의록 초안(`POST /meeting-notes/preview`) 내부 API가 있다. 모두 `X-Internal-Token`을 요구하고 오디오·전사를 저장하지 않으며, 확정 전사의 저장은 호출 서비스 책임으로 정해져 있다. [AI 음성 API](https://github.com/FruitionKR/Fruition-ai/blob/main/docs/api/speech.md)

사용자용 경로가 없어 브라우저가 이 기능을 쓸 수 없다. 추가하려면 다음 제약을 함께 다뤄야 한다.

- 실시간 전사는 한 연결에서 오디오 frame과 전사 이벤트가 양방향으로 오가며, 연결당 최대 60분이다. 기존 통신 방식(HTTP 요청·응답, Kafka command/event, SSE)은 단방향이다.
- 브라우저 WebSocket API는 `Authorization` 헤더를 보낼 수 없다.
- 브라우저의 모든 API 요청은 Vercel `next.config.mjs` rewrite를 거쳐 같은 origin으로 들어오고, ALB는 host 기반으로만 라우팅한다. Vercel rewrite는 WebSocket upgrade를 중계하지 않는 것으로 알려져 있다.
- AWS에서 document-svc는 2개 Pod로 동작한다. ALB 기본 idle timeout은 60초다.
- AI의 음성 호출은 모델 사용량 원장에 기록되지 않는다. 원장은 `run_id`, `workspace_id`, `user_id`가 있는 호출만 기록한다.

## 결정

1. **책임 분리**
   - AI: 음성 모델 호출과 사용량 기록만 맡는다. 오디오·전사를 저장하지 않는 기존 원칙을 유지한다. 모델은 AI가 고정한다(파일 전사 `gpt-transcribe`, 실시간 전사 `gpt-live-transcribe`, 회의록 `gpt-5-nano`).
   - Document: 사용자용 음성 API, 인가, 확정 전사와 녹음 원본 저장을 맡는다. 저장 모델은 [Document ADR-0023](https://github.com/FruitionKR/Fruition-document/blob/main/docs/adr/0023-meeting-transcripts-and-recordings.md)을 따른다.
   - Frontend: 마이크 권한, PCM16 24 kHz 변환, 녹음 원본 생성을 맡는다.
2. **실시간 전사는 Document가 WebSocket을 1:1 중계한다.** 브라우저 ↔ Document ↔ AI를 연결마다 한 쌍으로 잇는다. Document는 오디오를 가공하지 않고 넘기며 전사 이벤트를 저장한 뒤 브라우저에 전달한다. 실시간 경로에는 Kafka를 쓰지 않는다.
3. **WebSocket 인가는 일회용 ticket으로 한다.** 브라우저는 JWT로 인증한 HTTP 요청으로 ticket을 받는다. ticket은 Redis에 60초 TTL로 저장되고 handshake에서 한 번만 쓰인다(`GETDEL`). handshake는 ticket과 함께 `Origin`을 CORS 허용 origin 목록과 대조한다. JWT를 URL에 넣지 않는다.
4. **브라우저는 WebSocket만 API host에 직접 연결한다.** `wss://api.<domain>`으로 접속하며 Vercel rewrite를 거치지 않는다. Frontend는 이 주소를 공개 환경변수로 받는다. 다른 HTTP 요청은 기존 rewrite 경로를 유지한다.
5. **ALB idle timeout을 120초로 올린다.** AI가 60초 동안 제공자 이벤트가 없으면 연결을 닫으므로 그보다 길어야 한다. WAF는 handshake 요청만 검사한다.
6. **Pod 교체 시 연결이 끊기는 것을 허용한다.** 회의당 동시 연결은 Redis 잠금으로 1개로 제한한다. 배포·장애로 끊기면 확정 전사는 이미 저장돼 있고, 브라우저가 새 ticket으로 다시 연결한다. sticky session은 쓰지 않는다.
7. **사용량**: 음성·회의록 사용량 기록은 AI가 요청(실시간은 연결)마다 `run_id`를 직접 만들어 기존 원장에 남기는 방식으로 AI 저장소에서 반영한다. 원장 합산은 workspace·사용자·기간 기준이라 Document가 run_id를 넘길 필요가 없고, Document 구현은 이 작업을 기다리지 않는다.

## 대안과 기각 사유

- **브라우저가 AI에 직접 연결**: 내부 토큰을 브라우저에 줘야 하고, 확정 전사 저장이 브라우저 책임이 되어 연결이 끊길 때 전사가 사라진다.
- **AI가 전사 저장**: 회의 전사는 사용자 문서와 같은 사용자 콘텐츠다. AI가 사용자 콘텐츠의 원본 저장소가 되면 [ADR-0020](0020-platform-and-document-ownership.md)의 소유 경계와 삭제 책임이 나뉜다.
- **Kafka로 오디오·전사 전달**: 1초 단위 frame마다 메시지가 생기고 왕복 지연이 늘어난다. 연결 안의 순서는 WebSocket이 이미 보장한다.
- **HTTP chunk 업로드 + SSE 응답**: 요청 두 갈래의 순서·짝을 서버가 맞춰야 하고, AI 쪽 WebSocket 계약을 다시 바꿔야 한다.
- **JWT를 query string에 넣기**: access log와 브라우저 기록에 오래 유효한 토큰이 남는다.
- **Vercel rewrite 경유**: WebSocket upgrade를 중계하지 않는다.
- **workspace별 음성 모델 설정(Access 소유)**: 용도마다 선택지가 OpenAI 하나뿐이고, 다른 provider는 AI 구현이 먼저 필요하다. 설정 컬럼·화면·용도별 catalog가 선택지 없이 늘어난다. 다른 provider를 붙일 때 다시 검토한다.

## 결과

플랫폼 통신 방식에 WebSocket이 추가되고, API host가 브라우저에 직접 노출되는 첫 경로가 생긴다. Document Pod가 최대 60분짜리 연결을 들고 있으므로 롤링 배포 때 진행 중인 회의 연결이 끊긴다. 확정 전사는 보존되지만 사용자는 재연결을 겪는다. 동시 회의 수가 늘면 Pod당 연결 수 지표와 배포 시 연결 drain을 추가로 검토한다.

적용 전에 두 가지를 검증한다. 하나는 Vercel rewrite로 WebSocket이 실제로 중계되지 않는지다. 다른 하나는 ALB·WAF를 거친 `wss://api.<domain>` 연결이 60분 동안 유지되는지다.
