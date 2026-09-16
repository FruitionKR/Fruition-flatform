# 실검증 결과

기준일 2026-08-07. 컨테이너 스택(access-svc·document-svc·pipeline·ingest-worker·kafka·redis·postgres·minio)으로 실측.

## 서비스 분리

| 항목 | 결과 |
|---|---|
| 코드 경계 강제 | `document-svc`에 `import fruition.access` 0건, `access-svc`에 `import fruition.core` 0건 |
| 테스트 | access-svc 108 + document-svc 435, 실패 0 |
| 이미지 빌드 | access-svc·document-svc bootJar + Docker 이미지 빌드 성공 |
| 라우팅 | 로그인·워크스페이스 → :8081(access), 문서·query → :8080(document) 200 |
| 내부 API | access→document 초기노트(커밋 후 호출, FK 위반 해소, 노트 1개 생성), document→access 권한 조회 |

## 장애 격리 (핵심 — 문서 §5.2)

access-svc 강제 정지 상태에서:

| 요청 | 결과 | 해석 |
|---|---|---|
| 로그인(access) | 000 (연결 불가) | access 담당 기능만 중단 — 정상 |
| 문서 조회(document) | 200 | Redis projection warm 캐시로 access 없이 인가 |
| 문서 업로드(document) | 201 | 〃 |

캐시 miss(cold) 상태에서 access 다운 시에는 fail-closed 404 — 안전 측 실패 확인.

## Kafka 비동기 (유실 0)

| 항목 | 결과 |
|---|---|
| ingest 발행 | document-svc가 `ai.ingest.command`(key=workspace_id) 발행, run_id 자체 생성 |
| worker 소비 | ingest-worker consumer group join(12 partition), 소비·실행 |
| **유실 검증** | worker 정지 중 발행 → Kafka lag 대기 → 기동 후 소비 → lag 0 |

## 내부 인증·격리

| 항목 | 결과 |
|---|---|
| pipeline 무토큰 | 401 (fail-closed) |
| pipeline 포트 | 127.0.0.1 바인딩 (호스트 외부 차단) |
| 내부 콜백 무토큰 | 401 (X-Internal-Token 상수시간 검증) |

## K8s (kind)

전 pod Ready, 가입·로그인 스모크, pod 강제 삭제 자가 복구, NetworkPolicy 시행(외부 namespace에서 pipeline 차단), KEDA ScaledObject Ready.

## 알려진 한계

- LLM 최종 답변 생성은 외부 LLM API 키 무효로 실패(구조 무관 — 키 갱신 필요)
- 초기 노트는 best-effort(access→document 실패 시 워크스페이스 생성은 성공)
- projection은 TTL 300s 캐시 — access 장기 다운 시 캐시 만료 후 fail-closed
