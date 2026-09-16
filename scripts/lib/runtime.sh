#!/usr/bin/env bash

java_home_version() {
  local java_home="$1"
  [[ -x "$java_home/bin/java" ]] || return 1
  "$java_home/bin/java" -version 2>&1 | head -n 1 | grep -Eq 'version "21\.|openjdk version "21\.'
}

find_java21_home() {
  local candidate

  for candidate in "${JAVA_HOME_21:-}" "${JAVA_HOME:-}"; do
    if [[ -n "$candidate" ]] && java_home_version "$candidate"; then
      printf '%s\n' "$candidate"
      return
    fi
  done

  if command -v /usr/libexec/java_home >/dev/null 2>&1; then
    candidate="$(/usr/libexec/java_home -v 21 2>/dev/null || true)"
    if [[ -n "$candidate" ]] && java_home_version "$candidate"; then
      printf '%s\n' "$candidate"
      return
    fi
  fi

  local common_paths=(
    "/opt/homebrew/opt/openjdk@21/libexec/openjdk.jdk/Contents/Home"
    "/usr/local/opt/openjdk@21/libexec/openjdk.jdk/Contents/Home"
    "/Library/Java/JavaVirtualMachines/temurin-21.jdk/Contents/Home"
    "/usr/lib/jvm/temurin-21-jdk-amd64"
    "/usr/lib/jvm/java-21-openjdk"
    "/usr/lib/jvm/java-21-openjdk-amd64"
  )

  for candidate in "${common_paths[@]}"; do
    if [[ -d "$candidate" ]] && java_home_version "$candidate"; then
      printf '%s\n' "$candidate"
      return
    fi
  done

  return 1
}

runtime_pid_file() {
  local name="$1"
  printf '%s/%s.pid\n' "$RUNTIME_DIR" "$name"
}

runtime_port_in_use() {
  local port="$1"

  if command -v lsof >/dev/null 2>&1; then
    lsof -tiTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1
    return
  fi
  if command -v nc >/dev/null 2>&1; then
    nc -z 127.0.0.1 "$port" >/dev/null 2>&1
    return
  fi
  curl --silent --output /dev/null --connect-timeout 1 "http://127.0.0.1:$port/" >/dev/null 2>&1
}

runtime_process_matches() {
  local pid="$1"
  local owner_script="$2"
  local command

  [[ "$pid" =~ ^[0-9]+$ ]] || return 1
  kill -0 "$pid" >/dev/null 2>&1 || return 1
  command="$(ps -p "$pid" -o command= 2>/dev/null || true)"
  [[ "$command" == *"$owner_script"* ]]
}

runtime_is_running() {
  local name="$1"
  local owner_script="$2"
  local file pid

  file="$(runtime_pid_file "$name")"
  [[ -f "$file" ]] || return 1
  read -r pid < "$file" || true

  if runtime_process_matches "$pid" "$owner_script"; then
    return 0
  fi

  rm -f "$file"
  return 1
}

runtime_register() {
  local name="$1"
  local owner_script="$2"
  local file

  if runtime_is_running "$name" "$owner_script"; then
    return 1
  fi

  mkdir -p "$RUNTIME_DIR"
  file="$(runtime_pid_file "$name")"
  printf '%s\n' "$$" > "$file"
}

runtime_unregister() {
  local name="$1"
  local file pid

  file="$(runtime_pid_file "$name")"
  [[ -f "$file" ]] || return 0
  read -r pid < "$file" || true
  if [[ "$pid" == "$$" ]]; then
    rm -f "$file"
  fi
}

runtime_descendant_pids() {
  local pid="$1"
  local child_pid

  while IFS= read -r child_pid; do
    [[ -n "$child_pid" ]] || continue
    printf '%s\n' "$child_pid"
    runtime_descendant_pids "$child_pid"
  done < <(ps -axo pid=,ppid= | awk -v parent="$pid" '$2 == parent { print $1 }')
}

runtime_terminate_tree() {
  local pid="$1"
  local process_pid
  local -a process_pids remaining_pids

  [[ "$pid" =~ ^[0-9]+$ ]] || return 0
  process_pids=("$pid")
  while IFS= read -r process_pid; do
    [[ -n "$process_pid" ]] && process_pids+=("$process_pid")
  done < <(runtime_descendant_pids "$pid")

  kill -TERM "${process_pids[@]}" >/dev/null 2>&1 || true
  for _ in $(seq 1 50); do
    remaining_pids=()
    for process_pid in "${process_pids[@]}"; do
      kill -0 "$process_pid" >/dev/null 2>&1 && remaining_pids+=("$process_pid")
    done
    [[ ${#remaining_pids[@]} -eq 0 ]] && return 0
    sleep 0.2
  done

  kill -KILL "${remaining_pids[@]}" >/dev/null 2>&1 || true
  for _ in $(seq 1 10); do
    for process_pid in "${remaining_pids[@]}"; do
      if kill -0 "$process_pid" >/dev/null 2>&1; then
        sleep 0.1
        continue 2
      fi
    done
    return 0
  done
  return 1
}

runtime_stop() {
  local name="$1"
  local owner_script="$2"
  local label="$3"
  local prefix="$4"
  local file pid

  file="$(runtime_pid_file "$name")"
  if ! runtime_is_running "$name" "$owner_script"; then
    printf '[%s] 관리 중인 %s 프로세스가 없습니다.\n' "$prefix" "$label"
    return 0
  fi

  read -r pid < "$file"
  printf '[%s] %s supervisor를 종료합니다: PID %s\n' "$prefix" "$label" "$pid"
  if runtime_terminate_tree "$pid"; then
    rm -f "$file"
    return 0
  fi

  printf '[%s] ERROR: %s 프로세스 트리가 종료되지 않았습니다: PID %s\n' "$prefix" "$label" "$pid" >&2
  return 1
}
