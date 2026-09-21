# 대용량 PDF CPU 이미지 재배포 검토

대상 릴리스: `5ae196495ad79831bad2ad81df8f740fe40ded35`

## 소스

- FruitionKR/Fruition-access: `b73cf750a312383057dad366ee5827868a0c9354`
- FruitionKR/Fruition-ai: `ffd8037062d11f7147fd41e8692515e01a3a9c5a`
- FruitionKR/Fruition-document: `c4152ec27b96c42b0d5f9ad3739fae57c1a62b18`

## 재배포 배경

대용량 PDF 기능의 첫 [운영 배포](https://github.com/FruitionKR/Fruition-flatform/actions/runs/35582927074)는 converter 선행 교체 단계에서 중단됐다. CUDA/cuDNN 라이브러리를 포함한 이미지의 압축 해제가 CPU 노드의 20GiB 디스크를 소진했다. 기존 converter template을 복원해 서비스는 유지했고, 임시 이미지 파일 정리 후 디스크 압박이 해제됐다. 다른 애플리케이션 교체와 프런트엔드 활성화는 진행하지 않았다.

[AI PR #13](https://github.com/FruitionKR/Fruition-ai/pull/13)은 공식 CPU wheel의 torch/torchvision 버전을 고정하고 GPU 패키지 혼입을 금지한다. 의존성 해석 CI와 실제 이미지 빌드에서 CPU 빌드 여부, torchvision 연산, OCR 모듈 및 converter/복원 CLI import를 검사한다. 이 검사를 통과한 게시 이미지로만 재배포한다.

## DB와 기존 기능 검증

첫 배포에서 Document V50이 운영 DB에 적용됐다. 이번 재배포에도 `expand-only` 검토를 사용하며 Flyway가 이미 적용된 V50을 재적용하지 않고 이력을 검증한다. 새 CPU 수정에는 추가 DB 변경이 없다. V50 컬럼을 제거하지 않으며, 이전 성공 릴리스의 schema fingerprint와 달라 일반 rollback 조건은 충족하지 않는다.

[Document PR #8](https://github.com/FruitionKR/Fruition-document/pull/8)의 886개 시험과 실제 PostgreSQL V1–V50 실행, MinIO multipart 복사·완료 재호출 검증은 유지된다. 같은 PR의 공개 V50 리허설은 합성 변환 큐 1,000행의 기본값·구버전 INSERT·claim 및 stale 복구 쿼리·논리 복원 checksum을 확인한 범위이며, 운영 전체 DB/PITR 검증을 의미하지 않는다.

원래 대용량 PDF 기능 및 agent 재전달 수정의 근거는 [AI PR #11](https://github.com/FruitionKR/Fruition-ai/pull/11), converter 선행 교체와 실제 PDF 검증 절차는 [Platform PR #22](https://github.com/FruitionKR/Fruition-flatform/pull/22)에서 확인한다.

## 완료 조건

네 이미지의 소스와 digest를 확인한 뒤 `action=deploy`를 실행한다. converter가 준비된 후 문서·AI 서비스를 교체하고 기존 로그인·문서 저장·AI ingest 검증을 통과해야 한다. 이후 65MiB/11페이지 PDF의 multipart 완료 재호출, 원본 Range 읽기, 두 묶음 변환과 AI 완료를 검증한다. 해당 PDF 검증 성공 뒤 프런트엔드를 활성화한다.

실제 2GiB 초과 PDF 전체 OCR·AI 완료는 이 smoke 검증 범위 밖이다. 원본 Range 읽기와 입력 분할 회귀 검증을 실제 대용량 문서 전체 처리 완료로 표현하지 않는다.

CPU 수정 PR의 [CI](https://github.com/FruitionKR/Fruition-ai/actions/runs/35585103062)가 통과했다. converter 시험 13개와 Linux CPU 의존성 해석 검사를 포함한다. 실제 게시 이미지의 runtime 검사는 이미지 빌드 성공을 통해 확인하며, 이 문서 작성 시 운영 재배포 완료를 주장하지 않는다.
