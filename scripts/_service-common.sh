#!/usr/bin/env bash
# Sourced by run-backend.sh / run-celery.sh / run-frontend.sh / stop-celery.sh.
# Provides nohup background start, pid-file based stop, status, and restart.

minerva_scripts_dir() {
  cd "$(dirname "${BASH_SOURCE[0]}")" && pwd
}

minerva_repo_root() {
  cd "$(minerva_scripts_dir)/.." && pwd
}

minerva_run_dir() {
  local root
  root="$(minerva_repo_root)"
  echo "${MINERVA_RUN_DIR:-${root}/.minerva/run}"
}

minerva_service_log_dir() {
  local root
  root="$(minerva_repo_root)"
  echo "${MINERVA_SERVICE_LOG_DIR:-${root}/.minerva/logs}"
}

minerva_service_slug() {
  echo "$1" | tr ' /:' '---'
}

minerva_service_pid_file() {
  local name=$1
  local run_dir
  run_dir="$(minerva_run_dir)"
  mkdir -p "${run_dir}"
  echo "${run_dir}/$(minerva_service_slug "${name}").pid"
}

minerva_service_log_file() {
  local name=$1
  local log_dir
  log_dir="$(minerva_service_log_dir)"
  mkdir -p "${log_dir}"
  echo "${log_dir}/$(minerva_service_slug "${name}").log"
}

minerva_service_running() {
  local name=$1
  local pid_file pid

  pid_file="$(minerva_service_pid_file "${name}")"
  [[ -f "${pid_file}" ]] || return 1
  pid="$(<"${pid_file}")"
  [[ -n "${pid}" ]] && kill -0 "${pid}" 2>/dev/null
}

minerva_kill_tree() {
  local pid=$1
  local wait_sec=${2:-10}
  local pgid i

  [[ -n "${pid}" ]] || return 0
  if ! kill -0 "${pid}" 2>/dev/null; then
    return 0
  fi

  pgid="$(ps -o pgid= -p "${pid}" 2>/dev/null | tr -d ' ' || true)"
  if [[ -n "${pgid}" && "${pgid}" != "$$" ]]; then
    kill -TERM "-${pgid}" 2>/dev/null || kill -TERM "${pid}" 2>/dev/null || true
  else
    kill -TERM "${pid}" 2>/dev/null || true
  fi

  for ((i = 0; i < wait_sec * 2; i++)); do
    if ! kill -0 "${pid}" 2>/dev/null; then
      return 0
    fi
    sleep 0.5
  done

  if [[ -n "${pgid}" && "${pgid}" != "$$" ]]; then
    kill -KILL "-${pgid}" 2>/dev/null || kill -KILL "${pid}" 2>/dev/null || true
  else
    kill -KILL "${pid}" 2>/dev/null || true
  fi
}

minerva_service_start() {
  local name=$1
  shift
  local pid_file log_file pid

  pid_file="$(minerva_service_pid_file "${name}")"
  log_file="$(minerva_service_log_file "${name}")"

  if minerva_service_running "${name}"; then
    pid="$(<"${pid_file}")"
    echo "[${name}] already running (pid ${pid})"
    return 0
  fi
  [[ -f "${pid_file}" ]] && rm -f "${pid_file}"

  echo "[${name}] starting -> log: ${log_file}"
  if command -v setsid >/dev/null 2>&1; then
    setsid nohup "$@" >>"${log_file}" 2>&1 &
  else
    nohup "$@" >>"${log_file}" 2>&1 &
  fi
  pid=$!
  echo "${pid}" >"${pid_file}"
  sleep 0.5
  if kill -0 "${pid}" 2>/dev/null; then
    echo "[${name}] started pid=${pid}"
    return 0
  fi
  echo "[${name}] failed to start, see ${log_file}" >&2
  rm -f "${pid_file}"
  return 1
}

minerva_service_stop() {
  local name=$1
  local pid_file pid

  pid_file="$(minerva_service_pid_file "${name}")"
  if [[ ! -f "${pid_file}" ]]; then
    echo "[${name}] not running (no pid file)"
    return 0
  fi

  pid="$(<"${pid_file}")"
  if ! kill -0 "${pid}" 2>/dev/null; then
    echo "[${name}] stale pid file removed"
    rm -f "${pid_file}"
    return 0
  fi

  echo "[${name}] stopping pid=${pid}..."
  minerva_kill_tree "${pid}"
  rm -f "${pid_file}"
  echo "[${name}] stopped"
}

minerva_service_status() {
  local name=$1
  local pid_file log_file pid

  pid_file="$(minerva_service_pid_file "${name}")"
  log_file="$(minerva_service_log_file "${name}")"
  if minerva_service_running "${name}"; then
    pid="$(<"${pid_file}")"
    echo "[${name}] running pid=${pid} log=${log_file}"
    return 0
  fi
  [[ -f "${pid_file}" ]] && rm -f "${pid_file}"
  echo "[${name}] stopped"
  return 1
}

minerva_service_restart() {
  local name=$1
  shift
  minerva_service_stop "${name}"
  minerva_service_start "${name}" "$@"
}

minerva_service_stop_glob() {
  local pattern=$1
  local run_dir pid_file

  run_dir="$(minerva_run_dir)"
  shopt -s nullglob
  local files=("${run_dir}"/${pattern}.pid)
  shopt -u nullglob
  if [[ ${#files[@]} -eq 0 ]]; then
    return 0
  fi
  for pid_file in "${files[@]}"; do
    local base
    base="$(basename "${pid_file}" .pid)"
    minerva_service_stop "${base}"
  done
}
