# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This System Does

Calendar-driven heating controller for a bedehus (church hall). It polls two Google Calendars (Storsalen and Bønnerom) and, based on a configurable lookahead window, turns heating on or off via:
- **SR201 relay** — TCP commands to a network relay (Storsalen main heating)
- **Glamox API** — REST + JWT to set room temperature (Storsalen)
- **Mill controller** — HTTP API to set temperature (Bønnerom)

State is persisted in SQLite. The system runs as a systemd service on a Raspberry Pi.

## Language Implementations

Three implementations exist at different maturity levels:

| Directory | Language | Status |
|---|---|---|
| `go-bedehus/` | Go | **Primary** — deployed, full-featured |
| `main.py` / `systemd_main.py` | Python | Legacy reference |
| `rust-bedehus/` | Rust | Emerging — reporting tools + controller WIP |

The Go implementation is the active controller. Rust handles data analysis and reporting. Python is kept as a reference but not deployed.

## Build & Test Commands

### Go (go-bedehus/)
```sh
go test ./...                # run tests
make build                   # build `bedehus` binary
make build-all               # cross-compile for all ARM targets + amd64
make build-pi1               # armv6 (Pi 1)
make build-pi2-3             # armv7 (Pi 2/3)
make build-pi4-arm64         # arm64 (Pi 4)
make run                     # run with config/config.json
make build-on && make run-on # force heater on
make build-off && make run-off # force heater off
```

### Rust (rust-bedehus/)
```sh
cargo build
cargo build --release
cargo test
cargo run -- controller-run-once --config config/config.json [--dry-run]
cargo run -- controller-daemon --config config/config.json [--interval-seconds N] [--dry-run]
cargo run -- generate-static-report [options]
cargo run -- import-arp-presence --db ../data/temperature_history.sqlite --log-path /var/log/bedehus/arp-scan.jsonl --aliases-file ../scripts/arp_alias
```

### Python
```sh
python3 main.py --config config/config.json
scripts/run_safe_test.sh [main|systemd]   # offline test with mock servers
python3 scripts/mock_sr201_server.py      # mock TCP relay for testing
python3 scripts/mock_mill_controller.py   # mock HTTP Mill for testing
```

## Configuration

Active config lives at `config/config.json` (git-ignored). Use `config/config.example.json` as the schema reference.

The Go binary resolves paths relative to `BEDEHUS_BASE_DIR` env var, or the directory of the executable. Secrets (Glamox/Mill credentials) live in `secrets.json` or as env vars.

## Architecture Details

### Go package layout
```
go-bedehus/
├── main.go              # entrypoint: calendar check → device updates
├── cmd/on/ cmd/off/     # CLI to force relay on/off
└── internal/
    ├── config/          # JSON config parsing + validation
    ├── gcal/            # Google Calendar API (service account auth, 24h cache)
    ├── sr201/           # TCP protocol client (commands: "00" check, "1R" close, "2R" open)
    ├── glamox/          # REST + JWT auth
    ├── mill/            # HTTP API client
    ├── logging/         # structured logging setup
    └── state/           # SQLite state persistence
```

### Shared SQLite databases
- `config/relay_state.db` — relay state history (Go controller)
- `data/temperature_history.sqlite` — readings from all sources (Rust/Python scripts)
- `data/energy_history.sqlite` — energy consumption logs

### Key conventions
- Room names: **Storsalen** (main hall), **Bønnerom** (prayer room)
- Oven MAC aliases defined in `scripts/arp_alias`
- Timestamps: ISO8601 throughout
- Temperature logging: `scripts/temperature_logger.py` runs via cron; Rust `import-arp-presence` processes ARP scan logs
- systemd service templates: `config/bedehus-*.service.example`
- Cron templates: `config/crontab.root`, `config/crontab.user`

## CI/CD

`.github/workflows/build-release.yml` triggers on version tags (`v*`) or manual dispatch. It cross-compiles the Go binary to armv6 and publishes a GitHub release. See `RELEASE_CHECKLIST.md` for the pre/post-deploy runbook.
