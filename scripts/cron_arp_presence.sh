#!/usr/bin/env bash
# Enkel wrapper for cron: scanner lokale ARP-enheter og logger JSON-lines til syslog.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="${ROOT_DIR}/logs"
PYTHON_BIN="${PYTHON_BIN:-${ROOT_DIR}/venv/bin/python}"
CONFIG_FILE="${CONFIG_FILE:-${ROOT_DIR}/config/config.json}"
mkdir -p "${LOG_DIR}"

if [[ ! -x "${PYTHON_BIN}" ]]; then
  PYTHON_BIN="${PYTHON_FALLBACK:-python3}"
fi

if [[ ! -f "${CONFIG_FILE}" ]]; then
  echo "Mangler config-fil: ${CONFIG_FILE}" >&2
  exit 1
fi

cd "${ROOT_DIR}"

PYTHONUNBUFFERED=1 "${PYTHON_BIN}" scripts/arp_presence_logger.py --config "${CONFIG_FILE}" \
  >> "${LOG_DIR}/arp_presence_cron.log" 2>&1
