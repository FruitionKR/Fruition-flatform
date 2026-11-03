#!/usr/bin/env bash
# Local scripts never inherit the production project token. Opt in explicitly.
local_analytics_env() {
  local source_dir="$1"
  export ANALYTICS_ENABLED="${LOCAL_ANALYTICS_ENABLED:-false}"
  export ANALYTICS_ENVIRONMENT=local
  export POSTHOG_PROJECT_TOKEN="${LOCAL_POSTHOG_PROJECT_TOKEN:-}"
  export POSTHOG_HOST="${LOCAL_POSTHOG_HOST:-http://127.0.0.1:18080}"
  APP_VERSION="$(git -C "$source_dir" rev-parse HEAD)" || return 1
  export APP_VERSION
  case "$ANALYTICS_ENABLED" in
    true|false) ;;
    *) printf 'LOCAL_ANALYTICS_ENABLED must be true or false\n' >&2; return 1 ;;
  esac
}
