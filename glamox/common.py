# glamox/common.py
import os
import json
import requests
from pathlib import Path
from typing import Dict, Any, List, Optional

DEFAULT_API = "https://api-1.glamoxheating.com/client-api"


def load_secrets() -> dict:
    base = Path(__file__).resolve().parent
    candidates = [
        # Path(os.getenv("GLAMOX_SECRETS", "")),
        # base.parent / "secrets" / "secrets.json",
        base.parent / "secrets.json",
        base / "secrets.json",
    ]
    for p in candidates:
        if p and p.exists():
            raw = json.loads(p.read_text())
            if "ACCOUNT_ID" in raw and "API_PASSWORD" in raw:
                return {"ACCOUNT_ID": str(raw["ACCOUNT_ID"]),
                        "API_PASSWORD": raw["API_PASSWORD"],
                        "API_URL": raw.get("API_URL", DEFAULT_API).rstrip("/")}
            if "GLAMOX_CLIENT_ID" in raw and "GLAMOX_CLIENT_SECRET" in raw:
                return {"ACCOUNT_ID": str(raw["GLAMOX_CLIENT_ID"]),
                        "API_PASSWORD": raw["GLAMOX_CLIENT_SECRET"],
                        "API_URL": raw.get("GLAMOX_API_URL", DEFAULT_API).rstrip("/")}
    raise FileNotFoundError("Fant ingen secrets.json")


def auth(api_url: str, account_id: str, api_password: str, timeout: int = 20) -> str:
    r = requests.post(f"{api_url}/auth/token",
                      data={"grant_type": "password",
                            "username": account_id, "password": api_password},
                      timeout=timeout)
    r.raise_for_status()
    return r.json()["access_token"]


def list_rooms(api_url: str, token: str, timeout: int = 20) -> List[Dict[str, Any]]:
    r = requests.get(f"{api_url}/rest/v1/content/",
                     headers={"Authorization": f"Bearer {token}"}, timeout=timeout)
    r.raise_for_status()
    return r.json().get("rooms", [])


def resolve_room_id(api_url: str, token: str, room_name: str, timeout: int = 20) -> int:
    for r in list_rooms(api_url, token, timeout=timeout):
        if r.get("name") == room_name:
            return int(r["id"])
    raise RuntimeError(f"Fant ikke rom '{room_name}' i Glamox-appen.")


def get_room_status(api_url: str, token: str, room_id: int, timeout: int = 20) -> Dict[str, Any]:
    # Vi henter /content og finner kun det rommet vi vil ha
    for r in list_rooms(api_url, token, timeout=timeout):
        if int(r.get("id")) == int(room_id):
            return {
                "room": r.get("name"),
                "id": int(r.get("id")),
                "temperature": (r.get("temperature") or 0)/100.0,
                "targetTemperature": (r.get("targetTemperature") or 0)/100.0,
            }
    raise RuntimeError(f"Room id {room_id} ikke funnet")


def set_room_target(api_url: str, token: str, room_id: int, target_c: float, timeout: int = 20) -> Dict[str, Any]:
    centi = int(round(float(target_c) * 100))
    payload = {
        "rooms": [{"id": int(room_id), "targetTemperature": str(centi)}]}
    r = requests.post(f"{api_url}/rest/v1/control/",
                      headers={"Authorization": f"Bearer {token}"},
                      json=payload, timeout=timeout)
    r.raise_for_status()
    return {"ok": True, "requested": payload}

# Convenience helpers (bruker navn → cacher id i kalleren)


def get_room_status_by_name(api_url: str, token: str, room_name: str, timeout: int = 20) -> Dict[str, Any]:
    rid = resolve_room_id(api_url, token, room_name, timeout=timeout)
    return get_room_status(api_url, token, rid, timeout=timeout)


def set_room_target_by_name(api_url: str, token: str, room_name: str, target_c: float, timeout: int = 20) -> Dict[str, Any]:
    rid = resolve_room_id(api_url, token, room_name, timeout=timeout)
    return set_room_target(api_url, token, rid, target_c, timeout=timeout)
