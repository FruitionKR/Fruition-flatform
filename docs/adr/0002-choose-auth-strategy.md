# ADR-0002: 인증·인가 전략 — JWT 로컬 검증 + Redis 권한 projection

- 상태: 채택 (실검증 완료 — access-svc 정지 중 문서 기능 유지 확인)
- 관련: [architecture.md](../architecture.md) §3

## 맥락

인증(access-svc)과 문서 기능(document-svc)이 분리되면서, 매 요청마다 access-svc를 호출하면 동기 결합·단일 장애점이 된다. 워크스페이스 멤버십 검사는 document-svc의 거의 모든 요청 경로에 존재한다.

## 결정

1. **JWT 로컬 검증**: HS256 공유 시크릿, iss·aud 검증. 각 서비스가 access-svc 호출 없이 토큰 자체 검증. 발급·검증 코드는 각 서비스의 `fruition.shared` 패키지에서 소유한다([저장소 분리 결정](0019-independent-service-repositories.md)).
2. **권한은 Redis projection**: `authz:role:{wid}:{uid}` (TTL 300s). access-svc가 멤버십 변경 시 write-through/무효화. document-svc는 hit 시 즉시 판정, miss 시만 access-svc 내부 API 호출(connect 2s/read 3s) 후 캐시.
3. **fail-closed**: projection miss + access-svc 호출 실패 → 404 (WorkspaceNotFoundException). 권한을 임의로 열지 않는다.
4. **내부 API 인증**: X-Internal-Token 상수시간 비교. 무토큰 401.

## 대안과 기각 사유

- **매 요청 access-svc 동기 호출**: access 다운 = 전 기능 다운. 기각.
- **RS256 + JWKS**: 시크릿 공유 제거 가능하나 키 배포·회전 인프라 필요. 소규모 초대 사용자 profile에선 과잉 — 외부 공개 시점에 전환 (트리거 명시, architecture.md §7).
- **멤버십 DB 직접 읽기(공유 DB)**: 데이터 소유권 침식. ADR-0001과 모순. 기각.

## 결과

- access-svc 강제 정지 실측: warm 캐시 문서 조회 200·업로드 201, 로그인만 중단. cold 캐시는 fail-closed 404 (안전 측 실패).
- 트레이드오프: 권한 변경 전파 최대 300s 지연(TTL) — write-through로 통상 즉시 반영.
- `JWT_SECRET`·`INTERNAL_CALLBACK_TOKEN`은 배포 시 두 앱 동일 값 필수.
