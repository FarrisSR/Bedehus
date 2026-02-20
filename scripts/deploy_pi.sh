#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  scripts/deploy_pi.sh --host <pi-host> [options]

Required:
  --host <host>              Pi hostname or IP

Options:
  --user <user>              SSH user (default: pi)
  --arch <arch>              pi2-3 | pi4-arm64 (default: pi2-3)
  --remote-dir <path>        Base deploy dir on Pi (default: /home/pi/bedehus)
  --service <name>           systemd service to restart (default: bedehus)
  --restart-service          Restart service after copy
  --rollback                 Restore previous binaries (*.prev) on target and exit
  --skip-build               Skip local Go build step
  -h, --help                 Show this help

Examples:
  scripts/deploy_pi.sh --host 192.168.1.40
  scripts/deploy_pi.sh --host bedehus-pi.local --arch pi4-arm64 --restart-service
  scripts/deploy_pi.sh --host bedehus-pi.local --rollback --restart-service
EOF
}

HOST=""
USER_NAME="pi"
ARCH="pi2-3"
REMOTE_DIR="/home/pi/bedehus"
SERVICE_NAME="bedehus"
RESTART_SERVICE=0
ROLLBACK=0
SKIP_BUILD=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --host)
      HOST="${2:-}"
      shift 2
      ;;
    --user)
      USER_NAME="${2:-}"
      shift 2
      ;;
    --arch)
      ARCH="${2:-}"
      shift 2
      ;;
    --remote-dir)
      REMOTE_DIR="${2:-}"
      shift 2
      ;;
    --service)
      SERVICE_NAME="${2:-}"
      shift 2
      ;;
    --restart-service)
      RESTART_SERVICE=1
      shift
      ;;
    --rollback)
      ROLLBACK=1
      shift
      ;;
    --skip-build)
      SKIP_BUILD=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage
      exit 1
      ;;
  esac
done

if [[ -z "$HOST" ]]; then
  echo "Error: --host is required" >&2
  usage
  exit 1
fi

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
GO_DIR="$REPO_ROOT/go-bedehus"
DIST_DIR="$GO_DIR/dist"

case "$ARCH" in
  pi2-3)
    BUILD_TARGET="build-pi2-3"
    SUFFIX="linux-armv7"
    ;;
  pi4-arm64)
    BUILD_TARGET="build-pi4-arm64"
    SUFFIX="linux-arm64"
    ;;
  *)
    echo "Error: invalid --arch '$ARCH' (expected pi2-3 or pi4-arm64)" >&2
    exit 1
    ;;
esac

if [[ "$SKIP_BUILD" -eq 0 ]]; then
  echo "Building Go binaries for $ARCH ($SUFFIX)..."
  make -C "$GO_DIR" "$BUILD_TARGET"
fi

BIN_MAIN="$DIST_DIR/bedehus-$SUFFIX"
BIN_ON="$DIST_DIR/bedehus-on-$SUFFIX"
BIN_OFF="$DIST_DIR/bedehus-off-$SUFFIX"

for file in "$BIN_MAIN" "$BIN_ON" "$BIN_OFF"; do
  if [[ ! -f "$file" ]]; then
    echo "Error: missing binary $file" >&2
    exit 1
  fi
done

REMOTE="${USER_NAME}@${HOST}"
REMOTE_BIN_DIR="$REMOTE_DIR/bin"

if [[ "$ROLLBACK" -eq 1 ]]; then
  echo "Rolling back binaries on $REMOTE..."
  ssh "$REMOTE" "\
    test -f '$REMOTE_BIN_DIR/bedehus.prev' && cp '$REMOTE_BIN_DIR/bedehus.prev' '$REMOTE_BIN_DIR/bedehus' || true; \
    test -f '$REMOTE_BIN_DIR/bedehus-on.prev' && cp '$REMOTE_BIN_DIR/bedehus-on.prev' '$REMOTE_BIN_DIR/bedehus-on' || true; \
    test -f '$REMOTE_BIN_DIR/bedehus-off.prev' && cp '$REMOTE_BIN_DIR/bedehus-off.prev' '$REMOTE_BIN_DIR/bedehus-off' || true; \
    chmod +x '$REMOTE_BIN_DIR/bedehus' '$REMOTE_BIN_DIR/bedehus-on' '$REMOTE_BIN_DIR/bedehus-off' 2>/dev/null || true"

  if [[ "$RESTART_SERVICE" -eq 1 ]]; then
    echo "Restarting systemd service: $SERVICE_NAME"
    ssh "$REMOTE" "sudo systemctl restart '$SERVICE_NAME' && sudo systemctl status '$SERVICE_NAME' --no-pager"
  fi

  echo "Rollback completed."
  exit 0
fi

echo "Creating remote bin directory: $REMOTE_BIN_DIR"
ssh "$REMOTE" "mkdir -p '$REMOTE_BIN_DIR'"

echo "Backing up previous binaries to *.prev"
ssh "$REMOTE" "\
  test -f '$REMOTE_BIN_DIR/bedehus' && cp '$REMOTE_BIN_DIR/bedehus' '$REMOTE_BIN_DIR/bedehus.prev' || true; \
  test -f '$REMOTE_BIN_DIR/bedehus-on' && cp '$REMOTE_BIN_DIR/bedehus-on' '$REMOTE_BIN_DIR/bedehus-on.prev' || true; \
  test -f '$REMOTE_BIN_DIR/bedehus-off' && cp '$REMOTE_BIN_DIR/bedehus-off' '$REMOTE_BIN_DIR/bedehus-off.prev' || true"

echo "Copying binaries to $REMOTE..."
scp "$BIN_MAIN" "$REMOTE:$REMOTE_BIN_DIR/bedehus"
scp "$BIN_ON" "$REMOTE:$REMOTE_BIN_DIR/bedehus-on"
scp "$BIN_OFF" "$REMOTE:$REMOTE_BIN_DIR/bedehus-off"

echo "Setting executable permissions..."
ssh "$REMOTE" "chmod +x '$REMOTE_BIN_DIR/bedehus' '$REMOTE_BIN_DIR/bedehus-on' '$REMOTE_BIN_DIR/bedehus-off'"

if [[ "$RESTART_SERVICE" -eq 1 ]]; then
  echo "Restarting systemd service: $SERVICE_NAME"
  ssh "$REMOTE" "sudo systemctl restart '$SERVICE_NAME' && sudo systemctl status '$SERVICE_NAME' --no-pager"
fi

cat <<EOF
Deploy completed.

Next checks on Pi:
  BEDEHUS_BASE_DIR=$REMOTE_DIR $REMOTE_BIN_DIR/bedehus -config config/config.json
  journalctl -u $SERVICE_NAME -n 100 --no-pager
EOF
