#!/usr/bin/env bash
# Install Minerva backend + Celery worker/beat as systemd units under /etc/systemd/system/.
# Usage:
#   sudo bash scripts/install-systemd.sh [install|uninstall|show] [all|backend|worker|beat ...]
# Env:
#   MINERVA_REPO_ROOT, MINERVA_PROFILE (default test), MINERVA_USER, MINERVA_GROUP
#   MINERVA_BACKEND_PORT (default 8000)
#   MINERVA_CELERY_POOL (default prefork), MINERVA_CELERY_CONCURRENCY (default 4)
#   MINERVA_CELERY_QUEUES (default default,dataset)
#   MINERVA_SYSTEMD_DIR (default /etc/systemd/system)
#   MINERVA_SYSTEMD_ENABLE=0, MINERVA_SYSTEMD_START=0
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=_systemd-common.sh
source "${SCRIPT_DIR}/_systemd-common.sh"

usage() {
  cat <<'EOF'
Usage: install-systemd.sh [install|uninstall|show] [all|backend|worker|beat ...]

  install     write unit files, daemon-reload, enable, start (default: all)
  uninstall   disable, stop, remove unit files, daemon-reload (default: all)
  show        print unit files to stdout (no root required; default: all)

Units:
  minerva-backend.service
  minerva-celery-worker.service
  minerva-celery-beat.service

Examples:
  sudo bash scripts/install-systemd.sh
  sudo bash scripts/install-systemd.sh install worker beat
  MINERVA_PROFILE=prod MINERVA_USER=minerva sudo bash scripts/install-systemd.sh
  bash scripts/install-systemd.sh show backend
  sudo bash scripts/install-systemd.sh uninstall all
EOF
}

normalize_targets() {
  local -a raw=("$@")
  local -a out=()
  local item

  if [[ ${#raw[@]} -eq 0 ]]; then
    echo "all"
    return 0
  fi

  for item in "${raw[@]}"; do
    case "${item}" in
      all)
        out+=(backend worker beat)
        ;;
      backend | api | minerva-backend)
        out+=(backend)
        ;;
      worker | celery-worker | minerva-celery-worker)
        out+=(worker)
        ;;
      beat | celery-beat | scheduler | minerva-celery-beat)
        out+=(beat)
        ;;
      *)
        echo "[error] unknown target: ${item}" >&2
        usage >&2
        exit 1
        ;;
    esac
  done

  printf '%s\n' "${out[@]}" | awk '!seen[$0]++'
}

target_selected() {
  local needle=$1
  local target
  while IFS= read -r target; do
    [[ "${target}" == "${needle}" ]] && return 0
  done < <(normalize_targets "$@")
  return 1
}

resolve_runtime_identity() {
  RUN_USER="$(minerva_systemd_resolve_user)"
  RUN_GROUP="$(minerva_systemd_resolve_group "${RUN_USER}")"
  minerva_systemd_validate_user "${RUN_USER}" "${RUN_GROUP}"
}

do_show() {
  shift
  resolve_runtime_identity

  if target_selected backend "$@"; then
    echo "# --- minerva-backend.service ---"
    minerva_systemd_render_backend_unit "${RUN_USER}" "${RUN_GROUP}"
    echo
  fi
  if target_selected worker "$@"; then
    echo "# --- minerva-celery-worker.service ---"
    minerva_systemd_render_celery_worker_unit "${RUN_USER}" "${RUN_GROUP}"
    echo
  fi
  if target_selected beat "$@"; then
    echo "# --- minerva-celery-beat.service ---"
    minerva_systemd_render_celery_beat_unit "${RUN_USER}" "${RUN_GROUP}"
    echo
  fi
}

write_backend_unit() {
  minerva_systemd_validate_backend_api
  minerva_systemd_render_backend_unit "${RUN_USER}" "${RUN_GROUP}" | minerva_systemd_write_unit "minerva-backend.service"
}

write_worker_unit() {
  minerva_systemd_validate_celery
  minerva_systemd_render_celery_worker_unit "${RUN_USER}" "${RUN_GROUP}" | minerva_systemd_write_unit "minerva-celery-worker.service"
}

write_beat_unit() {
  minerva_systemd_validate_celery
  minerva_systemd_render_celery_beat_unit "${RUN_USER}" "${RUN_GROUP}" | minerva_systemd_write_unit "minerva-celery-beat.service"
}

do_install() {
  shift
  minerva_systemd_require_root install "$@"
  resolve_runtime_identity

  echo "[install] repo: $(minerva_systemd_repo_root)"
  echo "[install] profile: $(minerva_systemd_profile)"
  echo "[install] user: ${RUN_USER}:${RUN_GROUP}"

  if target_selected backend "$@"; then
    write_backend_unit
  fi
  if target_selected worker "$@"; then
    write_worker_unit
  fi
  if target_selected beat "$@"; then
    write_beat_unit
  fi

  systemctl daemon-reload

  if target_selected backend "$@"; then
    minerva_systemd_enable_unit "minerva-backend.service"
    minerva_systemd_start_unit "minerva-backend.service"
  fi
  if target_selected worker "$@"; then
    minerva_systemd_enable_unit "minerva-celery-worker.service"
    minerva_systemd_start_unit "minerva-celery-worker.service"
  fi
  if target_selected beat "$@"; then
    minerva_systemd_enable_unit "minerva-celery-beat.service"
    minerva_systemd_start_unit "minerva-celery-beat.service"
  fi

  echo "[install] done"
}

do_uninstall() {
  shift
  minerva_systemd_require_root uninstall "$@"

  if target_selected beat "$@"; then
    minerva_systemd_remove_unit "minerva-celery-beat.service"
  fi
  if target_selected worker "$@"; then
    minerva_systemd_remove_unit "minerva-celery-worker.service"
  fi
  if target_selected backend "$@"; then
    minerva_systemd_remove_unit "minerva-backend.service"
  fi

  systemctl daemon-reload
  echo "[uninstall] done"
}

ACTION="${1:-install}"
case "${ACTION}" in
  -h | --help | help)
    usage
    ;;
  install)
    do_install "$@"
    ;;
  uninstall | remove)
    do_uninstall "$@"
    ;;
  show)
    do_show "$@"
    ;;
  backend | worker | beat | all)
    do_install install "$@"
    ;;
  *)
    usage >&2
    exit 1
    ;;
esac
