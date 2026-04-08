#!/usr/bin/env bash
# Enkel wrapper for cron: logger temperaturer fra Glamox og Mill hver gang den kjøres.
# Forutsetter at secrets.json inneholder Mill/Glamox creds og at python3/requests er installert.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="${ROOT_DIR}/logs"
REPORT_ROOT="${REPORT_ROOT:-/home/runo/public_html/www}"
REPORT_IMG="${REPORT_ROOT}/graphs/last_48h.png"
REPORT_HTML="${REPORT_ROOT}/index.html"
RUST_REPORT_ROOT="${RUST_REPORT_ROOT:-/home/runo/public_html/rust_temp}"
RUST_REPORT_BIN="${ROOT_DIR}/rust-bedehus/target/release/bedehus-rs"
PYTHON_LOG="${LOG_DIR}/temperature_log_cron.log"
RUST_LOG="${LOG_DIR}/temperature_log_rust_cron.log"
mkdir -p "${LOG_DIR}"
mkdir -p "${REPORT_ROOT}/graphs"
mkdir -p "${RUST_REPORT_ROOT}/graphs"

cd "${ROOT_DIR}"

timestamp() {
    date +"%Y-%m-%d %H:%M:%S"
}

{
    echo "--- $(timestamp) ---"
echo "+ Python import ARP presence -> data/temperature_history.sqlite"
PYTHONUNBUFFERED=1 python3 scripts/temperature_logger.py import-arp-presence \
    --db data/temperature_history.sqlite \
    --log-path /var/log/bedehus/arp-scan.jsonl \
    --aliases-file scripts/arp_alias
echo "+ Python temperature log -> data/temperature_history.sqlite"
PYTHONUNBUFFERED=1 python3 scripts/temperature_logger.py log \
    --glamox-room "Storsalen" \
    --mill-device-id "a279571d-5f56-4eb3-a10a-a729a5424787" \
    --mill-room-name "Bønnerom" \
    --yr
echo "+ Python static report -> ${REPORT_HTML}"
PYTHONUNBUFFERED=1 python3 scripts/generate_static_report.py \
        --db data/temperature_history.sqlite \
        --hours 48 \
    --output-img "${REPORT_IMG}" \
    --output-img-7d "${REPORT_ROOT}/graphs/last_7d.png" \
    --output-img-30d "${REPORT_ROOT}/graphs/last_30d.png" \
    --output-html "${REPORT_HTML}"
echo "+ Python energy log -> data/energy_history.sqlite"
PYTHONUNBUFFERED=1 python3 scripts/energy_logger.py log \
    --db data/energy_history.sqlite \
    --mill-device-id "a279571d-5f56-4eb3-a10a-a729a5424787" \
    --mill-home-name "Bedehuset" \
    --mill-room-name "Bønnerom"
echo "+ Python energy report -> ${REPORT_ROOT}/energy.html"
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
} >> "${PYTHON_LOG}" 2>&1

{
    echo "--- $(timestamp) ---"
echo "+ Rust static report -> ${RUST_REPORT_ROOT}/index.html"
"${RUST_REPORT_BIN}" generate-static-report \
    --db data/temperature_history.sqlite \
    --hours 48 \
    --output-img "${RUST_REPORT_ROOT}/graphs/last_48h.png" \
    --output-img-7d "${RUST_REPORT_ROOT}/graphs/last_7d.png" \
    --output-img-30d "${RUST_REPORT_ROOT}/graphs/last_30d.png" \
    --output-html "${RUST_REPORT_ROOT}/index.html"
echo "+ Rust energy report -> ${RUST_REPORT_ROOT}/energy.html"
"${RUST_REPORT_BIN}" generate-energy-report \
    --db data/energy_history.sqlite \
    --hours 48 \
    --temp-db data/temperature_history.sqlite \
    --temp-outdoor-source "yr" \
    --temp-outdoor-room "Bjørkelangen ute" \
    --temp-room-source "mill" \
    --temp-room "Bønnerom" \
    --output-img "${RUST_REPORT_ROOT}/graphs/energy_48h.png" \
    --output-html "${RUST_REPORT_ROOT}/energy.html"
} >> "${RUST_LOG}" 2>&1
