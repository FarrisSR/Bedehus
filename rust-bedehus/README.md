# rust-bedehus

Rust-MVP for Bedehus-repoet.

Første mål her er ikke å porte alt fra Python/Go med en gang, men å vise en ren Rust-struktur og å portere en konkret, nyttig del først:

- `import-arp-presence`
- `heater-status`

Disse to kommandoene bruker samme `data/temperature_history.sqlite` som Python-koden og skriver/leser fra de samme `heater_presence_*`-tabellene.

Eksempel:

```bash
cd rust-bedehus
cargo run -- import-arp-presence \
  --db ../data/temperature_history.sqlite \
  --log-path /var/log/bedehus/arp-scan.jsonl \
  --aliases-file ../scripts/arp_alias

cargo run -- heater-status --db ../data/temperature_history.sqlite
```

Neste naturlige steg hvis denne retningen ser bra ut:

1. portere temperatur-loggerens database- og rapportlogikk
2. portere ARP-graf/HTML-generering
3. til slutt vurdere Mill/Glamox/Yr-klientene
