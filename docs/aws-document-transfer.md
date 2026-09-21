# 대용량 PDF 업로드·변환·AI 처리

## 처리 경로

Vercel은 화면·로그인·접근 코드 확인을 담당한다. `BACKEND_URL`이 설정된 빌드에서는 문서 API 요청이 해당 AWS origin으로 직접 전달되고, 인증 갱신은 기존 동일 출처 `/api/auth/refresh`를 사용한다. `/api/document-transport`는 접근 코드 middleware 뒤에서 연결 설정만 제공한다. 문서 서버는 Bearer 토큰과 workspace 권한을 계속 검증한다.

`BACKEND_URL`이 설정된 빌드에서는 직접 업로드가 기본 활성화되며, `DOCUMENT_DIRECT_UPLOAD_ENABLED=false`를 명시한 경우에만 비활성화된다. 활성화 상태에서 PDF는 시작 → 조각 URL 발급 → S3 multipart PUT → 완료 확인 순서로 업로드한다. 기본 64MiB 조각을 동시에 최대 3개 전송한다. 큰 파일은 10,000개 파트 이내가 되도록 조각 크기를 늘린다. Java `long`과 브라우저 Blob.slice를 사용하며 SDK 호환 상한은 파일당 5TiB다. 이는 저장 경로의 상한이며 그 크기의 모든 PDF를 OCR 처리할 수 있다는 보장은 아니다.

각 조각은 최대 3회 시도하며 재시도 시 URL을 갱신한다. 업로드 티켓은 24시간, 조각 URL은 15분 유효하다. 탭 새로고침 후 업로드 재개는 아직 지원하지 않는다. 완료 요청은 같은 멱등 키를 재사용한다. 서버는 파트 번호·크기, 최종 크기·MIME·PDF 헤더, 사용자·workspace를 검증하고 특정 객체 버전/ETag를 고정해 S3 내부에서 원본 경로로 복사한다. PDF 식별값은 multipart ETag와 크기의 SHA-256이며 원본 바이트 전체 SHA-256은 아니다. 편집 Markdown의 본문 SHA-256 계약은 유지한다.

PDF 미리보기는 인증 후 발급한 1시간짜리 S3 GET URL을 사용한다. 브라우저 PDF 뷰어가 Range 요청을 사용할 수 있으며, 프런트엔드가 전체 파일을 Blob으로 복제하지 않는다.

## 변환과 AI

AWS 변환은 `/convert-source-batch`에 원본 URL·크기·완료 페이지 번호만 전달한다. converter는 승인된 S3 HTTPS 호스트에서 1MiB Range로 읽으며 16MiB 캐시를 사용한다. 원본 전체를 JVM이나 converter 임시 디스크에 내려받지 않는다. 기본 10페이지씩 추출하여 기존 PDF 복원 엔진에 전달한다. `PDF_PAGES_PER_BATCH`는 1~50, `PDF_BATCH_CONCURRENCY` 기본값은 1이다.

V50 migration의 `document_convert_queue`에 완료 페이지, 전체 페이지, 시도 횟수와 heartbeat를 저장한다. 실패하면 완료한 묶음 다음부터 자동 재시도하며 총 3회 실패하면 실패 상태를 남긴다. 처리 중 heartbeat가 10분 이상 끊긴 작업은 회수한다. 페이지 묶음마다 읽기 URL을 새로 발급한다.

변환 Markdown의 PNG/JPEG/GIF data URI는 별도 S3 asset으로 저장한다. 본문은 UTF-8 기준 최대 64KiB 문서로 나누어 기존 AI 큐에 등록한다. 첫 문서는 변환 placeholder를 사용하고 나머지는 `origin=convert_part`, `source_document_id=첫 문서 ID`로 연결한다. AI packet 실행은 설정된 worker 수만큼만 대기/실행하여 전체 packet future를 한꺼번에 생성하지 않는다. PDF 변환 완료 후 각 분할 문서의 AI 처리가 시작된다.

