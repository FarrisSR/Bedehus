#!/usr/bin/env python3
import sys
from glamox.common import load_secrets, auth, get_rooms, find_room_id, set_room_target, wait_until_reflected

if len(sys.argv) < 3:
    print("Bruk: glamox_set.py <romnavn> <temperatur_C> [--no-verify]")
    raise SystemExit(2)

room_name = sys.argv[1]
target_c = float(sys.argv[2])
verify = "--no-verify" not in sys.argv

s = load_secrets()
token = auth(s["API_URL"], s["ACCOUNT_ID"], s["API_PASSWORD"])

rooms = get_rooms(s["API_URL"], token)
rid = find_room_id(rooms, room_name)
if rid is None:
    print("Fant ikke rommet. Tilgjengelige rom:")
    for r in rooms:
        print(" -", r.get("name"))
    raise SystemExit(1)

set_room_target(s["API_URL"], token, rid, target_c)
msg = f"→ Satt {room_name} til {target_c:.1f}°C (room_id={rid})"
if verify:
    ok = wait_until_reflected(s["API_URL"], token, rid, target_c)
    msg += " ✓ bekreftet" if ok else " (advarsel: ikke reflektert ennå)"
print(msg)
