#!/usr/bin/env bash
set -Eeuo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$ROOT_DIR/scripts/lib/runtime.sh"
java21_home="$(find_java21_home)" || {
  printf '[back-test] ERROR: Java 21을 찾지 못했습니다. JAVA_HOME_21을 지정하세요.\n' >&2
  exit 1
}
# 첫 인자는 서비스 폴더명이다. 생략하면 두 독립 프로젝트를 검사한다.
services=(Access Document)
if [[ $# -gt 0 ]]; then
  case "$1" in
    Access|Document) services=("$1"); shift ;;
    *) printf '사용법: scripts/back-test.sh [Access|Document] [Gradle 인자...]\n' >&2; exit 2 ;;
  esac
fi
if [[ $# -eq 0 ]]; then set -- test --no-daemon; fi
for service in "${services[@]}"; do
  (cd "$ROOT_DIR/../$service"
   JAVA_HOME="$java21_home" ./gradlew "$@" -Porg.gradle.java.installations.paths="$java21_home")
done
