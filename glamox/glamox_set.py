#!/usr/bin/env python3
import json
import sys
import requests

if len(sys.argv) < 3:
    print("Bruk: glamox_set.py <romnavn> <temperatur_C>", file=sys.stderr)
    sys.exit(2)

room_name = sys.argv[1]
target_c = float(sys.argv[2])

with open("../secrets.json", "r", encoding="utf-8") as f:
    s = json.load(f)

ACCOUNT_ID = str(s["GLAMOX_CLIENT_ID"])
API_PASSWORD = s["GLAMOX_CLIENT_SECRET"]
API_URL = s.get(
    "GLAMOX_API_URL", "https://api-1.glamoxheating.com/client-api").rstrip("/")

# Auth
r = requests.post(f"{API_URL}/auth/token",
                  data={"grant_type": "password",
                        "username": ACCOUNT_ID, "password": API_PASSWORD},
                  timeout=20)
r.raise_for_status()
token = r.json()["access_token"]
H = {"Authorization": f"Bearer {token}"}

# Finn rom-id fra navn
content = requests.get(f"{API_URL}/rest/v1/content/",
                       headers=H, timeout=20).json()
rooms = content.get("rooms", [])
match = next((r for r in rooms if r.get("name") == room_name), None)
if not match:
    print("Fant ikke rommet. Tilgjengelige rom:")
    for r in rooms:
        print(" -", r.get("name"))
    sys.exit(1)

room_id = match["id"]
centi = int(round(target_c * 100))

# Sett target
payload = {"rooms": [{"id": room_id, "targetTemperature": str(centi)}]}
resp = requests.post(f"{API_URL}/rest/v1/control/",
                     headers=H, json=payload, timeout=20)
resp.raise_for_status()

print(f"✓ Satt {room_name} → {target_c:.1f}°C (room_id={room_id})")
