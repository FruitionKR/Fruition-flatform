# PDF multipart IAM 인증 수정 릴리스 검토

대상 릴리스: `efaf1a8bbfe3e4754840bb84243090ff46bc7a02`

- Access: `b73cf750a312383057dad366ee5827868a0c9354`
- Document: `e348658001f50d31756a5b98b3b1dc48dd59cf73`
- AI: `c6a03083e22dadae10d99a148c6e43408b46caae`

이전 [운영 배포](https://github.com/FruitionKR/Fruition-flatform/actions/runs/35613521438)는 모든 서비스 rollout과 인증된 Markdown 저장·AI ingest 검증을 통과했으나, 추가 PDF 검증의 multipart 시작 요청에서 HTTP 500이 발생했다. 문서 서비스 로그에서 정적 AWS 자격 증명이 없을 때 IAM fallback 전에 발생하는 `AccessKey must not be null` 예외를 확인했다. 이 단계에서는 파일이 업로드되지 않았으며 테스트 문서 정리 실패는 없었다. 프런트엔드 활성화는 보류했다.

[Document PR #10](https://github.com/FruitionKR/Fruition-document/pull/10)은 multipart 클라이언트도 기존 `MinioConfig`의 환경 자격 증명 예외 처리와 IAM fallback을 사용하도록 수정한다. mode·region 검증을 공유하며 로컬 MinIO 인증 방식은 유지한다. 정적 키 없이 웹 자격 증명으로 실제 multipart 시작 요청을 서명하는 회귀 테스트와 기존 MinIO multipart 통합 테스트를 포함해 로컬 888개 테스트가 통과했다. [PR CI](https://github.com/FruitionKR/Fruition-document/actions/runs/35615870225)도 정확한 PR HEAD에서 성공했다. 배포 검증의 단계·HTTP 상태 보고는 [Platform PR #26](https://github.com/FruitionKR/Fruition-flatform/pull/26)에서 보강했다.

이번 수정에는 추가 DB 변경이 없다. 운영에 이미 적용된 V50의 `expand-only` 검토를 유지하고 Flyway 이력을 재검증한다. [Document PR #8](https://github.com/FruitionKR/Fruition-document/pull/8)의 V50 리허설은 합성 큐 1,000행의 구버전 INSERT·claim·기본값과 논리 복원 checksum 확인 범위이며 운영 전체 DB/PITR 검증을 뜻하지 않는다. [이전 CPU 릴리스 검토](c6f2a97396549f271c91fa29a1dce780d5404dff-validation.md)의 CPU/OCR 이미지 검사와 디스크 절감 근거는 유지된다.

main CI와 네 이미지 게시가 성공하고 manifest·소스·digest가 일치한 뒤 배포한다. converter 선행 rollout, 기존 인증된 문서·AI 검증과 65MiB/11페이지 PDF의 multipart 완료 재호출·Range 읽기·두 묶음 변환·AI 완료를 모두 확인한 후 프런트엔드를 활성화한다. 실제 2GiB 초과 PDF 전체 처리 검증은 이 smoke 범위에 포함되지 않는다.
