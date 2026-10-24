# 백엔드 Java 보안 배포 검토

릴리스: `df7d4744f7c8d452e40d9b4b71a1c38ba46ca1c5`

- Access PR51·52, Document PR164·165에서 빌드 JDK·운영 JRE를 Temurin 21.0.13+9로 업데이트했다. Docker Hub 태그 게시 지연 때문에 공식 배포 파일의 고정 SHA-256을 검증해 설치한다.
- main push 전체 테스트와 bootJar: https://github.com/FruitionKR/Fruition-access/actions/runs/40093897597, https://github.com/FruitionKR/Fruition-document/actions/runs/40094217874.
- 두 서비스 로컬 Docker 빌드와 Java 실행 확인을 통과했다. 런타임 신뢰 저장소에 emSign ECC G3와 AAA Certificate Services 인증서가 없는지 확인했다.
- 이전 성공 릴리스 `9b8626717358908f4efb45f626e464ebc4aa5021`에서 Access·Document의 Dockerfile, CI, 변경 이력만 바뀌었다. API·DB migration·애플리케이션 의존성 변경은 없다. frontend·pipeline·converter 이미지 digest는 이전 릴리스와 동일하다.
- DB 복원 시험은 동일 스키마에 대한 https://github.com/FruitionKR/Fruition-flatform/pull/107 의 기존 복원·migration 리허설 근거를 재사용한다. 새 복원 시험을 수행했다는 뜻은 아니다.
- 기존 DB preflight, rollout, 업무 smoke, PDF smoke gate를 모두 적용한다. 배포 후 Pod imageID와 게시 digest를 대조하고 이미지의 Java release·신뢰 저장소를 확인한다.
- 이번 작업은 Java 보안 업데이트이며 전체 전이 의존성의 취약점 부재를 보증하지 않는다.

## fruition.wiki 도메인 전환

- 사용자가 후이즈 네임서버 변경을 완료했고 `.wiki` 상위 DNS, Google·Cloudflare DNS에서 Route53 위임을 확인했다.
- 서울 ACM에서 `fruition.wiki`, `*.fruition.wiki` 인증서를 발급(ISSUED)하고 기존 ALB HTTPS listener에 추가했다. DNS 검증 CNAME은 자동 갱신을 위해 유지한다.
- Route53에 루트·api·access 호스트의 ALB Alias A 레코드를 등록한다. 배포 config의 app_domain/domain을 fruition.wiki로 바꾸고 새 인증서를 지정한다.
- 기존 renderer가 Ingress 호스트, CORS, OAuth 완료 후 이동 주소, 초대 링크를 새 도메인으로 생성한다. 프론트엔드는 상대 경로 API/OAuth 시작 주소를 사용하므로 이미지 변경이 필요 없다.
- WAF 접근 코드 규칙은 전환 동안 기존·새 화면 호스트 모두에 적용한다. S3 CORS에 새 origin을 추가하고 기존 origin을 유지한다. 접근 코드 및 로그인 쿠키는 새 도메인에서 다시 입력해야 한다.
- Google/네이버/카카오 개발자 콘솔의 redirect URI 등록은 별도 계정 권한이 필요하다. 각각 https://fruition.wiki/login/oauth2/code/google, /naver, /kakao를 등록해야 하며 콘솔 반영 확인 전 소셜 로그인 전체 완료로 판단하지 않는다.
- 새 주소의 HTTPS, 화면·일반 로그인/API, 파일 업로드 smoke, 내부 경로 차단을 확인한다. 이전 호스트의 Ingress 라우팅은 새 호스트로 교체된다.
- 이번 배포 이전의 성공 릴리스로 되돌릴 때는 저장된 이전 배포 config도 함께 복원한다. DNS·WAF·S3 설정 백업은 운영자 로컬 작업 디렉터리에 보관한다.
