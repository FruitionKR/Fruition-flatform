# AI ingest 잠금 수정 릴리스 검증

대상 릴리스: `5a7940f19c4bec95b7006b8ea7ee158d0bce6245`

이전 배포는 이미지 rollout과 S3 문서 저장을 통과했지만 AI ingest 완료 검증에서 실패했다. 같은 실행이 최종화와 저장 단계에서 서로 다른 PostgreSQL 연결로 동일 workspace 잠금을 중복 획득하며 60초 후 timeout이 발생했다. [AI PR #10](https://github.com/FruitionKR/Fruition-ai/pull/10)은 같은 스레드·DB·workspace·run의 중첩 호출만 이미 보유한 잠금을 재사용한다. 다른 worker나 run은 기존 PostgreSQL 잠금을 계속 획득해야 한다.

## 회귀 검증

- 기존 코드가 실제 PostgreSQL 중첩 잠금 회귀 시험에 실패함을 재현했다.
- 수정 후 단위 시험 6개와 실제 PostgreSQL 시험 4개가 통과했다. 중첩 scope 종료 후 바깥 잠금 유지, 다른 스레드의 같은 run 경쟁, 다른 run의 잠금 경쟁, 예외 이후 해제를 확인했다.
- 전체 AI 시험은 1,265 passed, 24 skipped, 170 subtests passed였다. 기존 document restoration 제외 조건은 유지하며 새 PostgreSQL 시험 4개는 생략하지 않았다.
- CI에 PostgreSQL 16 시험 서비스를 추가했고 [main CI](https://github.com/FruitionKR/Fruition-ai/actions/runs/35515713646)가 통과했다.

## DB 변경과 복원 근거

Access와 Document는 직전 배포와 같은 소스이며, AI 수정에도 SQL 마이그레이션이나 DB 스키마 변경이 없다. 운영 세 DB의 schema fingerprint가 직전 배포 이후 동일함을 read-only preflight로 확인했다. Document V49는 앞선 배포에서 이미 적용됐다. 따라서 이번 검토는 `migration_mode=none`이다.

복원 근거는 같은 날 수행한 [이전 릴리스 검증 PR #16](https://github.com/FruitionKR/Fruition-flatform/pull/16)의 V49 적용 후 세 DB, 93개 테이블 논리 복원·schema·전체 행 비교 결과를 사용한다. 이번 잠금 수정 뒤 별도 복원 시험을 다시 실행한 것으로 표시하지 않는다. 해당 시험은 격리 PostgreSQL 16.14이며 운영 RDS 16.13 snapshot/PITR 복원은 검증 범위 밖이다.

## 실제 이미지 검증

2026-09-20에 새 pipeline digest로 임시 Kubernetes Job을 실행했다. 실제 pipeline ServiceAccount와 AI runtime DB 연결을 사용해 운영 RDS에서 다음 항목을 확인했다.

- 같은 workspace·run의 중첩 잠금 호출이 timeout 없이 완료됐다.
- 독립된 DB 연결은 안쪽 scope 종료 뒤에도 바깥 scope가 보유한 잠금을 얻지 못했다.
- 바깥 scope 종료 후 독립 연결이 잠금을 얻을 수 있었다.
- 중첩 scope에서 예외가 발생한 뒤에도 잠금이 해제됐다.
- Job 성공 및 `NESTED_LOCK_OWNERSHIP_AND_EXCEPTION_RELEASE_PASS`를 확인했다.

고유한 시험용 advisory lock만 사용했으며 업무 행·스키마·앱 Deployment는 변경하지 않았다. 임시 Job과 NetworkPolicy는 삭제했다. 새 배포 manifest의 render와 검증도 통과했다.

[네 이미지 게시](https://github.com/FruitionKR/Fruition-flatform/actions/runs/35516021765)가 성공했고 manifest 식별자와 네 ECR digest 일치를 확인했다.

| 이미지 | digest |
| --- | --- |
| converter | `sha256:0779df09092659dc19cebb7ad356c8f7aac11e8956846a596e1c1895b9682ad6` |
| document-svc | `sha256:f01852c11eecfd1fac2e7241f510eacef602b44f25d4d7492f5bd04c7a013c94` |
| pipeline | `sha256:6638b6de3e2682231da536630f0acec92d77ab3479fabf7cf04f697a66c0a3b2` |
| access-svc | `sha256:f090f8ec98df7953dc590de94668cf2aa2c563fcb353f0ba42195f5bed9c8dee` |

## 배포 조건

`action=deploy`를 사용하며 bootstrap 및 health 복구 옵션은 모두 끈다. 배포 후 로그인 → 문서 생성·조회 → 외부 LLM을 사용하는 AI ingest 완료 → 시험 문서 삭제가 모두 통과해야 성공 릴리스를 기록한다. 배포 전 잠금 시험을 전체 ingest 성공으로 간주하지 않는다.

아직 성공 릴리스 기록이 없어 기존 성공 SHA로 자동 rollback할 수 없다. 실패 시 bootstrap 이력을 삭제하거나 DB를 되돌리지 않고 실패 단계에 맞는 호환 수정으로 진행한다.

앞서 노드 디스크 압박으로 발생한 failed_nodes 경보는 OK로 복귀했고 사전 확인에서 노드 6대 모두 Ready, DiskPressure=false였다. 20GiB 노드 한 대의 여유 공간이 약 3.6GiB여서 rollout 중 디스크 상태를 별도로 관찰한다.
