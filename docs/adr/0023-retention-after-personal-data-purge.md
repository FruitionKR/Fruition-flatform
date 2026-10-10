# ADR-0023: 개인정보 파기 후 잔존 데이터 보관 기간

상태: 승인됨. 아래 기간은 개인정보 처리방침에 반영해야 하며 법무 검토 후 바뀔 수 있다.

## 맥락

탈퇴·워크스페이스 파기·영구 삭제는 애플리케이션이 DB 행과 S3 객체를 지우는 것으로 끝나지 않는다. 다음 세 곳에 데이터가 남는다.

- S3 storage 버킷은 버전 관리가 켜져 있다. 삭제 코드(document `DataPurgeService`, ai `postgres_purge.py`)는 versionId 없이 지우므로 delete marker만 생기고 이전 버전은 기한 없이 남는다. 이전 버전 만료 규칙은 `tmp/`에만 있었다. (Fruition-flatform#71)
- AI 실행 로그 `pipeline-runs/{run_id}/pipeline.log`는 AI role에 삭제 권한이 없어 파기 때 지울 수 없다. 로그에는 단계·ID·개수·소요 시간·오류 문자열만 있고 문서 본문은 없다. (#72)
- Kafka AI command·event 토픽에는 질문 원문과 최근 대화가 들어 있고, `retention.ms`가 없어 브로커 기본값 7일 동안 남는다. (#73)

## 결정

1. **S3 이전 버전은 30일 보관한다.** 버전 관리는 유지하고, 전체 prefix(`filter {}`)에 `noncurrent_version_expiration` 30일과 `expired_object_delete_marker`를 건다. `tmp/`는 기존 `expire-tmp` 규칙(7일)이 더 짧아 먼저 적용된다. S3는 겹치는 규칙의 동작을 각각 평가하고 먼저 도래하는 만료를 실행한다.
2. **AI 실행 로그는 사용자별로 지우지 않고 `pipeline-runs/` prefix 30일 lifecycle로 만료한다.** AI role의 삭제 권한은 늘리지 않는다. 이전 버전은 1번 규칙이 정리한다.
3. **document role에 `meetings/*` 쓰기·삭제를 추가한다.** 녹음 업로드와 파기가 둘 다 필요하다.
4. **AI command·event Kafka 토픽의 `retention.ms`를 72시간(259200000)으로 한다.**

## 대안과 기각 사유

- 버전 관리 해제: document 직접 업로드가 versionId에 의존해 업로드가 깨진다.
- 앱 코드에서 `DeleteObjectVersion`: `s3:DeleteObjectVersion` 권한과 버전 열거 코드가 서비스마다 늘고 권한 범위가 커진다.
- AI role에 로그 삭제 권한 부여: 로그에 문서 본문이 없고 기간 만료로 충분해 최소 권한을 유지한다. 보관 기간 기반 정리는 일반적인 관행이다.
- Kafka 24시간: 하루를 넘는 worker 장애에서 메시지를 잃는다. 7일: 개인정보를 더 오래 보관한다.

## 결과

- 파기 후에도 S3 이전 버전·AI 로그는 최대 30일, Kafka 메시지는 최대 72시간 남는다. 개인정보 처리방침의 보관 항목에 적어야 한다.
- 로그 보관 30일 이내에는 파기한 사용자의 실행 ID·오류 문자열이 남을 수 있다.
- 적용하려면 `terraform apply`와 Kafka 토픽 배포가 필요하다.
