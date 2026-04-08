#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_PYTHON="${ROOT_DIR}/venv/bin/python"
TEST_DIR="${ROOT_DIR}/data/safe_test"
TEST_LOGGING_CONFIG="${TEST_DIR}/logging.config"
TEST_CONFIG="${TEST_DIR}/config.json"
MODE="${1:-main}"
TEST_DB="${TEST_DIR}/state-${MODE}.db"

mkdir -p "${TEST_DIR}"

if [[ ! -x "${VENV_PYTHON}" ]]; then
    echo "Fant ikke ${VENV_PYTHON}. Opprett venv og installer requirements først." >&2
    exit 1
fi

cat > "${TEST_LOGGING_CONFIG}" <<EOF
[loggers]
keys=root

[handlers]
keys=consoleHandler

[formatters]
keys=simpleFormatter

[logger_root]
level=INFO
handlers=consoleHandler

[handler_consoleHandler]
class=StreamHandler
level=INFO
formatter=simpleFormatter
args=(sys.stdout,)

[formatter_simpleFormatter]
format=%(asctime)s %(name)-12s %(levelname)-8s %(message)s
EOF

cat > "${TEST_CONFIG}" <<EOF
{
  "google": {
    "key_file": "service-account-key.json",
    "scopes": [
      "https://www.googleapis.com/auth/calendar.readonly"
    ],
    "calendar_id": "84ansm753q4ru2mjc9952nel7g@group.calendar.google.com",
    "pray_id": "sivrsgorvkkohp6ofe7p65j4o0@group.calendar.google.com"
  },
  "sr201": {
    "enabled": false,
    "ip": "192.168.100.100",
    "port": 6722,
    "relay": 1,
    "timeout_seconds": 5,
    "relay_pause_seconds": 5
  },
  "mill": {
    "enabled": false,
    "ip": "192.168.0.173",
    "temp_type": "Normal",
    "heat_on_temp": 21,
    "heat_off_temp": 17
  },
  "glamox": {
    "enabled": false,
    "room_name": "Storsalen",
    "api_url": "https://api-1.glamoxheating.com/client-api",
    "heat_on_temp": 24,
    "heat_off_temp": 18
  },
  "logging": {
    "python_config_file": "data/safe_test/logging.config"
  },
  "cache": {
    "google_max_age_hours": 24
  },
  "state_db": {
    "path": "data/safe_test/state-${MODE}.db"
  },
  "time_window_hours": 2
}
EOF

rm -f "${TEST_DB}"

cd "${ROOT_DIR}"

case "${MODE}" in
    main)
        exec "${VENV_PYTHON}" main.py --config "data/safe_test/config.json"
        ;;
    systemd)
        exec "${VENV_PYTHON}" systemd_main.py --config "data/safe_test/config.json" --run-once
        ;;
    *)
        echo "Ugyldig modus: ${MODE}. Bruk 'main' eller 'systemd'." >&2
        exit 1
        ;;
esac
