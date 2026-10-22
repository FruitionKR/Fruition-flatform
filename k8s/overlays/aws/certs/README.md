# RDS 신뢰 인증서

`rds-ca-bundle.pem`은 2026-10-22에 가져온 AWS 공식 서울 리전 공개 CA 묶음이다.

출처: https://truststore.pki.rds.amazonaws.com/ap-northeast-2/ap-northeast-2-bundle.pem

개인키가 아닌 공개 신뢰 루트이며 `fruition-rds-ca` ConfigMap의 `root.crt`로 마운트한다.
교체 시 공식 출처와 유효기간을 확인하고 실제 DB 연결 및 잘못된 호스트명 거부를 검증한다.
