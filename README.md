# Bedehus

Hi ALL!

This is my rPI project to control heat at our Bedehus.

I pull the calander from Google and turn on the heat if someone is renting it.

For this project I have a Raspberry Pi (Running Rasbian) with the GrovePI HAT and a Grove-relay:

https://www.raspberrypi.org/

Let's see if the SR-201 can do the job better!!
http://www.uddating.se/2017/05/13/sr-201-network-relay/
https://github.com/berkinet/sr-201-relay/blob/master/sr-201-relay.py


The GRove is out!
https://www.dexterindustries.com/GrovePi/get-started-with-the-grovepi/


* Have a look into requirements.txt. 

During development (whenever new requirements are added):

    pip freeze > requirements.txt 

When arriving to a new runtime location, install dependencies like this:

    pip install -r requirements.txt 

--
FarrisSR & Vaskeball

## Hemmeligheter / API-nøkler

Bruk `secrets.json` i rot (se `secrets.example.json` for struktur). Felter som støttes:
- Glamox: `GLAMOX_CLIENT_ID`, `GLAMOX_CLIENT_SECRET`, valgfritt `GLAMOX_API_URL`.
- Mill cloud: `MILL_USERNAME`, `MILL_PASSWORD`, valgfritt `MILL_API_URL`.

`scripts/temperature_logger.py` leser disse automatisk (eller via miljøvariabler).

## Go-port

Go-koden ligger i `go-bedehus/`. Konfigurasjonen ligger i `config/config.json` (se `config/config.example.json`).

Viktige felter:
- `time_window_hours`: hvor langt fram vi ser etter events i Google Calendar.
- `glamox.enabled`: sett til `false` for å deaktivere Glamox-integrasjon.
- `mill.enabled`: sett til `false` for å deaktivere Mill-integrasjon.

Build/run (eksempel):

```
cd go-bedehus
go mod tidy
go build -o bedehus .
./bedehus -config ../config/config.json
```



## Lokale mock-tjenester

For testing uten ekte maskinvare finnes to språkagnostiske mock-servere i `scripts/`:
- `mock_sr201_server.py`: emulerer SR201 TCP-protokollen (`00`, `1R`, `2R`).
- `mock_mill_controller.py`: emulerer Mill-kontrollerens HTTP-endepunkter (`POST /set-temperature`, `GET /control-status`).

Eksempel:

```
python3 scripts/mock_sr201_server.py --port 16722 --initial-state 10000000
python3 scripts/mock_mill_controller.py --port 18080 --target 17 --current-temperature 16.5
```

Disse kan brukes fra Python-, Go- og Rust-variantene ved å peke konfigurasjonen til `127.0.0.1:<port>`.

## ARP-overvåkning av ovner

For lokal overvåkning av ARP-synlighet (f.eks. Glamox-ovner) finnes `scripts/arp_presence_logger.py`.
Den leser alias fra `scripts/arp_alias`, kjører `arp-scan` med valgt interface (standard `wlan0`, dvs. `-I <interface>`), og logger JSON-lines via `logging_arp.config` til syslog (`bedehus-arp`).

Eksempel:

```
python3 scripts/arp_presence_logger.py --config config/config.json --stdout
```

Eksempelfiler for `systemd` ligger i `systemd/bedehus-arp-presence.service` og `systemd/bedehus-arp-presence.timer`. For cron kan `scripts/cron_arp_presence.sh` brukes; scriptet finner repo-roten automatisk, bruker `venv/bin/python` hvis den finnes, og faller ellers tilbake til `python3`.

Eksempel på crontab-linje på Pi1:

```
*/5 * * * * cd /home/runo/code/Bedehus-glamox && flock -n /home/runo/arp_presence.lockfile /home/runo/code/Bedehus-glamox/scripts/cron_arp_presence.sh >> /dev/null 2>&1
```
