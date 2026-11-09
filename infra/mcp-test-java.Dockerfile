ARG BASE_IMAGE=eclipse-temurin:21-jre
FROM ${BASE_IMAGE}
COPY --chown=10001:10001 *.jar /app/app.jar
