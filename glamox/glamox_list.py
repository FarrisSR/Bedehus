#!/usr/bin/env python3
from glamox.common import load_secrets, auth, get_rooms

s = load_secrets()
token = auth(s["API_URL"], s["ACCOUNT_ID"], s["API_PASSWORD"])
rooms = get_rooms(s["API_URL"], token)

print("== Romstatus ==")
for room in rooms:
    name = room.get("name", f"id:{room.get('id')}")
    temp = (room.get("temperature") or 0)/100.0
    tgt = (room.get("targetTemperature") or 0)/100.0
