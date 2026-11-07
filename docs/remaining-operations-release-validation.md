# 크레딧 안내·계획 항목 실패 이유 배포 검토 (2026-11-07)

## 변경과 데이터 호환성

- document: 충전 UI가 없으므로 크레딧 부족 안내에서 충전을 제거한다. Agent 시작 전 실패와 진행 중 중단의 문서 상태 안내를 구분한다. 예약·차감·한도·BILLING_ENFORCE는 변경하지 않는다.
- frontend: 실제 AgentRun operations의 error_code에 따라 기존 카드의 실패 이유를 구분한다. 코드 원문과 내부 식별자는 노출하지 않는다. 기존 문서 수정·폴더 정리 경로를 사용하고 모바일 행의 긴 문구를 줄바꿈한다.
- 테스트만 변경: 원본 저장은 공유 Spring spy 대신 테스트 로컬 위임 mock을 사용한다. 음성 합성은 별도 테스트 DB와 자체 수집기 주기 실행 해제로 대기열 생산자/소비자 경쟁을 분리한다.
- DB 마이그레이션·API·AI 라우팅·인프라 설정 변경 없음. migration_mode는 none이다. 첨부 턴 Jev 라우팅과 502 관련 타임아웃은 변경하지 않는다.

## 실제 검증 범위

- frontend: 최종 로컬 전체 2102개 테스트·타입 검사·lint·빌드 통과. 실제 카드 정적 렌더 fixture를 Chromium 1440/390 폭에서 확인해 실패 이유 3행·가로 넘침 0·pageerror 0을 확인했다. 운영 전체 앱 동선 시험은 아니다.
- document: 원본 저장 3개·오류 문구 14개·크레딧 26개 로컬 통과. 음성 합성 클래스는 25개씩 별도 실행 3회 모두 통과했다. 전체 Testcontainers는 GitHub CI로 확인한다.
- 최초 로컬 document 전체 검사에서 변경된 문구 기대값 3개를 발견해 수정했다. 다음 검사에서 #213의 동일 음성 테스트가 대기열 존재 대기에서 실패했다. 공유 DB의 다른 수집기가 행을 소비할 수 있다는 코드상 경합을 제거했으며 실제 실패 당시 소비 주체는 미확인이다. 재시도 설정이나 Disabled는 추가하지 않았다.
- frontend 초기 로컬 main 검증의 타입 실패는 설치된 fflate와 lock 버전 불일치였다. npm ci 후 통과했으며 압축 코드는 변경하지 않았다. 폴더 정리의 이전 권한·충돌 문구 기대값은 이번 변경에 맞춰 수정했고 다른 검증은 유지했다.
- 이번 작업에서 별도 RDS 복원·운영 복제 DB 구/신 앱 교차 업무 시험은 수행하지 않았다. 기존 복원 기록 https://github.com/FruitionKR/Fruition-flatform/issues/158 은 이전 증거로만 참조한다.

## 502 조사 결론

14일 ALB 502는 6건이며 조사 대상 이전 5건이다. 04:25:55 UTC 해당 요청은 target HTTP 응답 없이 ALB 502였고 동일 document 파드가 전후 유지됐으며 재시작은 0이었다. 주변 autoscaler 로그에 노드 제거·축출 근거는 없었다. ALB idle timeout은 120초이고 대상 런타임 keep-alive 및 TCP 패킷은 확보하지 못했다. 연결 재사용 중 종료는 원인 후보일 뿐 확정하지 않는다. 설정은 수정하지 않는다.

## 운영 확인 계획

게시 manifest의 sources와 이미지 digest를 대조하고 두 RDS 배포 전 스냅샷 available을 확인한다. deploy.yml의 기존 smoke·rollout·대형 PDF 게이트를 유지한다. 실행 한 건만 사용자 지시로 feedback 승인하며 배포 실패 시 재실행·롤백하지 않는다. 배포 후 실제 digest·재시작·ALB 5xx·ai_price_missing·문서 건수를 읽기 확인한다.

## 최종 소스 및 CI

게시된 묶음 ID: `2a0121a5cb745ed36876b636c625af0e95b5fdbb`. 게시 manifest가 위 소스 및 계산한 묶음 ID와 일치함을 확인했다. document-svc·frontend digest만 변경됐고 나머지 세 이미지는 이전 digest 그대로다.

| 저장소 | main source | 근거 |
|---|---|---|
| document | 92c12a3ba55e310b45005cf8eebb989e30732ad4 | [변경 #227](https://github.com/FruitionKR/Fruition-document/pull/227), [릴리스 #228](https://github.com/FruitionKR/Fruition-document/pull/228) |
| frontend | ac9b625c074adc0e83c306a3a73f8935cdf955f0 | [변경 #248](https://github.com/FruitionKR/Fruition-frontend/pull/248) |
| access | e590bb57b2056c318473306e8de7d3ab85067f10 | 이전 성공 묶음과 동일 |
| AI | 6710c43d60d6afa725ca4412e73995a6628cb4a8 | 이전 성공 묶음과 동일 |

- document 변경 PR 전체 CI [42347137055](https://github.com/FruitionKR/Fruition-document/actions/runs/42347137055) attempt 1·2 모두 success. 첫 성공 뒤 사용자 지시에 따라 반복 검증했다.
- document dev push [42347971067](https://github.com/FruitionKR/Fruition-document/actions/runs/42347971067), 릴리스 PR [42347991237](https://github.com/FruitionKR/Fruition-document/actions/runs/42347991237), main [42348379301](https://github.com/FruitionKR/Fruition-document/actions/runs/42348379301) 모두 success.
- frontend 변경 PR [42347051737](https://github.com/FruitionKR/Fruition-frontend/actions/runs/42347051737) attempt 1·2, main [42347540479](https://github.com/FruitionKR/Fruition-frontend/actions/runs/42347540479) 모두 success.
- 두 RDS 스냅샷 `pre-2a0121a5-fruition-core-20261107`, `pre-2a0121a5-fruition-access-20261107` available 확인. 배포 전 살아 있는 문서 366개, 전체 651개, Jev 사용량 52건 모두 charged.

게시 성공: https://github.com/FruitionKR/Fruition-flatform/actions/runs/42348795953 . 배포 전 검토 시점이며 배포 성공으로 표시하지 않는다.
