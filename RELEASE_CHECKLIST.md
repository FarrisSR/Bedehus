# Release Checklist

## 1. Pre-release (local)
- Ensure branch is clean: `git status`
- Pull latest: `git pull --rebase`
- Verify Go, Rust og Python lokalt:
  - `cd go-bedehus && go vet ./... && go test ./...`
  - `cd rust-bedehus && cargo test && cargo clippy -- -D warnings`
  - `python3 -m compileall -q main.py systemd_main.py glamox/ mill_controller/ sr201/ common/ scripts/`
  - `pytest tests/ -v`
- Build og røyktest lokalt (valgfritt, CI gjør dette automatisk):
  - `cd go-bedehus && make build-all`
  - `cd rust-bedehus && cargo build --release`

## 2. CI-verifisering
CI-pipelinene kjøres automatisk ved tagging. Bekreft at alle jobber er grønne
på GitHub Actions før du går videre:
- **ci.yml** (push/PR): Go vet + test, Python lint + test, Rust test + clippy
- **build-release.yml** (Go): vet → test → bygg armv6 → QEMU røyktest → release
- **build-release-rust.yml** (Rust): test + clippy → bygg armv6 → QEMU røyktest → release

## 3. Tag og release
- Velg versjonsnummer etter [SemVer](https://semver.org/): `vMAJOR.MINOR.PATCH`
- Tag og push:
  ```bash
  git tag v1.2.3
  git push origin v1.2.3
  ```
- Verifiser at GitHub Release ble opprettet med alle forventede assets:
  - `bedehus-linux-armv6` + `.sha256`
  - `bedehus-on-linux-armv6` + `.sha256`
  - `bedehus-off-linux-armv6` + `.sha256`
  - `bedehus-rs-linux-armv6` + `.sha256`
  - **Viktig**: vent til *begge* pipelines (`build-release.yml` og `build-release-rust.yml`)
    er fullført før auto-updateren tillates å kjøre – de oppretter/oppdaterer samme
    release-tag uavhengig av hverandre, og en for tidlig poll kan plukke opp en
    delvis ferdig release.
- Record commit: `git rev-parse --short HEAD`

## 4. Deploy til Pi (automatisk via auto-updater)
Pi-en poller GitHub Releases hvert 10. minutt og installerer automatisk.
Vent til timeren trigger, eller kjør manuelt:
```bash
sudo systemctl start bedehus-updater.service
journalctl -u bedehus-updater -f
```
Forventet logg ved vellykket oppdatering:
```
bedehus-updater INFO  Ny versjon tilgjengelig: v1.2.2 → v1.2.3
bedehus-updater INFO  Installerte bedehus → /home/pi/bedehus/bedehus
bedehus-updater INFO  Restartet bedehus
bedehus-updater INFO  Oppdatering fullført: v1.2.3 (4 installert)
```

## 5. Target Host Prep (kun første gang / ved schemaendringer)
- Verifiser at disse filene finnes på Pi-en (aldri i git):
  - `config/config.json`
  - `service-account-key.json`
  - `secrets.json`
- Bekreft konfigverdier før start:
  - `sr201.enabled`
  - `cache.google_max_age_hours`

## 6. Post-deploy validering
- Auto-updateren verifiserer hver binary mot `<asset>.sha256` fra releasen før
  den installeres, og avviser nedlastingen ved mismatch (gammel binary beholdes).
  Sjekk `journalctl -u bedehus-updater -n 50` for `Checksum-mismatch`-feil ved feilsøking.
- Manuell verifisering av en installert binary mot releasen:
  ```bash
  TOKEN=$(sudo cat /etc/bedehus/github_token 2>/dev/null)
  curl -sf ${TOKEN:+-H "Authorization: Bearer $TOKEN"} \
    "https://api.github.com/repos/FarrisSR/Bedehus/releases/tags/<tag>" \
    | python3 -c "import sys,json; [print(a['name'],a['id']) for a in json.load(sys.stdin)['assets']]"
  # finn sha256-asset-id og last den ned, sammenlign mot:
  sha256sum /home/runo/bedehus/<binary>
  ```
- Kjør én manuell dry-run på Pi-en:
  ```bash
  /home/pi/bedehus/bedehus -config config/config.json
  ```
- Hvis `sr201.enabled=true`, verifiser reléatferd:
  ```bash
  /home/pi/bedehus/bedehus-on -config config/config.json
  /home/pi/bedehus/bedehus-off -config config/config.json
  ```
- Valider logger (`journalctl -u bedehus -n 50`):
  - Ingen Google auth/nettverksfeil
  - Ingen Glamox/Mill-feil
  - `Timing summary` til stede

## 7. Rollback
Auto-oppdateren lagrer `.prev`-kopi av hver binary. Manuell rollback:
```bash
cd /home/pi/bedehus
for f in bedehus bedehus-on bedehus-off bedehus-rs; do
    [[ -f "$f.prev" ]] && mv "$f.prev" "$f"
done
sudo systemctl restart bedehus
```
Verifiser at loggene er normale etter rollback.
Dokumenter årsak og commit-hash for feilen.

## 8. Git-hygiene
- Commit aldri runtime-hemmeligheter eller lokal konfig:
  - `config/config.json` (git-ignorert)
  - `service-account-key.json`
  - `secrets.json`
- Oppdater `config/config.example.json` ved endringer i konfigskjema.
