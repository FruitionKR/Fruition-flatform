# 2026-11-07 릴리스 배포 검토 (AI 실패 코드와 문구, Jev 키 반영)

릴리스: `a377209ef0d7ef2ac918aee26bc117704c9880ee`. 마지막 성공 배포는 `9b21325b709cac46dadedd0d8ea0c8b8478fc669`이다.

## 소스

- Document `235a45fd7ac44af4e670abee14a379f19e2480eb`: [PR224](https://github.com/FruitionKR/Fruition-document/pull/224). #221 실패 코드별 문구.
- AI `6710c43d60d6afa725ca4412e73995a6628cb4a8`: [PR239](https://github.com/FruitionKR/Fruition-ai/pull/239). #235 실패 코드 세분화.
- Frontend `e6703464`, Access `e590bb57`: 운영과 같다. 이미지 재사용.
- Platform: k8s 변경 없음.

`migration_mode`는 `none`이다.

## 이 배포로 달라지는 것

1. **Jev 경로가 실제로 돈다.** `TYPESAFE_API_KEY` 값이 02:59:40 UTC에 Secret으로 동기화됐고, pipeline 이미지 교체로 새 파드가 그 값을 받는다. 라우팅, 근거 선택, 개념 병합, Skill 의도, 폴더 조회, 편집 세부 분류 6개 경로다. `typesafe` 사용 기록은 지금까지 0건이고, 키를 넣고 시험한 기록이 없다. 잠긴 평가 287/306은 대체 라우터 기준이라 이 경로에 적용되지 않는다. 실패하면 코드상 기존 경로로 대체한다.
2. **첫 document 기동 때 30일 지난 휴지통 문서 3건이 영구 삭제된다**(03:04 UTC 기준). 되돌릴 수 없다.
3. 실패 문구가 코드별로 바뀐다. 화면에 나오는 코드만 해당한다.

## 교체 구간

교체 순서는 converter → document-svc → pipeline-api → AI worker다. frontend와 access는 교체되지 않는다. #221 본문의 권장 순서와 같다. document가 먼저 뜬 구간에는 옛 AI가 기존 코드를 보내 기존 문구 또는 접두사 기본 문구가 나간다.

## 시험

- 시험 기록: https://github.com/FruitionKR/Fruition-flatform/issues/164
- 복원 시험은 스키마가 같아 [issue 158](https://github.com/FruitionKR/Fruition-flatform/issues/158)을 재사용한다. 새 격리 시험은 돌리지 않았다.
- PR CI와 병합된 main CI가 모두 통과했다.

## 시험하지 않은 것과 위험

- Jev 경로의 운영 동작과 비용. 배포 뒤 `ai_model_usage`의 `typesafe` 행과 `[Jev ... 대체]` 로그로 본다.
- 첨부 여러 개 수정과 자동 승인 요약 회귀는 이전 릴리스에서 받아들인 상태 그대로다.
- 스키마가 같아 이전 이미지로 rollback은 가능할 수 있으나 실행해 보지 않았다. 영구 삭제는 되돌리지 못한다.

이 파일은 배포 성공 증명이 아니다.
