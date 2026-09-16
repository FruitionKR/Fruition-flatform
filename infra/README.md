# 인프라

로컬 Compose 구성과 클라우드 인프라 설정을 보관한다.

- `compose.infra.yml`: PostgreSQL, Kafka, Redis, MinIO
- `compose.ai.yml`: Pipeline API와 AI 워커
- `compose.converter.yml`: 문서 변환기
- `compose.containerized.yml`: 백엔드 포함 컨테이너 통합 구성
- `compose.monitoring.yml`: Prometheus, Grafana, kafka-exporter (선택)
- `monitoring/`: Prometheus 스크레이프 설정, Grafana 프로비저닝과 커밋된 대시보드
- `postgres/`: 로컬 DB 초기화와 검증 스크립트
- `terraform/`: AWS 인프라 정의
- `.env.example`: 로컬 환경변수 예시

실행 방법은 [`docs/script.md`](../docs/script.md)를 참고한다.
