#!/usr/bin/env python3
"""
Standalone test: hent status fra Glamox/Adax API
- Leser hemmeligheter fra secrets.json
- Logger inn og skriver ut rom med nåværende temperatur og target
"""

import json
import requests

# --- les hemmeligheter ---
with open("../secrets.json", "r", encoding="utf-8") as f:
    secrets = json.load(f)

CLIENT_ID = secrets["GLAMOX_CLIENT_ID"]
CLIENT_SECRET = secrets["GLAMOX_CLIENT_SECRET"]

API_URL = secrets.get(
    "GLAMOX_API_URL", "https://api-1.glamoxheating.com/client-api")

# --- hent token ---
r = requests.post(
    f"{API_URL}/auth/token",
    data={"grant_type": "password",
          "username": CLIENT_ID, "password": CLIENT_SECRET},
    timeout=20,
)
r.raise_for_status()
token = r.json()["access_token"]

headers = {"Authorization": f"Bearer {token}"}

# --- hent status ---
resp = requests.get(f"{API_URL}/rest/v1/content/", headers=headers, timeout=20)
resp.raise_for_status()
data = resp.json()

print("== Romstatus ==")
for room in data.get("rooms", []):
    name = room["name"]
    temp = room.get("temperature", 0) / 100.0
    target = room.get("targetTemperature", 0) / 100.0
    print(f"{name:20s} nå {temp:.1f}°C  →  mål {target:.1f}°C")
