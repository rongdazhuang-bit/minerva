#!/usr/bin/env bash
# Shared helpers for install-systemd*.sh. Do not execute directly.

minerva_systemd_repo_root() {
  local script_dir
  script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  cd "${MINERVA_REPO_ROOT:-${script_dir}/..}" && pwd
}

minerva_systemd_backend_dir() {
  echo "$(minerva_systemd_repo_root)/backend"
}

minerva_systemd_profile() {
  echo "${MINERVA_PROFILE:-test}"
}

minerva_systemd_dir() {
  echo "${MINERVA_SYSTEMD_DIR:-/etc/systemd/system}"
}

minerva_systemd_resolve_user() {
  if [[ -n "${MINERVA_USER:-}" ]]; then
    echo "${MINERVA_USER}"
    return 0
  fi
  if [[ -n "${SUDO_USER:-}" && "${SUDO_USER}" != "root" ]]; then
    echo "${SUDO_USER}"
    return 0
  fi
  id -un
}

minerva_systemd_resolve_group() {
  local user=$1
  if [[ -n "${MINERVA_GROUP:-}" ]]; then
    echo "${MINERVA_GROUP}"
    return 0
  fi
  id -gn "${user}"
}

minerva_systemd_venv_python() {
  echo "$(minerva_systemd_backend_dir)/.venv/bin/python"
}

minerva_systemd_validate_user() {
  local run_user=$1
  local run_group=$2

  if ! id "${run_user}" >/dev/null 2>&1; then
    echo "[error] user not found: ${run_user}" >&2
    return 1
  fi
  if ! getent group "${run_group}" >/dev/null 2>&1; then
    echo "[error] group not found: ${run_group}" >&2
    return 1
  fi
}

minerva_systemd_validate_backend_base() {
  local profile backend_dir env_file venv_py
  profile="$(minerva_systemd_profile)"
  backend_dir="$(minerva_systemd_backend_dir)"
  env_file="${backend_dir}/.env.${profile}"
  venv_py="$(minerva_systemd_venv_python)"

  if [[ ! -d "${backend_dir}" ]]; then
    echo "[error] backend directory not found: ${backend_dir}" >&2
    return 1
  fi
  if [[ ! -f "${env_file}" ]]; then
    echo "[error] env file not found: ${env_file}" >&2
    echo "[hint] cp backend/.env.example backend/.env.${profile}" >&2
    return 1
  fi
  if [[ ! -x "${venv_py}" ]]; then
    echo "[error] venv python not found: ${venv_py}" >&2
    echo "[hint] bash scripts/install-backend.sh" >&2
    return 1
  fi
}

minerva_systemd_validate_backend_api() {
  local venv_py
  minerva_systemd_validate_backend_base || return 1
  venv_py="$(minerva_systemd_venv_python)"
  if ! "${venv_py}" -c "import uvicorn" >/dev/null 2>&1; then
    echo "[error] uvicorn not installed in ${venv_py}" >&2
    echo "[hint] bash scripts/install-backend.sh" >&2
    return 1
  fi
}

minerva_systemd_validate_celery() {
  local venv_py
  minerva_systemd_validate_backend_base || return 1
  venv_py="$(minerva_systemd_venv_python)"
  if ! "${venv_py}" -c "import celery" >/dev/null 2>&1; then
    echo "[error] celery not installed in ${venv_py}" >&2
    echo "[hint] bash scripts/install-backend.sh" >&2
    return 1
  fi
}

minerva_systemd_require_root() {
  if [[ "${EUID}" -ne 0 ]]; then
    echo "[error] this action requires root; run: sudo bash $0 $*" >&2
    exit 1
  fi
}

minerva_systemd_unit_path() {
  local unit_name=$1
  echo "$(minerva_systemd_dir)/${unit_name}"
}

minerva_systemd_write_unit() {
  local unit_name=$1
  local unit_path tmp
  unit_path="$(minerva_systemd_unit_path "${unit_name}")"
  tmp="$(mktemp)"
  cat >"${tmp}"
  install -m 0644 "${tmp}" "${unit_path}"
  rm -f "${tmp}"
  echo "[install] wrote ${unit_path}"
}

minerva_systemd_enable_unit() {
  local unit_name=$1
  if [[ "${MINERVA_SYSTEMD_ENABLE:-1}" == "0" ]]; then
    return 0
  fi
  systemctl enable "${unit_name}"
  echo "[install] enabled ${unit_name}"
}

minerva_systemd_start_unit() {
  local unit_name=$1
  if [[ "${MINERVA_SYSTEMD_START:-1}" == "0" ]]; then
    echo "[install] skipped start for ${unit_name} (MINERVA_SYSTEMD_START=0)"
    return 0
  fi
  systemctl restart "${unit_name}"
  systemctl --no-pager --full status "${unit_name}" || true
}

