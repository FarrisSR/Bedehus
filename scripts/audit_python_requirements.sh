#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "${ROOT_DIR}/venv/bin/activate"
exec pip-audit -r "${ROOT_DIR}/requirements.txt"
