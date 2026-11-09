# 2026-11-06 릴리스 배포 검토 (라우팅 단어 판정과 채팅 탭 문서 질문 되돌리기)

릴리스: `9b21325b709cac46dadedd0d8ea0c8b8478fc669`. 마지막 성공 배포는 `61ab1888f8b62abe171978f09e16540847b9517c`이다.

## 소스

- AI `45b328a58940bd136e8e9aadafc084afbc41cbd1`: [PR237](https://github.com/FruitionKR/Fruition-ai/pull/237). #236 단어 판정과 `mode=chat` 되돌리기, #234 백필 스크립트(실행 안 함).
- Document `c327c61a10fc68b75c8897bb1f8ec72224e7f41f`: [PR223](https://github.com/FruitionKR/Fruition-document/pull/223). #222 `mode=chat` 되돌리기, #220 멈춘 실행 정리 SQL(실행 안 함).
- Frontend `e67034643cb81a5ad64da759ddef127412d3c792`: #247 채팅 탭 문서 칩과 옮기기 버튼 되돌리기.
- Access `e590bb57`: 운영과 같다. 이미지 재사용.
- Platform: k8s 변경 없음.

`migration_mode`는 `none`이다.

## 받아들인 회귀 (사용자 결정)

- 자동 승인을 켜면 작업 탭의 "이 문서 요약해 줘"가 원문을 요약본으로 덮어쓴다. 로그 화면 롤백으로 되돌린다.
- "요약해서 저장해 줘"도 새 문서가 아니라 원문 수정이다.
- 첨부 여러 개 수정이 불안정해진다. `attached_edit_instruction`은 복원하지 않았다. 로컬에서 첨부 3개 요청이 1회 실패, 1회 1개만 저장됐다.
- 채팅 탭은 다시 위키 질의만 한다. 문서 첨부 질문은 작업 탭에서 한다.

## 배포 순서와 겹치는 구간 (`scripts/aws_deploy.py`, 코드로 읽음)

교체 순서는 converter → access-svc(변경 없음) → document-svc → pipeline-api → 나머지(frontend, AI worker) 동시다. PR이 권장한 프론트 → AI → document와 **반대다.** 묶음 배포에는 부분 배포가 없어 받아들인다.

| 구간 | 일어나는 일 | 문서 영향 |
|---|---|---|
| 새 document + 옛 프론트 | 채팅 탭의 `mode=chat` agent turn이 400. 채팅 탭 문서 질문이 시작되지 않는다. 옛 탭을 열어 둔 사용자는 새로고침 전까지 같다 | 없음 |
| 옛 document Pod가 남은 동안 들어간 `mode=chat` 턴 | 옛 worker가 처리해도 결과가 새 document의 `AiTaskResultApplier`에 닿으면 `agent_result_request_mismatch`로 실패할 수 있다. 적용 표의 문서가 비어 있고 대조 분기가 사라졌기 때문이다 | 없음 |
| 그 턴을 새 worker가 받음 | `mode: Literal["task"]` 검증 실패로 그 턴만 실패한다 | 없음 |
| 새 프론트 + 옛 agent worker | 작업 탭 질문이 `chat_tab_question`으로 되돌아올 수 있는데 옮기기 버튼이 없다. frontend와 worker가 같이 바뀌어 짧다 | 없음 |

구간은 지난 배포 기준 수 분이다. 재현하지 않았다. 배포 직전 진행 중 실행은 0건이다(07:38 UTC).

## 첫 document 기동

30일 지난 휴지통은 07:38 UTC 기준 0건이다. `scrubOrphans`의 대상도 지난 실행으로 비었다. 진행 중 실행의 변경 기록 11행은 남는다.

## 시험

- 시험 기록: https://github.com/FruitionKR/Fruition-flatform/issues/162
- 복원 시험은 스키마가 같아 [issue 158](https://github.com/FruitionKR/Fruition-flatform/issues/158)을 재사용한다. 새 격리 시험은 돌리지 않았다.
- 로컬 실서버 기록(`local/revert-20261106`)은 묶음과 파일 차이가 0이다. 라우팅 평가 287/306(이전 263/306). **Jev는 돌리지 않았다.** 운영도 키가 비어 있다.

## 시험하지 않은 것과 위험

- 옛·새 Pod 공존 구간은 코드로만 읽었다.
- 스키마가 같아 이전 이미지로 rollback은 가능할 수 있으나 실행해 보지 않았다.

이 파일은 배포 성공 증명이 아니다.