minerva_systemd_stop_disable_unit() {
  local unit_name=$1
  if systemctl is-active --quiet "${unit_name}" 2>/dev/null; then
    systemctl stop "${unit_name}"
  fi
  if systemctl is-enabled --quiet "${unit_name}" 2>/dev/null; then
    systemctl disable "${unit_name}"
  fi
}

minerva_systemd_remove_unit() {
  local unit_name=$1
  local unit_path
  unit_path="$(minerva_systemd_unit_path "${unit_name}")"
  minerva_systemd_stop_disable_unit "${unit_name}"
  if [[ -f "${unit_path}" ]]; then
    rm -f "${unit_path}"
    echo "[uninstall] removed ${unit_path}"
  else
    echo "[uninstall] unit file not present: ${unit_path}"
  fi
}

minerva_systemd_render_backend_unit() {
  local run_user=$1
  local run_group=$2
  local profile repo_root backend_dir venv_py port
  profile="$(minerva_systemd_profile)"
  repo_root="$(minerva_systemd_repo_root)"
  backend_dir="$(minerva_systemd_backend_dir)"
  venv_py="$(minerva_systemd_venv_python)"
  port="${MINERVA_BACKEND_PORT:-8000}"

  cat <<EOF
[Unit]
Description=Minerva FastAPI Backend (APP_ENV=${profile})
Documentation=file://${repo_root}/README.md
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=${run_user}
Group=${run_group}
WorkingDirectory=${backend_dir}
Environment=APP_ENV=${profile}
Environment=MINERVA_BACKEND_PORT=${port}
ExecStart=${venv_py} -m uvicorn app.main:app --host 0.0.0.0 --port ${port}
Restart=on-failure
RestartSec=5
TimeoutStopSec=30
KillMode=mixed
NoNewPrivileges=true

[Install]
WantedBy=multi-user.target
EOF
}

minerva_systemd_render_celery_worker_unit() {
  local run_user=$1
  local run_group=$2
  local profile repo_root backend_dir venv_py pool concurrency queues
  profile="$(minerva_systemd_profile)"
  repo_root="$(minerva_systemd_repo_root)"
  backend_dir="$(minerva_systemd_backend_dir)"
  venv_py="$(minerva_systemd_venv_python)"
  pool="${MINERVA_CELERY_POOL:-prefork}"
  concurrency="${MINERVA_CELERY_CONCURRENCY:-4}"
  queues="${MINERVA_CELERY_QUEUES:-default,dataset}"

  cat <<EOF
[Unit]
Description=Minerva Celery Worker (APP_ENV=${profile})
Documentation=file://${repo_root}/README.md
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=${run_user}
Group=${run_group}
WorkingDirectory=${backend_dir}
Environment=APP_ENV=${profile}
Environment=MINERVA_CELERY_POOL=${pool}
Environment=MINERVA_CELERY_CONCURRENCY=${concurrency}
Environment=MINERVA_CELERY_QUEUES=${queues}
ExecStartPre=${venv_py} -m app.sys.celery.service.broker_preflight
ExecStart=${venv_py} -m celery -A app.celery_app:celery_app worker --loglevel=INFO --pool=${pool} --concurrency=${concurrency} -Q ${queues}
Restart=on-failure
RestartSec=10
TimeoutStopSec=60
KillMode=mixed
NoNewPrivileges=true

[Install]
WantedBy=multi-user.target
EOF
}

minerva_systemd_render_celery_beat_unit() {
  local run_user=$1
  local run_group=$2
  local profile repo_root backend_dir venv_py
  profile="$(minerva_systemd_profile)"
  repo_root="$(minerva_systemd_repo_root)"
  backend_dir="$(minerva_systemd_backend_dir)"
  venv_py="$(minerva_systemd_venv_python)"

  cat <<EOF
[Unit]
Description=Minerva Celery Beat Scheduler (APP_ENV=${profile})
Documentation=file://${repo_root}/README.md
After=network-online.target minerva-celery-worker.service
Wants=network-online.target

[Service]
Type=simple
User=${run_user}
Group=${run_group}
WorkingDirectory=${backend_dir}
Environment=APP_ENV=${profile}
ExecStartPre=${venv_py} -m app.sys.celery.service.broker_preflight
ExecStart=${venv_py} -m celery -A app.celery_app:celery_app beat --loglevel=INFO
Restart=on-failure
RestartSec=10
TimeoutStopSec=60
KillMode=mixed
NoNewPrivileges=true

[Install]
WantedBy=multi-user.target
EOF
}

minerva_systemd_all_units() {
  echo "minerva-backend.service minerva-celery-worker.service minerva-celery-beat.service"
}
