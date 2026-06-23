#!/usr/bin/env bash
# Backward-compatible wrapper: install only minerva-backend.service.
# Prefer: bash scripts/install-systemd.sh [install|uninstall|show] backend
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec bash "${SCRIPT_DIR}/install-systemd.sh" "${1:-install}" backend "${@:2}"
