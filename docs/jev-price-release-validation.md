# Jev 단가 V108 배포 검토 (2026-11-07)

예상 묶음: `3367322f9b35b03f10c52281f0386aa9afe7d91e`. Document main은 `a8eff3d7ed9b267de0f3d4446132973d8658e4b8`이며 다른 세 저장소 source는 기존 `77aab0c3` 묶음과 같다. 실제 게시 manifest도 이 값과 대조해야 한다. main CI·게시·스냅샷·배포는 이 기록 초안 작성 시 아직 완료되지 않았으며 완료로 표시하지 않는다.

## 변경 범위

[Fruition-document #225](https://github.com/FruitionKR/Fruition-document/pull/225)의 V108은 기존 `ai_model_prices`에 `typesafe/jev-1.13.0` 한 행을 추가한다. 테이블/컬럼/API/AI 모델 및 라우팅은 바꾸지 않는다. 적용 시각은 2026-11-07 00:00 UTC이며 같은 날 최초 호출 04:02:54 UTC 이전이다. 기존 `unpriced`를 자동 재계산하는 변경임을 알고 배포한다.

입력 단가 $0.042/100만 토큰은 [공식 홈페이지](https://typesafe.ai/)의 $42/10억 토큰과 같다. 상세 공식 가격표는 미확인이고 [OpenRouter](https://openrouter.ai/typesafe/jev-1.13), [eesel](https://www.eesel.ai/blog/typesafe-jev-pricing), [Zuplo](https://zuplo.com/docs/ai-gateway/jev)의 출력 무료 표기가 일치한다. 캐시 0은 현재 미사용 필드의 NOT NULL 충족값으로, 공급사의 캐시 무료 정책을 입증하지 않는다. 운영 읽기 집계의 캐시 읽기·쓰기 합계는 0이었다.

변경 PR 전체 CI: https://github.com/FruitionKR/Fruition-document/actions/runs/42339843070 (success). 릴리스 PR: https://github.com/FruitionKR/Fruition-document/pull/226.

## CI 간헐 실패 기록

dev push 최초 실행(https://github.com/FruitionKR/Fruition-document/actions/runs/42340265996)은 2,047개 중 `SourceStoreOutsideTransactionIntegrationTest.storedSourceIsDeletedWhenExecutionFails` 1개가 `UnfinishedStubbingException`으로 실패했다. 같은 HEAD 릴리스 PR CI는 통과했다. 공유 mock·스케줄러 스레드 경쟁은 원인 후보이나 추측이며 확인되지 않았다. 사용자 지시로 동일 HEAD dev CI를 한 번 재실행해 attempt 2가 통과했다. 테스트 코드는 수정하지 않았다.

## 실제 수행한 시험

- Java 21·Colima의 Testcontainers DB에서 `AiModelCatalogPriceIntegrationTest`, `UsageChargeServiceIntegrationTest`, `CreditServiceIntegrationTest` 총 53개 통과, 실패/스킵 0. Flyway 전체 마이그레이션이 새 테스트 DB에 적용됐다.
- 별도의 임시 PostgreSQL 16 컨테이너에서 저장소 V59/V65로 기존 가격 스키마를 만든 뒤 V108 파일 자체를 실행했다. Jev 1행·입력 0.042·출력 0을 확인했다.
- 같은 V108 파일을 다시 실행해 여전히 1행이고 기존 별도 모델 fixture의 가격이 그대로임을 확인했다. 이 컨테이너는 제거했다.
- 전체 운영 복제 DB 업그레이드, 이전/새 앱의 로그인·문서·AI 업무 흐름을 교차 실행한 시험, 새 RDS 복원 시험은 이번 변경에서 수행하지 않았다. 위 시험을 그러한 시험으로 표시하지 않는다.
- 기존 [복원 기록 #158](https://github.com/FruitionKR/Fruition-flatform/issues/158)은 기존 증거로만 참조한다. 이번 변경의 신규 복원 시험은 아니다.

## 재계산과 사용자 영향

`UsageChargeService.recompute`는 앱 시작 180초 뒤 처음 실행하고 이후 기본 1시간 간격으로 최근 90일 미산정 행을 처리한다. 호출 `started_at`에 적용되는 가격/환율/정책을 선택한다. `charged` 행은 바꾸지 않는다. 처리 커밋 뒤 `CreditService.settle`이 누적 청구액 중 기존 차감액과의 차이만 차감한다.

운영 `BILLING_ENFORCE=false`를 읽기 확인했다. 이 설정은 잔액 부족 요청의 차단을 끄지만 크레딧 차감은 끄지 않는다. 사전 관찰 28건의 예상 원가는 호출별 올림 합계 $0.002959, 사용자 금액은 환율·버퍼·마진·VAT를 적용한 6.651원이다. 이후 호출이 생기면 총 영향은 늘 수 있다. 직접 운영 쓰기 쿼리나 수동 재계산은 하지 않는다.

`ai_price_missing` 경보는 로그 Sum >=1, 86,400초 한 구간, missing=notBreaching이다. 경고가 더 나오지 않고 기존 경고가 평가 구간을 벗어난 뒤 OK가 될 수 있으며 재계산 직후 OK를 보장하지 않는다.

## 배포 확인 범위

변경은 데이터 추가형이므로 migration_mode는 expand-only다. 소스와 이미지 digest 대조, 배포 전 두 DB 스냅샷 available 확인, 배포 workflow의 기존 migration·rollout·smoke 게이트를 그대로 사용한다. 배포 뒤 V108 성공·가격 행, 자동 재계산 전후 건수/금액, 크레딧 정산, 재시작·ALB 5xx를 읽기 확인한다. 실패 시 임의 재실행·롤백은 하지 않는다.
