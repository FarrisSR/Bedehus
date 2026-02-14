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
