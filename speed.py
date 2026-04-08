#!/usr/bin/env python3
import argparse
import datetime as dt
import json
import time
from pathlib import Path
from typing import Any, Dict, List

import requests
from google.auth.transport.requests import Request as GoogleAuthRequest
from google.oauth2 import service_account


DEFAULT_CONFIG_PATH = "config/config.json"
CALENDAR_SCOPE = "https://www.googleapis.com/auth/calendar.readonly"
CALENDAR_EVENTS_URL = "https://www.googleapis.com/calendar/v3/calendars/{calendar_id}/events"


def load_config(base_dir: Path, config_path: str) -> Dict[str, Any]:
    path = Path(config_path)
    if not path.is_absolute():
        path = base_dir / path
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def resolve_path(base_dir: Path, path: str) -> Path:
    p = Path(path)
    if p.is_absolute():
        return p
    return base_dir / p


def get_access_token(base_dir: Path, cfg: Dict[str, Any]) -> str:
    scopes = cfg["google"].get("scopes") or [CALENDAR_SCOPE]
    key_file = resolve_path(base_dir, cfg["google"]["key_file"])
    creds = service_account.Credentials.from_service_account_file(str(key_file), scopes=scopes)
    creds.refresh(GoogleAuthRequest())
    if not creds.token:
        raise RuntimeError("failed to obtain access token")
    return creds.token


def fetch_events(
    session: requests.Session,
    token: str,
    calendar_id: str,
    start: dt.datetime,
    end: dt.datetime,
) -> List[Dict[str, Any]]:
    url = CALENDAR_EVENTS_URL.format(calendar_id=calendar_id)
    headers = {"Authorization": f"Bearer {token}"}
    params = {
        "timeMin": start.isoformat().replace("+00:00", "Z"),
        "timeMax": end.isoformat().replace("+00:00", "Z"),
        "singleEvents": "true",
        "orderBy": "startTime",
    }
    resp = session.get(url, headers=headers, params=params, timeout=20)
    resp.raise_for_status()
    return resp.json().get("items", [])


def timed(name: str, timings: Dict[str, float], fn):
    start = time.perf_counter()
    out = fn()
    timings[name] = (time.perf_counter() - start) * 1000.0
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Fast calendar fetch benchmark (google-auth + requests)")
    parser.add_argument("--config", default=DEFAULT_CONFIG_PATH, help="Path to config file")
    parser.add_argument("--hours", type=int, default=2, help="Lookahead window in hours")
    args = parser.parse_args()

    base_dir = Path(__file__).resolve().parent
    cfg = load_config(base_dir, args.config)

    calendar_id = cfg["google"]["calendar_id"]
    pray_id = cfg["google"]["pray_id"]
    if not calendar_id or not pray_id:
        raise ValueError("google.calendar_id and google.pray_id are required")

    now = dt.datetime.now(dt.UTC)
    end = now + dt.timedelta(hours=args.hours)

    timings: Dict[str, float] = {}
    session = requests.Session()
    try:
        token = timed("auth_token", timings, lambda: get_access_token(base_dir, cfg))
        events_storsalen = timed(
            "calendar_storsalen",
            timings,
            lambda: fetch_events(session, token, calendar_id, now, end),
        )
        events_pray = timed(
            "calendar_pray",
            timings,
            lambda: fetch_events(session, token, pray_id, now, end),
        )
    finally:
        session.close()

    print(f"storsalen_events={len(events_storsalen)}")
    print(f"pray_events={len(events_pray)}")
    summary = ", ".join(f"{k}={v:.1f}ms" for k, v in sorted(timings.items(), key=lambda kv: kv[1], reverse=True))
    print(f"Timing summary: {summary}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
