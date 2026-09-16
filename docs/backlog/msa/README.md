# Fruition MSA 현행 구조

이 폴더는 **현재 코드에 실제로 반영된 MSA 구조**를 설명한다. 목표·설계 근거는 상위 문서를 따른다:

- 목표 구조 확정안: [`../Fruition_AWS_MSA_Architecture.md`](../Fruition_AWS_MSA_Architecture.md) (Vercel·EKS·Strimzi/MSK Kafka·KEDA)
- 전환 근거·단계·장애 격리 원칙: [`../backlog/Fruition_MSA_Proposal_revised.md`](../../../../docs/backlog/backlog/Fruition_MSA_Proposal_revised.md)

문서 목록:
- [`current-architecture.md`](current-architecture.md) — 서비스 경계·요청 흐름·데이터 소유
- [`deployment.md`](deployment.md) — 로컬(compose)·kind(K8s) 실행과 AWS 매핑
- [`verification.md`](verification.md) — 실검증 항목과 결과

> 기준일: 2026-08-07. 변경 이력은 `docs/changelog/{backend,ai,infra,frontend}.md`.
