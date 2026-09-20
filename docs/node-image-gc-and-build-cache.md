# 노드 이미지 정리와 CI 빌드 캐시

## 확인한 현상

2026-09-20 배포 시간대 노드에서 `EvictionThresholdMet`의 ephemeral-storage 회수 이벤트가 발생했다. 이전 converter 이미지가 남아 있던 20GiB 노드의 여유 공간은 약 3.6GiB였다. 당시 실행 Pod가 사용하지 않았다는 점은 확인했지만 종료 컨테이너 참조 여부와 kubelet 내부 정리 실패 여부까지 확인한 것은 아니다.

실제 kubelet configz는 이미지 정리 high=85%, low=80%, minimum age=2m, maximum age=0s였다. 따라서 오래된 미사용 이미지도 용량 임계값에 도달하기 전에는 남을 수 있었다. 3.6GiB 여유라는 한 시점의 수치만으로 그 시점에 DiskPressure가 있었다고 해석하지 않는다.

별도로 AI Spot 그룹의 AZ 균형 조정 중 용량 부족(UnfulfillableCapacity/InsufficientInstanceCapacity)과 노드 교체 기록도 확인했다. 디스크 정리만으로 Spot 수급이나 모든 노드 경보가 해결되지는 않는다.

## 변경

AL2023 nodeadm NodeConfig를 통해 kubelet high=70%, low=60%, maximum age=24h를 설정한다. 최소 보관 시간·실행 컨테이너 참조 판단은 kubelet에 맡긴다. 외부 prune cron/privileged DaemonSet은 추가하지 않는다. 80GiB 증설 초안은 제거했고 디스크 용량은 유지한다.

24시간은 kubelet이 추적한 미사용 시간이며 kubelet 재시작 시 추적 시간이 초기화된다. GC는 주기적으로 실행되므로 다운로드 순간의 공간 부족을 완전히 막지는 못한다. 적용 후 configz와 디스크 가용 공간, ImageGCFailed/FreeDiskSpaceFailed/DiskPressure를 확인하고 부족하면 이미지 크기와 디스크 증설을 추가 검토한다.

기존 노드에는 자동 소급되지 않아 launch template 업데이트 및 노드 순차 교체가 필요하다. 각 그룹의 max_unavailable=1이며 두 그룹 동시 적용 시 그룹별 한 대씩 교체될 수 있다. Kafka·worker 단일 replica는 교체 중 일시 중단될 수 있어 적용 창을 정해야 한다. 강제 drain이나 PDB 우회는 하지 않는다.

## 캐시

CI cache는 GitHub hosted runner의 서비스별 BuildKit 레이어 캐시다. 운영 노드의 이미지 캐시·ECR 릴리스 보존 정책과 별개다. 공식 Docker action이 GHA cache 인증을 처리하고 `version=2`, 서비스별 scope, `mode=max`, export timeout=2m, ignore-error=true를 사용한다. 캐시 저장 장애만 허용하며 빌드·push·digest 검증 실패는 게시를 차단한다.

재시도에서 동일 릴리스 태그가 있으면 재빌드하지 않는다. 서로 다른 릴리스 간 이미지 digest 재사용은 이번 범위가 아니다. 변경된 Dockerfile/소스는 BuildKit 캐시 키에 반영된다. `RUN --mount=type=cache` 내용 자체의 외부 보존을 보장하지는 않는다. 최초 캐시 채우기는 느릴 수 있고 실제 시간 절감은 후속 실행에서 확인해야 한다.

근거: [Kubernetes GC](https://v1-35.docs.kubernetes.io/docs/concepts/architecture/garbage-collection/), [Docker GHA cache](https://docs.docker.com/build/cache/backends/gha/).
