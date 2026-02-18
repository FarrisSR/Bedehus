#!/usr/bin/env bash
# Enkel wrapper for cron: logger temperaturer fra Glamox og Mill hver gang den kjøres.
# Forutsetter at secrets.json inneholder Mill/Glamox creds og at python3/requests er installert.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="${ROOT_DIR}/logs"
REPORT_ROOT="${REPORT_ROOT:-/home/runo/public_html/www}"
REPORT_IMG="${REPORT_ROOT}/graphs/last_48h.png"
REPORT_HTML="${REPORT_ROOT}/index.html"
mkdir -p "${LOG_DIR}"
mkdir -p "${REPORT_ROOT}/graphs"

cd "${ROOT_DIR}"

timestamp() {
    date +"%Y-%m-%d %H:%M:%S"
}

{
    echo "--- $(timestamp) ---"
PYTHONUNBUFFERED=1 python3 scripts/temperature_logger.py log \
    --glamox-room "Storsalen" \
    --mill-device-id "a279571d-5f56-4eb3-a10a-a729a5424787" \
    --mill-room-name "Bønnerom" \
    --yr
PYTHONUNBUFFERED=1 python3 scripts/generate_static_report.py \
        --db data/temperature_history.sqlite \
        --hours 48 \
    --output-img "${REPORT_IMG}" \
    --output-img-7d "${REPORT_ROOT}/graphs/last_7d.png" \
    --output-img-30d "${REPORT_ROOT}/graphs/last_30d.png" \
    --output-html "${REPORT_HTML}"
PYTHONUNBUFFERED=1 python3 scripts/energy_logger.py log \
    --db data/energy_history.sqlite \
    --mill-device-id "a279571d-5f56-4eb3-a10a-a729a5424787" \
    --mill-home-name "Bedehuset" \
    --mill-room-name "Bønnerom"
PYTHONUNBUFFERED=1 python3 scripts/generate_energy_report.py \
    --db data/energy_history.sqlite \
    --hours 48 \
    --temp-db data/temperature_history.sqlite \
    --temp-outdoor-source "yr" \
    --temp-outdoor-room "Bjørkelangen ute" \
    --temp-room-source "mill" \
    --temp-room "Bønnerom" \
    --output-img "${REPORT_ROOT}/graphs/energy_48h.png" \
    --output-html "${REPORT_ROOT}/energy.html"
} >> "${LOG_DIR}/temperature_log_cron.log" 2>&1
