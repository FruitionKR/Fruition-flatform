# PostHog 기존 설치 전환 검증 기록

대상 이미지 release는 `bc90ee595728f60defc3cf45517af33903ff4ddf`다.
사용자는 점검 중단과 기존 데이터 손실을 허용했다. 정상 migration으로 보존할 수 있는 데이터는 유지한다.
이 문서는 관찰 결과와 전환 정책을 구분한다. 운영 전환 완료 여부는 마지막 배포 결과로 판단한다.

## 소스와 실제 이미지

- Frontend main `b48c17873ffdf8b79482c55ba316e0470291d712`, PR 205.
- Access main `5ae401c62433bd90e205d6628ca84fd96f910ac3`, PR 49.
- Document main `8ef360641b5f85d49e33c3695d3229fed549926a`, PR 160.
- AI main `949f2e5b949a65a2529929228d43afbc1db59c74`, PR 134.
- Platform 점검 전환 PR 103, Strimzi controller 식별 보완 PR 106 모두 main 병합 및 CI 통과.
- [게시 실행](https://github.com/FruitionKR/Fruition-flatform/actions/runs/39782673427)이 성공했고, 게시 manifest와 5개 ECR digest를 별도 검증했다.
- [이미지 release](https://github.com/FruitionKR/Fruition-flatform/releases/tag/images-bc90ee595728f60defc3cf45517af33903ff4ddf)의 원본 OCI index와 linux/amd64 child/config/blob SHA256을 대조했다. 리허설은 그 child 이미지를 사용했다.
- 운영 hotfix의 실제 Pod imageID 12개를 수집했다. 과거 성공 release의 이미지와 같다고 가정하지 않는다.
- 유지할 이전 성공 release: `e84181aec2630da3ec870e5f3496059fda1c1b70`.
  immutable record의 data 전체 canonical SHA256: `fe73d08ac8d0588bd077415eff12d3aa099e31dbcc6fc7fafd24fdbecd3c25d7`.

## 로컬 실제 PostHog 검증

별도 합성 계정과 workspace를 사용해 실제 프로젝트 676020의 US 수집기로 전달했다. environment는 local이다.
수집기 HTTP 성공과 outbox sent를 확인했고 실제 PostHog 이벤트 화면에서도 수신을 확인했다.

| 시나리오 | 결과 |
| --- | --- |
| 유효 PDF multipart 업로드·1쪽 변환 | 성공 이벤트와 처리 결과 확인 |
| 잘못된 PDF | 실제 parser 실패, validation 분류, 실패 문서/부모 상태와 단일 이벤트 확인 |
| 초대·가입 | 초대 재발급, 구 토큰 거부, 다른 이메일 거부, 수락 반복의 멱등성 확인 |
| 채팅 내보내기 | saved/skipped, export ID 중복 방지, 최신 export와 ingest 연결 확인 |
| 변경 복원 | preview·실제 execute·operation 완료 확인 |
| 질의 실패 | 실제 embedding 서비스 중단으로 실패시킨 뒤 복구, answered 오발행과 취소 이벤트 배제 확인 |
| 수집 실패·재시도 | 최초 503에도 제품 요청 성공, 이후 실제 수집기로 재전송, UUID/timestamp/payload 일치 |
| 브라우저 보조 이벤트 | 실제 UI에서 restore_previewed·chat_export_started의 실제 수집 성공 |
| 개인정보·식별 | 본문/제목/이메일/비밀번호 제외, UUID와 사용자/workspace 연결 확인 |

오류 PDF가 실패 상태로 끝나지 않던 transaction flush 문제와, 전체 테스트가 실제 로컬 Kafka를 공유하던 문제는 Document PR 161에서 수정했다. 실제 실패 입력의 자동 복구와 remote 전체 CI를 확인했다.

## 큐와 중단 정책

점검 전 읽기 전용 조사 결과, ingest/query/agent/maintenance command 각각 12개 파티션 모두 committed offset과 end offset이 같았다. 총 lag는 0이며, 조사 과정에서 join/poll/commit을 실행하지 않았다.
`ai_task_runs`에는 convert 6건과 skill_author 17건의 legacy running 상태가 남아 있었다. 활성 resume claim은 0이고 마지막 갱신은 각각 10월 11일과 10월 7일이다. 새 scheduler가 자동 재개하는 상태는 cancel_requested/rolling_back이며 이 23건을 새 명령으로 재발행하지 않는다. 상태 행은 정상 migration의 보존 대상이고, 과거 실패 작업의 완료를 주장하지 않는다.
기존 PDF queue 3건은 모두 failed다. 재처리가 필요하면 새 제품 요청을 사용하며 구 command를 임의 replay하지 않는다.
namespace CronJob과 active Job은 0이었다. 점검 중에는 모든 앱 Deployment 12개를 중지하고 KEDA ScaledObject 4개/HPA 7개를 제거한다. Kafka와 검토한 두 Strimzi controller는 유지한다.
요청 기반 wake Lambda는 nodegroup을 깨우는 역할이며 앱 replica나 DB를 변경하지 않는다. 외부 DB writer가 없는지는 실제 quiescent DB preflight로 다시 검사한다.

## 운영 전환 절차와 복구 한계

기존 WAF·인증서·접근 로그 설정을 보존한 ALB fixed 503 응답을 먼저 적용하고 공개 HTTPS 세 경로 및 TargetGroupBinding 제거를 확인한다. 앱 Pod 종료 후 현재 이미지를 동일 digest로 고정하며 실제 before fingerprint가 검토와 같을 때만 기존 main 배포 workflow를 실행한다.
마이그레이션 순서는 Access → AI → Document다. 실제 게시 이미지의 production entrypoint를 사용하고, 리허설 after fingerprint와 일치해야 새 앱을 시작한다. DB reset/repair/baseline/clean, 과거 성공 기록 삭제, initial-install 재사용은 하지 않는다.
성공 후 인증 업무 smoke와 대용량 PDF gate, PostHog 운영 수집을 검증하고 target manifest의 scaler를 복구한다. 중간 실패 시 503과 앱 중단을 유지하며 시작/실패 감사 기록을 지워 재시도하지 않는다.
논리 복원은 RDS PITR 또는 S3 객체 버전 복원을 입증하지 않는다. 운영 재해 복구의 RTO를 보장하지 않으며, 사용자가 허용한 기존 데이터/객체/큐 손실 범위 안에서 검증한 논리 복원과 정상 전환을 사용한다. 실제 운영 배포 결과는 workflow 실행으로 별도 기록한다.
