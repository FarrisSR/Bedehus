# glamox/common.py
from __future__ import annotations
import os
import json
import time
from pathlib import Path
from typing import Optional, List, Dict, Any
import requests

DEFAULT_API = "https://api-1.glamoxheating.com/client-api"
DEFAULT_TIMEOUT = 20

__all__ = [
    "load_secrets",
    "auth",
    "get_rooms",
    "set_room_target",
    "find_room_id",
    "wait_until_reflected",
]


def load_secrets() -> dict:
    """
    Leser secrets fra første match blant:
      - $GLAMOX_SECRETS
      - ../secrets/secrets.json
      - ../secrets.json
      - ./secrets.json
    Støtter begge skjema:
      {ACCOUNT_ID, API_PASSWORD, API_URL}
      {GLAMOX_CLIENT_ID, GLAMOX_CLIENT_SECRET, GLAMOX_API_URL}
    Returnerer: {"ACCOUNT_ID": str, "API_PASSWORD": str, "API_URL": str}
    """
    base = Path(__file__).resolve().parent
    candidates = []
    if os.getenv("GLAMOX_SECRETS"):
        candidates.append(Path(os.getenv("GLAMOX_SECRETS")))
    candidates += [
        base.parent / "secrets" / "secrets.json",
        base.parent / "secrets.json",
        base / "secrets.json",
    ]
    for p in candidates:
        if p.exists():
            with open(p, "r", encoding="utf-8") as f:
                raw = json.load(f)

            # Nytt skjema
            if "ACCOUNT_ID" in raw and "API_PASSWORD" in raw:
                return {
                    "ACCOUNT_ID": str(raw["ACCOUNT_ID"]),
                    "API_PASSWORD": raw["API_PASSWORD"],
                    "API_URL": raw.get("API_URL", DEFAULT_API).rstrip("/"),
                }
            # Gammelt skjema
            if "GLAMOX_CLIENT_ID" in raw and "GLAMOX_CLIENT_SECRET" in raw:
                return {
                    "ACCOUNT_ID": str(raw["GLAMOX_CLIENT_ID"]),
                    "API_PASSWORD": raw["GLAMOX_CLIENT_SECRET"],
                    "API_URL": raw.get("GLAMOX_API_URL", DEFAULT_API).rstrip("/"),
                }
            raise RuntimeError(
                f"Fant secrets-fil, men kjente nøkler mangler: {p}")
    raise FileNotFoundError(
        "Fant ingen secrets.json. Sett GLAMOX_SECRETS eller legg ../secrets.json / ../secrets/secrets.json"
    )


def auth(api_url: str, account_id: str, api_password: str, timeout: int = DEFAULT_TIMEOUT) -> str:
    """Hent access_token via password-grant."""
    r = requests.post(
        f"{api_url}/auth/token",
        data={"grant_type": "password", "username": str(
            account_id), "password": api_password},
        timeout=timeout,
    )
    r.raise_for_status()
    return r.json()["access_token"]


def _headers(token: str) -> Dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def get_rooms(api_url: str, token: str, with_energy: bool = False, timeout: int = DEFAULT_TIMEOUT) -> List[Dict[str, Any]]:
    params = {"withEnergy": 1} if with_energy else None
    r = requests.get(f"{api_url}/rest/v1/content/",
                     headers=_headers(token), params=params, timeout=timeout)
    r.raise_for_status()
    return r.json().get("rooms", [])


def set_room_target(api_url: str, token: str, room_id: int, target_c: float, timeout: int = DEFAULT_TIMEOUT) -> None:
    centi = int(round(target_c * 100))
    payload = {"rooms": [{"id": room_id, "targetTemperature": str(centi)}]}
    r = requests.post(f"{api_url}/rest/v1/control/",
                      headers=_headers(token), json=payload, timeout=timeout)
    r.raise_for_status()


def find_room_id(rooms: List[Dict[str, Any]], name: str) -> Optional[int]:
    for r in rooms:
        if r.get("name") == name:
            return r.get("id")
    return None


def wait_until_reflected(
    api_url: str,
    token: str,
    room_id: int,
    target_c: float,
    timeout_s: int = 40,
    poll_interval_s: float = 2.0,
) -> bool:
    """
    Poller /content til targetTemperature samsvarer med ønsket verdi (avrundet til 0.1°C).
    Returnerer True ved treff, False ved timeout.
    """
    want = round(target_c, 1)
    end = time.time() + timeout_s
    while time.time() < end:
        rooms = get_rooms(api_url, token)
        for r in rooms:
            if r.get("id") == room_id:
                got = round((r.get("targetTemperature") or 0) / 100.0, 1)
                if got == want:
                    return True
        time.sleep(poll_interval_s)
    return False
