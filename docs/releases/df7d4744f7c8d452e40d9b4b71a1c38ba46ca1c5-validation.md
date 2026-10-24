# 백엔드 Java 보안 배포 검토

릴리스: `df7d4744f7c8d452e40d9b4b71a1c38ba46ca1c5`

- Access PR51·52, Document PR164·165에서 빌드 JDK·운영 JRE를 Temurin 21.0.13+9로 업데이트했다. Docker Hub 태그 게시 지연 때문에 공식 배포 파일의 고정 SHA-256을 검증해 설치한다.
- main push 전체 테스트와 bootJar: https://github.com/FruitionKR/Fruition-access/actions/runs/40093897597, https://github.com/FruitionKR/Fruition-document/actions/runs/40094217874.
- 두 서비스 로컬 Docker 빌드와 Java 실행 확인을 통과했다. 런타임 신뢰 저장소에 emSign ECC G3와 AAA Certificate Services 인증서가 없는지 확인했다.
- 이전 성공 릴리스 `9b8626717358908f4efb45f626e464ebc4aa5021`에서 Access·Document의 Dockerfile, CI, 변경 이력만 바뀌었다. API·DB migration·애플리케이션 의존성 변경은 없다. frontend·pipeline·converter 이미지 digest는 이전 릴리스와 동일하다.
- DB 복원 시험은 동일 스키마에 대한 https://github.com/FruitionKR/Fruition-flatform/pull/107 의 기존 복원·migration 리허설 근거를 재사용한다. 새 복원 시험을 수행했다는 뜻은 아니다.
- 기존 DB preflight, rollout, 업무 smoke, PDF smoke gate를 모두 적용한다. 배포 후 Pod imageID와 게시 digest를 대조하고 이미지의 Java release·신뢰 저장소를 확인한다.
- 이번 작업은 Java 보안 업데이트이며 전체 전이 의존성의 취약점 부재를 보증하지 않는다.
