# 프론트엔드 접근 코드 제거 릴리스 검토

- 릴리스: `54e34e0898d4acda25a62ee80cc858b243604dcc`
- 프론트엔드 main: `1854967015da181c7460e77fcdc3438347049e70` ([PR #323](https://github.com/FruitionKR/Fruition-frontend/pull/323)).
- [main CI](https://github.com/FruitionKR/Fruition-frontend/actions/runs/43448168906)의 테스트·프로덕션 빌드 성공을 확인했다.
- 이전 성공 릴리스 `cfbf263f212ac74861f09650cd45a192c091db92`와 소스·빌드 입력을 대조했다. 프론트엔드만 변경되며 Access·Document·pipeline·converter는 기존 빌드 입력을 재사용한다.
- DB 변경은 없어 `migration_mode=none`이다. 기존 [복원 검토](https://github.com/FruitionKR/Fruition-flatform/pull/202)를 같은 백엔드 이미지에 한해 재사용한다. 이번 작업에서 별도의 DB 복원 시험을 새로 수행한 것은 아니다.
- 복구 후보는 이전 성공 릴리스이며 실제 DB fingerprint가 같을 때 기존 rollback gate를 사용한다.
- WAF 접근 코드 제한은 선행 작업으로 제거됐다. 이번 릴리스는 화면·middleware의 접근 코드 입력 및 검사를 제거한다.
- 배포 후 rollout·인증 업무 smoke·PDF smoke 결과는 Deploy (EKS) 실행 기록에서 확인한다.
