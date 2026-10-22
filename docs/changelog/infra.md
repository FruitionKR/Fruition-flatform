# 인프라 변경 기록

## 2026-10-22

- Public ECR 다운로드 한도로 `minio-init` 이미지 pull이 실패하던 CI를 보완했다. 같은 AWS CLI 2.37.4 버전의 공식 Docker Hub 이미지를 다중 아키텍처 digest로 고정했다. 별도 Compose 프로젝트에서 4개 서비스의 정상 기동, MinIO·Kafka 초기화 종료 코드 0, 생성 버킷 조회 성공을 확인했다.

- 운영 JWT 전환 검증용 수동 Security authentication smoke workflow를 추가했다. feedback 환경의 검증 계정으로 공개 HTTPS 로그인·Access/Document 조회·refresh 교체·변조 서명 거부를 확인하고 테스트 세션을 로그아웃한다. 문서 생성·변경과 AWS 설정 변경은 수행하지 않으며 자격증명·응답 본문은 로그나 artifact에 남기지 않는다. 독립 회귀 테스트 7개를 통과했다.
- self-hosted runner 공통 계약에 맞춰 AWS_EC2_METADATA_DISABLED를 명시하고 관련 테스트 10개를 통과했다.
