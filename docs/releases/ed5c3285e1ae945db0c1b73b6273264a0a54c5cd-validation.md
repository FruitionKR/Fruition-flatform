# S3 multipart 완료 XML 수정 릴리스 검토

대상 릴리스: `ed5c3285e1ae945db0c1b73b6273264a0a54c5cd`

- Access: `b73cf750a312383057dad366ee5827868a0c9354`
- Document: `67b8b89489cd28acc7399def1925953bc2575d37`
- AI: `c6a03083e22dadae10d99a148c6e43408b46caae`

직전 [운영 배포](https://github.com/FruitionKR/Fruition-flatform/actions/runs/35617295213)는 전체 rollout과 인증된 Markdown 저장·AI 처리 검증을 통과했다. IAM fallback 수정으로 PDF multipart 시작과 파트 PUT도 성공했지만 완료 단계에서 S3가 `MalformedXML`을 반환했다. MinIO SDK의 조회 응답 `Part`를 그대로 재사용하면서 `Size`·`LastModified`가 완료 XML에 포함된 것이 원인이다. [AWS 완료 요청 스키마](https://docs.aws.amazon.com/AmazonS3/latest/API/API_CompleteMultipartUpload.html)는 이 조회용 필드를 허용하지 않는다.

[Document PR #11](https://github.com/FruitionKR/Fruition-document/pull/11)은 완료 시 파트 번호·ETag만 가진 새 `Part`를 구성한다. 완료 전 크기·개수·순서 검사는 조회 원본으로 유지한다. 실제 SDK의 ListParts 역직렬화와 완료 요청 XML을 검사하는 회귀 테스트를 추가했으며, 구 방식에는 잘못된 필드가 포함됨도 대조했다. 로컬 889개 테스트와 bootJar, 정확한 PR HEAD의 [CI](https://github.com/FruitionKR/Fruition-document/actions/runs/35619042149)가 통과했다.

추가 DB 변경은 없다. 이미 적용된 V50의 expand-only 호환·복원 근거는 [이전 릴리스 검토](efaf1a8bbfe3e4754840bb84243090ff46bc7a02-validation.md)를 따른다. main CI와 네 이미지 게시 성공, manifest의 소스·recipe·digest 확인 후 배포한다.

## 별도 운영 변환 검증

직전 릴리스의 실제 converter HTTP `/convert-source-batch`에 합성 65MiB·11페이지 PDF의 서명된 S3 URL을 전달했다. Range 읽기로 1–10페이지(993 Markdown 문자, `done=false`)와 11페이지(101문자, `done=true`) 변환이 모두 성공했다. 검증에 생성한 S3 객체의 정확한 버전을 삭제했다. 이 검증은 Document multipart 완료나 AI ingest 성공을 의미하지 않는다.

## 활성화 조건

이번 릴리스 배포 후 기존 문서·AI 검증과 전체 PDF 검증을 다시 실행한다. 65MiB multipart 완료 및 멱등 재호출, 원본 Range 읽기, 두 묶음 변환, 각 문서의 AI 완료와 테스트 문서 정리까지 통과한 뒤 프런트엔드를 활성화한다. 실제 2GiB 초과 PDF 전체 OCR·AI 처리는 이 smoke 범위 밖이다.
