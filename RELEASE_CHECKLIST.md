# Release Checklist

## 1. Pre-release (local)
- Ensure branch is clean: `git status`
- Pull latest: `git pull --rebase`
- Verify Go + Python sanity:
  - `cd go-bedehus && go test ./...`
  - `python3 -m py_compile main.py`
- Build all Go targets:
  - `cd go-bedehus && make build-all`

## 2. Package Artifacts
- Confirm required binaries exist in `go-bedehus/dist/`:
  - `bedehus-linux-amd64`
  - `bedehus-on-linux-amd64`
  - `bedehus-off-linux-amd64`
  - (and relevant ARM variants for target hardware)
- Record exact commit to deploy:
  - `git rev-parse --short HEAD`

## 3. Target Host Prep
- Verify local (non-git) runtime files exist on target host:
  - `config/config.json`
  - `service-account-key.json`
  - `secrets.json`
- Confirm safe config toggles before start:
  - `sr201.enabled`
  - `timing.enabled`
  - `cache.google_max_age_hours`
- Backup currently running binaries before replacing.

## 4. Deploy
- Copy binaries to target host.
- Replace running binaries atomically (new filename + symlink swap, or stop/copy/start).
- Restart service/cron job.

## 5. Post-deploy Validation
- Run one manual dry check:
  - `./bedehus -config config/config.json`
- If `sr201.enabled=true`, verify relay behavior using:
  - `./bedehus-on -config config/config.json`
  - `./bedehus-off -config config/config.json`
- Validate logs:
  - No Google auth/network errors
  - No Glamox/Mill errors
  - `Timing summary` present when `timing.enabled=true`
- Validate expected room state (Storsalen/Bønnerom) after run.

## 6. Rollback Plan
- Keep previous known-good binaries on host.
- If release fails:
  - restore previous binaries
  - restart service
  - confirm logs return to normal
- Document rollback cause and failing commit hash.

## 7. Git Hygiene
- Never commit runtime secrets or local config:
  - `config/config.json` (ignored)
  - `service-account-key.json`
  - `secrets.json`
- Update `config/config.example.json` whenever config schema changes.