전체 파일 크기 제한과 작업별 메모리 제한은 별개다. 단일 PDF 객체 읽기에는 64MiB 방어 한도가 있고, 암호화·손상 PDF, 매우 큰 단일 페이지/이미지, LLM 제공자 토큰·호출 제한은 별도 오류가 될 수 있다. 페이지 추출 시 PDF parser 메타데이터와 페이지 리소스 메모리도 필요하다. 64KiB는 문서 입력 단위이며 모델의 모든 prompt/output 토큰 한도를 대체하지 않는다. 일반 Markdown 편집 한도는 유지된다. 기존 로컬 `/convert` multipart 경로의 50MiB 제한도 유지되며 AWS 대용량 경로에는 적용되지 않는다.

## 배포 순서

1. S3 CORS에 실제 프런트엔드 HTTPS origin을 `document_upload_allowed_origins`로 등록한다. PUT/GET/HEAD 및 Range를 허용한다. 문서 IRSA에 임시 prefix 읽기/쓰기와 GetObjectVersion을 추가한다. 공개 버킷으로 변경하지 않는다.
2. converter에 pypdf 의존성과 새 API를 배포한다. `CONVERTER_SOURCE_HOSTS`는 현재 리전 S3 endpoint와 해당 버킷 hostname만 등록한다.
3. 문서 DB V50 migration을 적용한 후 document-svc를 배포한다. 기존 converter보다 먼저 새 문서 서버를 배포하지 않는다.
4. 프런트엔드에서 `BACKEND_URL=https://api.example.com`(실제 API origin)으로 빌드/배포한다. 직접 업로드는 기본 활성화이므로 `DOCUMENT_DIRECT_UPLOAD_ENABLED=true`를 별도로 지정할 필요가 없다. API CORS에 프런트엔드 origin이 포함되어 있어야 한다.
5. deploy workflow는 `deploy` 액션에서만 배포 성공 후 `scripts/aws_pdf_smoke.py`를 실행한다. 검증 계정으로 65MiB 합성 PDF의 multipart 업로드·완료 재호출·Range 읽기·11페이지 분할 변환·AI 완료를 확인하고 테스트 문서만 정리한다. 실제 계정의 편집 충돌 확인은 별도로 수행한다.

임시 객체/미완료 multipart는 7일 lifecycle로 회수한다. 버전 관리 버킷의 임시 이전 버전도 만료한다. 새 경로를 중지할 때는 frontend에 `DOCUMENT_DIRECT_UPLOAD_ENABLED=false`를 명시하고 재배포한다. 이는 기존 경로의 크기 제한도 다시 적용한다. V50은 추가 컬럼 migration이므로 롤백 시 데이터를 제거할 필요가 없다.

현재 인프라 상태에는 다른 브랜치의 요청 기반 기동 구성이 있으므로 이 작업을 적용할 때 전체 Terraform apply를 실행하지 않는다. CORS, storage lifecycle, document storage IAM만 대상으로 plan을 검토한다. `.local/aws/document-direct-upload.tfplan`은 변경 후 반드시 다시 생성한다.

## 검증 범위

- 실제 MinIO 통합: 65MiB를 64MiB+1MiB로 업로드, 서버 내부 복사, 완료 재호출.
- 가상 3GiB 파일: 브라우저 파트 offset·동시 3개·만료 URL 재발급.
- 유효 PDF를 3GiB sparse 원본으로 구성한 Range 테스트: 실제 pypdf 파서로 전체 다운로드 없이 끝 페이지 추출. OCR 엔진은 이 테스트에서 mock이다.
- 체크포인트 10페이지 이후 재개, 실패 시 checkpoint 유지, 문서 분할·AI 큐 등록, UTF-8 복원.
- 프런트엔드 빌드, 인증 갱신·편집 충돌·이름 중복 회귀, 문서 API 및 DB migration/OpenAPI 통합 테스트.

실제 수 GiB PDF 전체 OCR·LLM 처리와 운영 배포 후 end-to-end 검증은 별도로 수행해야 한다.
