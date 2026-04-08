#!/usr/bin/env python3
"""
Henter temperatur og target fra Mill (cloud) og Glamox, lagrer til SQLite og kan generere grafer.

Eksempel:
    python3 scripts/temperature_logger.py log --glamox-room Storsalen --mill-device-id 12345 \\
        --mill-username your@mail --mill-password secret
    python3 scripts/temperature_logger.py plot --hours 48 --output graphs/last_48h.png
"""
import argparse
import datetime as dt
import json
import math
import os
import sqlite3
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple
from zoneinfo import ZoneInfo

import requests

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from glamox.glamox_controller import glamox_controller

DEFAULT_DB = Path("data/temperature_history.sqlite")
# Dokumentasjon sier /customer/auth/sign-in og /devices/type. Ingen /share/app her.
DEFAULT_MILL_API = "https://api.millnorwaycloud.com"
DEFAULT_YR_LAT = 59.885
DEFAULT_YR_LON = 11.567
# Ca. høyde over havet i Bjørkelangen-området.
DEFAULT_YR_ALTITUDE = 130
DISPLAY_TZ = ZoneInfo("Europe/Oslo")
YR_API_URL = "https://api.met.no/weatherapi/locationforecast/2.0/compact"
YR_USER_AGENT = (
    "BedehusGlamox/1.0 (https://github.com/FarrisSR/Bedehus-glamox; contact: runo)"
)
MILL_DEVICE_TYPES = [
    "GL-Air Purifier L",
    "GL-Air Purifier M",
    "AU-Air Purifier L",
    "AU-Air Purifier M",
    "KR-Air Purifier L",
    "KR-Air Purifier M",
    "GL-Oil Heater G3",
    "GL-Oil Heater G3 V2",
    "GL-Oil Heater G2",
    "GL-Panel Heater G4",
    "GL-Panel Heater G3 M",
    "GL-Panel Heater G3 MV2",
    "GL-Panel Heater G3",
    "GL-Panel Heater G2",
    "GL-Panel Heater G1",
    "AU-Panel Heater G3",
    "GL-WIFI Convection MAX 1500W G3",
    "GL-Convection Heater G3",
    "GL-Convection Heater G2",
    "GL-WIFI Socket G4",
    "GL-WIFI Socket G3",
    "GL-WIFI Socket G2",
    "GL-WIFI Floor G4",
]

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS readings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    recorded_at TEXT NOT NULL,
    source TEXT NOT NULL,
    room TEXT NOT NULL,
    temperature_c REAL,
    target_c REAL,
    raw JSON
);
"""

CREATE_UNIQUE_INDEX_SQL = """
CREATE UNIQUE INDEX IF NOT EXISTS idx_readings_source_room_recorded_at
ON readings (source, room, recorded_at);
"""

CREATE_RECORDED_AT_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_readings_recorded_at
ON readings (recorded_at);
"""

CREATE_HEATER_PRESENCE_EVENTS_SQL = """
CREATE TABLE IF NOT EXISTS heater_presence_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    recorded_at TEXT NOT NULL,
    recorded_hour TEXT NOT NULL,
    alias TEXT NOT NULL,
    mac TEXT,
    ip TEXT,
    scanner TEXT,
    online INTEGER NOT NULL,
    raw JSON
);
"""

CREATE_HEATER_PRESENCE_EVENTS_UNIQUE_SQL = """
CREATE UNIQUE INDEX IF NOT EXISTS idx_heater_presence_events_recorded_at_alias
ON heater_presence_events (recorded_at, alias);
"""

CREATE_HEATER_PRESENCE_EVENTS_HOUR_SQL = """
CREATE INDEX IF NOT EXISTS idx_heater_presence_events_recorded_hour
ON heater_presence_events (recorded_hour);
"""

CREATE_HEATER_PRESENCE_HOURLY_SQL = """
CREATE TABLE IF NOT EXISTS heater_presence_hourly (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    recorded_hour TEXT NOT NULL,
    alias TEXT NOT NULL,
    online INTEGER NOT NULL,
    observed_at TEXT,
    mac TEXT,
    ip TEXT,
    scanner TEXT,
    raw JSON
);
"""

CREATE_HEATER_PRESENCE_HOURLY_UNIQUE_SQL = """
CREATE UNIQUE INDEX IF NOT EXISTS idx_heater_presence_hourly_hour_alias
ON heater_presence_hourly (recorded_hour, alias);
"""

CREATE_HEATER_PRESENCE_HOURLY_HOUR_SQL = """
CREATE INDEX IF NOT EXISTS idx_heater_presence_hourly_recorded_hour
ON heater_presence_hourly (recorded_hour);
"""


@dataclass
class Reading:
    source: str
    room: str
    temperature_c: float
    target_c: Optional[float]
    recorded_at: dt.datetime
    raw: Dict[str, Any]

    @classmethod
    def from_row(cls, row: Tuple[Any, ...]) -> "Reading":
        _, recorded_at, source, room, temperature_c, target_c, raw = row
        target_value = None if target_c is None else float(target_c)
        return cls(
            source=source,
            room=room,
            temperature_c=float(temperature_c),
            target_c=target_value,
            recorded_at=dt.datetime.fromisoformat(recorded_at),
            raw=json.loads(raw) if raw else {},
        )


@dataclass
class HeaterOnlineCount:
    recorded_at: dt.datetime
    online_count: int
    expected_count: int


@dataclass
class HeaterPresenceStatus:
    recorded_at: dt.datetime
    alias: str
    online: bool
    observed_at: Optional[dt.datetime]
    mac: Optional[str]
    ip: Optional[str]
    scanner: Optional[str]


def utc_now_naive() -> dt.datetime:
    # Hold SQLite-formatet som naiv UTC for bakoverkompatibilitet med eksisterende rader.
    return dt.datetime.now(dt.UTC).replace(tzinfo=None)


def ensure_db(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute(CREATE_TABLE_SQL)
    conn.execute(CREATE_HEATER_PRESENCE_EVENTS_SQL)
    conn.execute(CREATE_HEATER_PRESENCE_HOURLY_SQL)
    deleted = cleanup_duplicate_readings(conn)
    conn.execute(CREATE_UNIQUE_INDEX_SQL)
    conn.execute(CREATE_RECORDED_AT_INDEX_SQL)
    conn.execute(CREATE_HEATER_PRESENCE_EVENTS_UNIQUE_SQL)
    conn.execute(CREATE_HEATER_PRESENCE_EVENTS_HOUR_SQL)
    conn.execute(CREATE_HEATER_PRESENCE_HOURLY_UNIQUE_SQL)
    conn.execute(CREATE_HEATER_PRESENCE_HOURLY_HOUR_SQL)
    conn.commit()
    if deleted:
        print(f"Ryddet {deleted} duplikate temperaturmålinger i {db_path}", file=sys.stderr)
    return conn


def cleanup_duplicate_readings(conn: sqlite3.Connection) -> int:
    cur = conn.execute(
        """
        DELETE FROM readings
        WHERE id IN (
            SELECT id
            FROM (
                SELECT id,
                       ROW_NUMBER() OVER (
                           PARTITION BY source, room, recorded_at
                           ORDER BY id DESC
                       ) AS row_num
                FROM readings
            )
            WHERE row_num > 1
        )
        """
    )
    deleted = cur.rowcount or 0
    if deleted:
        conn.commit()
    return deleted


def insert_reading(conn: sqlite3.Connection, reading: Reading) -> None:
    conn.execute(
        """
        INSERT INTO readings (recorded_at, source, room, temperature_c, target_c, raw)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(source, room, recorded_at) DO UPDATE SET
            temperature_c = excluded.temperature_c,
            target_c = excluded.target_c,
            raw = excluded.raw
        """,
        (
            reading.recorded_at.isoformat(),
            reading.source,
            reading.room,
            reading.temperature_c,
            reading.target_c,
            json.dumps(reading.raw),
        ),
    )
    conn.commit()


def fetch_readings(
    conn: sqlite3.Connection,
    hours: Optional[int] = None,
    source: Optional[str] = None,
    room: Optional[str] = None,
) -> List[Reading]:
    query = "SELECT * FROM readings"
    clauses: List[str] = []
    params: List[Any] = []

    if hours is not None:
        since = utc_now_naive() - dt.timedelta(hours=hours)
        clauses.append("recorded_at >= ?")
        params.append(since.isoformat())
    if source:
        clauses.append("source = ?")
        params.append(source)
    if room:
        clauses.append("room = ?")
        params.append(room)

    if clauses:
        query += " WHERE " + " AND ".join(clauses)
    query += " ORDER BY recorded_at ASC"

    cur = conn.execute(query, params)
    return [Reading.from_row(row) for row in cur.fetchall()]


def fetch_heater_online_counts(
    conn: sqlite3.Connection,
    hours: Optional[int] = None,
) -> List[HeaterOnlineCount]:
    query = """
        SELECT recorded_hour, SUM(online) AS online_count, COUNT(*) AS expected_count
        FROM heater_presence_hourly
    """
    params: List[Any] = []
    clauses: List[str] = []
    if hours is not None:
        since = utc_now_naive() - dt.timedelta(hours=hours)
        clauses.append("recorded_hour >= ?")
        params.append(since.replace(minute=0, second=0, microsecond=0).isoformat())
    if clauses:
        query += " WHERE " + " AND ".join(clauses)
    query += " GROUP BY recorded_hour ORDER BY recorded_hour ASC"

    cur = conn.execute(query, params)
    return [
        HeaterOnlineCount(
            recorded_at=dt.datetime.fromisoformat(recorded_hour),
            online_count=int(online_count or 0),
            expected_count=int(expected_count or 0),
        )
        for recorded_hour, online_count, expected_count in cur.fetchall()
    ]


def fetch_latest_heater_presence_statuses(conn: sqlite3.Connection) -> List[HeaterPresenceStatus]:
    row = conn.execute("SELECT MAX(recorded_hour) FROM heater_presence_hourly").fetchone()
    latest_hour = row[0] if row else None
    if not latest_hour:
        return []

    cur = conn.execute(
        """
        SELECT recorded_hour, alias, online, observed_at, mac, ip, scanner
        FROM heater_presence_hourly
        WHERE recorded_hour = ?
        ORDER BY alias ASC
        """,
        (latest_hour,),
    )
    results: List[HeaterPresenceStatus] = []
    for recorded_hour, alias, online, observed_at, mac, ip, scanner in cur.fetchall():
        results.append(
            HeaterPresenceStatus(
                recorded_at=dt.datetime.fromisoformat(recorded_hour),
                alias=str(alias),
                online=bool(online),
                observed_at=dt.datetime.fromisoformat(observed_at) if observed_at else None,
                mac=mac,
                ip=ip,
                scanner=scanner,
            )
        )
    return results


def _extract_json_payload(line: str) -> Optional[Dict[str, Any]]:
    brace_index = line.find("{")
    if brace_index < 0:
        return None
    try:
        payload = json.loads(line[brace_index:])
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def load_arp_aliases(path: Path) -> List[str]:
    if not path.exists():
        return []

    aliases: List[str] = []
    seen: set[str] = set()
    for raw_line in path.read_text().splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line:
            continue
        columns = line.split()
        candidate = columns[-1]
        if not candidate.startswith("glamox_ovn_"):
            continue
        if candidate in seen:
            continue
        seen.add(candidate)
        aliases.append(candidate)
    return aliases


def import_arp_presence(
    conn: sqlite3.Connection,
    log_path: Path,
    aliases_path: Path,
) -> Dict[str, int]:
    if not log_path.exists():
        raise RuntimeError(f"Fant ikke ARP-logg: {log_path}")

    event_map: Dict[Tuple[dt.datetime, str], Dict[str, Any]] = {}
    event_rows = 0
    seen_aliases: set[str] = set()
    summary_hours: set[dt.datetime] = set()

    with log_path.open() as handle:
        for line in handle:
            payload = _extract_json_payload(line)
            if not payload:
                continue
            ts_value = payload.get("ts")
            if ts_value:
                try:
                    parsed = dt.datetime.fromisoformat(str(ts_value).replace("Z", "+00:00"))
                except ValueError:
                    parsed = None
                if parsed is not None:
                    recorded_at = parsed.astimezone(dt.UTC).replace(tzinfo=None)
                    summary_hours.add(recorded_at.replace(minute=0, second=0, microsecond=0))
            if payload.get("type") != "arp_presence":
                continue
            if payload.get("online") is not True:
                continue
            alias = payload.get("alias")
            if not alias or not ts_value:
                continue
            try:
                parsed = dt.datetime.fromisoformat(str(ts_value).replace("Z", "+00:00"))
            except ValueError:
                continue
            recorded_at = parsed.astimezone(dt.UTC).replace(tzinfo=None)
            recorded_hour = recorded_at.replace(minute=0, second=0, microsecond=0)
            seen_aliases.add(str(alias))
            conn.execute(
                """
                INSERT INTO heater_presence_events
                (recorded_at, recorded_hour, alias, mac, ip, scanner, online, raw)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(recorded_at, alias) DO UPDATE SET
                    recorded_hour = excluded.recorded_hour,
                    mac = excluded.mac,
                    ip = excluded.ip,
                    scanner = excluded.scanner,
                    online = excluded.online,
                    raw = excluded.raw
                """,
                (
                    recorded_at.isoformat(),
                    recorded_hour.isoformat(),
                    str(alias),
                    payload.get("mac"),
                    payload.get("ip"),
                    payload.get("scanner"),
                    1,
                    json.dumps(payload),
                ),
            )
            event_rows += 1
            key = (recorded_hour, str(alias))
            existing = event_map.get(key)
            if existing is None or recorded_at >= existing["recorded_at"]:
                event_map[key] = {
                    "recorded_at": recorded_at,
                    "payload": payload,
                }

    aliases = load_arp_aliases(aliases_path)
    if not aliases:
        aliases = sorted(seen_aliases)
        print(
            f"Fant ingen aliasfil i {aliases_path}; bruker aliaser observert i loggen.",
            file=sys.stderr,
        )

    hours = sorted(summary_hours or {hour for hour, _ in event_map})
    hourly_rows = 0
    for hour in hours:
        for alias in aliases:
            event = event_map.get((hour, alias))
            payload = event["payload"] if event else None
            conn.execute(
                """
                INSERT INTO heater_presence_hourly
                (recorded_hour, alias, online, observed_at, mac, ip, scanner, raw)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(recorded_hour, alias) DO UPDATE SET
                    online = excluded.online,
                    observed_at = excluded.observed_at,
                    mac = excluded.mac,
                    ip = excluded.ip,
                    scanner = excluded.scanner,
                    raw = excluded.raw
                """,
                (
                    hour.isoformat(),
                    alias,
                    1 if event else 0,
                    event["recorded_at"].isoformat() if event else None,
                    payload.get("mac") if payload else None,
                    payload.get("ip") if payload else None,
                    payload.get("scanner") if payload else None,
                    json.dumps(payload) if payload else None,
                ),
            )
            hourly_rows += 1

    conn.commit()
    return {
        "events_seen": event_rows,
        "hours_written": len(hours),
        "aliases_used": len(aliases),
        "hourly_rows_written": hourly_rows,
    }


def load_secrets(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError:
        raise RuntimeError(f"Ugyldig JSON i {path}")


def resolve_secret(
    name: str, cli_value: Optional[str], secrets: Dict[str, Any]
) -> Optional[str]:
    return cli_value or os.getenv(name) or secrets.get(name)


class MillCloudClient:
    """
    Minimal klient mot Mill-cloud. Endepunkter kan variere mellom kontoer/regioner,
    så juster base_url eller tilpass fetch_device_status til strukturen du får tilbake.
    """

    def __init__(
        self,
        username: str,
        password: str,
        base_url: str = DEFAULT_MILL_API,
        timeout: int = 20,
    ):
        self.username = username
        self.password = password
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._token: Optional[str] = None
        self._refresh: Optional[str] = None
        self._token_expires_at: Optional[dt.datetime] = None
        self.session = requests.Session()

    def _parse_tokens(self, payload: Dict[str, Any]) -> Tuple[str, Optional[str], Optional[int]]:
        """
        Forsøker å trekke ut access token, refresh token og evt. utløpstid (sek).
        """
        data = payload.get("data", payload)
        token = (
            data.get("token")
            or data.get("access_token")
            or data.get("accessToken")
            or data.get("idToken")
            or data.get("jwt")
            or data.get("jwtToken")
            or (data.get("token") or {}).get("accessToken")
        )
        refresh = (
            data.get("refreshToken")
            or data.get("refresh_token")
            or (data.get("token") or {}).get("refreshToken")
        )
        expires = data.get("expiresIn") or data.get("expires_in")
        if not token:
            raise RuntimeError(f"Fant ikke access token i responsen: {payload}")
        return (
            str(token),
            refresh,
            int(expires) if expires is not None else None,
        )

    def _sign_in(self) -> None:
        resp = self.session.post(
            f"{self.base_url}/customer/auth/sign-in",
            json={"login": self.username, "password": self.password},
            timeout=self.timeout,
        )
        if resp.status_code >= 400:
            raise RuntimeError(
                f"Login feilet ({resp.status_code}): {resp.text}"
            )
        try:
            payload = resp.json()
        except ValueError:
            raise RuntimeError(f"Uventet login-respons (ikke JSON): {resp.text}") from None
        token, refresh, expires = self._parse_tokens(payload)
        if expires is None:
            expires = 600  # fallback; dokumentasjon sier 600s
        self._token = token
        self._refresh = refresh
        if expires:
            self._token_expires_at = dt.datetime.now(dt.UTC) + dt.timedelta(seconds=expires - 30)
        self.session.headers.update({"Authorization": f"Bearer {self._token}"})

    def _refresh_token(self) -> None:
        if not self._refresh:
            self._sign_in()
            return
        resp = self.session.post(
            f"{self.base_url}/customer/auth/refresh",
            json={"refreshToken": self._refresh},
            timeout=self.timeout,
        )
        if resp.status_code == 401:
            # refresh er ugyldig; prøv full sign-in
            self._sign_in()
            return
        if resp.status_code >= 400:
            raise RuntimeError(
                f"Refresh feilet ({resp.status_code}): {resp.text}"
            )
        token, refresh, expires = self._parse_tokens(resp.json())
        if expires is None:
            expires = 600  # fallback
        self._token = token
        self._refresh = refresh or self._refresh
        if expires:
            self._token_expires_at = dt.datetime.now(dt.UTC) + dt.timedelta(seconds=expires - 30)
        self.session.headers.update({"Authorization": f"Bearer {self._token}"})

    def ensure_login(self) -> None:
        if not self._token:
            self._sign_in()
            return
        if self._token_expires_at and dt.datetime.now(dt.UTC) >= self._token_expires_at:
            self._refresh_token()

    def fetch_device_status(self, device_id: str) -> Dict[str, Any]:
        """
        Leser detaljer for en gitt ovn. Responsformat varierer; vi forsøker å
        tolke felter for temperatur og target.
        """
        self.ensure_login()
        resp = self.session.get(
            f"{self.base_url}/devices/{device_id}/data", timeout=self.timeout
        )
        resp.raise_for_status()
        return resp.json()

    def list_devices(self) -> List[Dict[str, Any]]:
        """Returnerer rå liste over alle devices i kontoen."""
        self.ensure_login()
        all_devices: List[Dict[str, Any]] = []
        seen_ids = set()
        debug_calls: List[str] = []
        base_variants = ["", "/customer"]
        for dev_type in MILL_DEVICE_TYPES:
            for base_prefix in base_variants:
                for url in (
                    f"{self.base_url}{base_prefix}/devices/type",
                    f"{self.base_url}{base_prefix}/devices/type/{dev_type}",
                ):
                    resp = self.session.get(
                        url,
                        params={"type": dev_type} if "type/" not in url else None,
                        timeout=self.timeout,
                    )
                    debug_calls.append(f"{resp.status_code} {url} → {resp.text[:150]}")
                    if resp.status_code in (404, 400):
                        continue
                    if resp.status_code >= 400:
                        raise RuntimeError(
                            f"/devices/type feilet ({resp.status_code}) for {dev_type}: {resp.text}"
                        )
                    payload = resp.json()
                    if isinstance(payload, list):
                        items = payload
                    elif "data" in payload and isinstance(payload["data"], list):
                        items = payload["data"]
                    elif "devices" in payload and isinstance(payload["devices"], list):
                        items = payload["devices"]
                    elif "items" in payload and isinstance(payload["items"], list):
                        items = payload["items"]
                    else:
                        items = []
                    if items:
                        break
                else:
                    items = []
                for item in items:
                    item_id = item.get("id")
                    if item_id in seen_ids:
                        continue
                    seen_ids.add(item_id)
                    all_devices.append(item)
        if not all_devices:
            # Siste forsøk: kall /devices uten type
            for base_prefix in base_variants:
                resp = self.session.get(f"{self.base_url}{base_prefix}/devices", timeout=self.timeout)
                debug_calls.append(f"{resp.status_code} {self.base_url}{base_prefix}/devices → {resp.text[:150]}")
                if resp.status_code < 400:
                    payload = resp.json()
                    if isinstance(payload, list):
                        return payload
                    if "data" in payload and isinstance(payload["data"], list):
                        return payload["data"]
                    if "devices" in payload and isinstance(payload["devices"], list):
                        return payload["devices"]
                    if "items" in payload and isinstance(payload["items"], list):
                        return payload["items"]
            raise RuntimeError(
                "Fant ingen devices via /devices/type med kjente typer eller /devices. "
                f"Prøv annen base-URL eller oppdater MILL_DEVICE_TYPES. "
                f"Siste /devices-status: {resp.status_code} {resp.text}. "
                f"Forsøk: {debug_calls}"
            )
        return all_devices

    def list_houses(self) -> List[Dict[str, Any]]:
        """Returnerer liste over egne og delte hus."""
        self.ensure_login()
        resp = self.session.get(f"{self.base_url}/houses", timeout=self.timeout)
        resp.raise_for_status()
        payload = resp.json()
        houses: List[Dict[str, Any]] = []
        houses.extend(payload.get("ownHouses") or [])
        houses.extend(payload.get("sharedHouses") or [])
        return houses

    def list_devices_for_house(self, house_id: str) -> List[Dict[str, Any]]:
        """
        Returnerer alle devices for et hus, med roomName/husnavn inkludert.
        """
        self.ensure_login()
        resp = self.session.get(
            f"{self.base_url}/houses/{house_id}/devices", timeout=self.timeout
        )
        resp.raise_for_status()
        payload = resp.json()
        results: List[Dict[str, Any]] = []
        for room_entry in payload or []:
            room_name = room_entry.get("roomName")
            room_id = room_entry.get("roomId")
            for dev in room_entry.get("devices") or []:
                enriched = dict(dev)
                enriched.setdefault("roomName", room_name)
                enriched.setdefault("roomId", room_id)
                results.append(enriched)
        return results

    @staticmethod
    def extract_temp(payload: Dict[str, Any]) -> Tuple[float, float]:
        """
        Prøver å finne aktuell og måltemperatur i responsen.
        Du kan justere denne hvis feltnavnene avviker.
        """
        # Foretrukket: live metrics
        metrics = payload.get("lastMetrics") or {}
        settings = payload.get("deviceSettings", {}).get("reported", {})
        if "temperature" in metrics:
            current = float(metrics.get("temperature"))
            target_candidates = [
                settings.get("temperature_last_set"),
                settings.get("temperature_normal"),
                settings.get("temperature_comfort"),
            ]
            for t in target_candidates:
                if t is not None:
                    return current, float(t)
        # Generelle fallback-kandidater
        candidates = [
            ("temperature", "targetTemperature"),
            ("currentTemp", "targetTemp"),
            ("currentTemperature", "targetTemperature"),
            ("roomTemp", "comfortTemp"),
        ]
        for temp_key, target_key in candidates:
            if temp_key in payload and target_key in payload:
                return float(payload[temp_key]), float(payload[target_key])
        if "data" in payload:
            for temp_key, target_key in candidates:
                inner = payload["data"]
                if temp_key in inner and target_key in inner:
                    return float(inner[temp_key]), float(inner[target_key])
        raise RuntimeError("Finner ikke temperaturfelter i Mill-responsen")


def fetch_glamox_reading(room_name: str) -> Reading:
    ctrl = glamox_controller(room_name)
    status = ctrl.get_control_status()
    if not status:
        raise RuntimeError(f"Ingen status mottatt fra Glamox for {room_name}")
    now = utc_now_naive()
    return Reading(
        source="glamox",
        room=status.get("room") or room_name,
        temperature_c=float(status.get("temperature") or 0.0),
        target_c=float(status.get("targetTemperature") or 0.0),
        recorded_at=now,
        raw=status,
    )


def fetch_mill_reading(
    client: MillCloudClient, device_id: str, room_name: Optional[str] = None
) -> Reading:
    payload = client.fetch_device_status(device_id)
    current, target = client.extract_temp(payload)
    now = utc_now_naive()
    resolved_room = room_name or str(payload.get("name") or payload.get("roomName") or device_id)
    return Reading(
        source="mill",
        room=resolved_room,
        temperature_c=current,
        target_c=target,
        recorded_at=now,
        raw=payload,
    )


def fetch_yr_outdoor_temperature(
    lat: float,
    lon: float,
    place_name: str,
    altitude: Optional[float] = None,
) -> Reading:
    """
    Henter utetemperatur fra Yr (MET) for gitt lokasjon.
    """
    params: Dict[str, Any] = {"lat": lat, "lon": lon}
    if altitude is not None:
        params["altitude"] = altitude
    headers = {"User-Agent": YR_USER_AGENT}
    resp = requests.get(YR_API_URL, params=params, headers=headers, timeout=20)
    resp.raise_for_status()
    payload = resp.json()
    timeseries = payload.get("properties", {}).get("timeseries") or []
    if not timeseries:
        raise RuntimeError("Yr-respons mangler timeserier")
    latest = timeseries[0]
    details = latest.get("data", {}).get("instant", {}).get("details") or {}
    temperature = details.get("air_temperature")
    if temperature is None:
        raise RuntimeError("Yr-respons mangler air_temperature i instant.details")
    time_str = latest.get("time")
    if time_str:
        parsed_time = dt.datetime.fromisoformat(time_str.replace("Z", "+00:00"))
        recorded_at = parsed_time.astimezone(dt.UTC).replace(tzinfo=None)
    else:
        recorded_at = utc_now_naive()
    return Reading(
        source="yr",
        room=place_name,
        temperature_c=float(temperature),
        target_c=None,
        recorded_at=recorded_at,
        raw={"meta": payload.get("properties", {}).get("meta"), "time": time_str},
    )


def plot_history(
    readings: Iterable[Reading],
    output: Path,
    max_points: int = 800,
    heater_counts: Optional[List[HeaterOnlineCount]] = None,
) -> None:
    import matplotlib.dates as mdates
    import matplotlib.pyplot as plt

    series: Dict[Tuple[str, str], List[Reading]] = {}
    for reading in readings:
        key = (reading.source, reading.room)
        series.setdefault(key, []).append(reading)

    if not series:
        raise RuntimeError("Ingen målinger å plotte")

    def gap_threshold(points: List[dt.datetime]) -> Optional[dt.timedelta]:
        if len(points) < 2:
            return None
        deltas = sorted(
            [
                points[idx] - points[idx - 1]
                for idx in range(1, len(points))
                if points[idx] > points[idx - 1]
            ]
        )
        if not deltas:
            return None
        typical = deltas[len(deltas) // 2]
        return max(typical * 3, dt.timedelta(hours=1))

    def split_on_gaps(
        points: List[dt.datetime], values: List[float]
    ) -> List[Tuple[List[dt.datetime], List[float]]]:
        threshold = gap_threshold(points)
        if threshold is None:
            return [(points, values)] if points else []

        segments: List[Tuple[List[dt.datetime], List[float]]] = []
        current_times = [points[0]]
        current_values = [values[0]]
        for idx in range(1, len(points)):
            if points[idx] - points[idx - 1] > threshold:
                segments.append((current_times, current_values))
                current_times = []
                current_values = []
            current_times.append(points[idx])
            current_values.append(values[idx])
        segments.append((current_times, current_values))
        return segments

    def downsample(times: List[dt.datetime], values: List[float]) -> Tuple[List[dt.datetime], List[float]]:
        if max_points is None or len(times) <= max_points:
            return times, values
        step = max(1, math.ceil(len(times) / max_points))
        ds_times = times[::step]
        ds_values = values[::step]
        if ds_times[-1] != times[-1]:
            ds_times.append(times[-1])
            ds_values.append(values[-1])
        return ds_times, ds_values

    fig, ax = plt.subplots(figsize=(10, 5))
    for (source, room), items in series.items():
        times = [r.recorded_at for r in items]
        temps = [r.temperature_c for r in items]
        label_base = f"{source}/{room}"
        temp_segments = split_on_gaps(times, temps)
        for idx, (segment_times, segment_temps) in enumerate(temp_segments):
            ds_times, ds_temps = downsample(segment_times, segment_temps)
            ax.plot(
                ds_times,
                ds_temps,
                label=f"{label_base} målt" if idx == 0 else None,
                marker="o",
                linewidth=1.0,
                markersize=3,
            )
        target_points = [(r.recorded_at, r.target_c) for r in items if r.target_c is not None]
        if target_points:
            target_times, targets = zip(*target_points)
            for idx, (segment_times, segment_targets) in enumerate(
                split_on_gaps(list(target_times), list(targets))
            ):
                ds_target_times, ds_targets = downsample(segment_times, segment_targets)
                ax.plot(
                    ds_target_times,
                    ds_targets,
                    linestyle="--",
                    label=f"{label_base} target" if idx == 0 else None,
                    marker="o",
                    linewidth=1.0,
                    markersize=3,
                )

    ax.set_ylabel("Temperatur (°C)")
    ax.set_xlabel("Tid (Europe/Oslo)")
    ax.set_title("Temperatur vs target")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d %H:%M", tz=DISPLAY_TZ))
    ax2 = None
    if heater_counts:
        ax2 = ax.twinx()
        count_times = [item.recorded_at for item in heater_counts]
        online_counts = [item.online_count for item in heater_counts]
        expected_counts = [item.expected_count for item in heater_counts]
        ax2.step(
            count_times,
            online_counts,
            where="post",
            label="Ovner online",
            linewidth=1.4,
            color="tab:green",
        )
        ax2.step(
            count_times,
            expected_counts,
            where="post",
            linestyle="--",
            label="Forventede ovner",
            linewidth=1.0,
            color="tab:gray",
        )
        max_count = max(expected_counts + online_counts)
        ax2.set_ylabel("Antall ovner")
        ax2.set_ylim(-0.2, max_count + 0.5)
    fig.autofmt_xdate()
    if ax2:
        handles1, labels1 = ax.get_legend_handles_labels()
        handles2, labels2 = ax2.get_legend_handles_labels()
        ax2.legend(handles1 + handles2, labels1 + labels2, loc="upper left")
    else:
        ax.legend()
    ax.grid(True)
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(output)


def handle_log(args: argparse.Namespace) -> None:
    secrets = load_secrets(Path(args.secrets))
    conn = ensure_db(Path(args.db))

    readings: List[Reading] = []

    for room in args.glamox_room or []:
        readings.append(fetch_glamox_reading(room))

    if args.mill_device_id:
        mill_username = resolve_secret("MILL_USERNAME", args.mill_username, secrets)
        mill_password = resolve_secret("MILL_PASSWORD", args.mill_password, secrets)
        if not mill_username or not mill_password:
            raise RuntimeError(
                "Mangler brukernavn/passord for Mill. "
                "Sett miljøvariabler MILL_USERNAME/MILL_PASSWORD eller legg dem i secrets.json."
            )
        mill_client = MillCloudClient(
            username=mill_username,
            password=mill_password,
            base_url=args.mill_base_url or secrets.get("MILL_API_URL", DEFAULT_MILL_API),
        )
        readings.append(
            fetch_mill_reading(
                mill_client, args.mill_device_id, room_name=args.mill_room_name
            )
        )

    if args.yr:
        readings.append(
            fetch_yr_outdoor_temperature(
                lat=args.yr_lat or DEFAULT_YR_LAT,
                lon=args.yr_lon or DEFAULT_YR_LON,
                altitude=args.yr_altitude if args.yr_altitude is not None else DEFAULT_YR_ALTITUDE,
                place_name=args.yr_name,
            )
        )

    if not readings:
        raise RuntimeError("Ingen kilder valgt. Bruk --glamox-room og/eller --mill-device-id.")

    for reading in readings:
        insert_reading(conn, reading)
        target_text = "-" if reading.target_c is None else f"{reading.target_c:.1f}C"
        print(
            f"[{reading.recorded_at.isoformat()}] {reading.source}/{reading.room}: "
            f"{reading.temperature_c:.1f}C (target {target_text})"
        )


def handle_mill_debug(args: argparse.Namespace) -> None:
    secrets = load_secrets(Path(args.secrets))
    mill_username = resolve_secret("MILL_USERNAME", args.mill_username, secrets)
    mill_password = resolve_secret("MILL_PASSWORD", args.mill_password, secrets)
    if not mill_username or not mill_password:
        raise RuntimeError(
            "Mangler brukernavn/passord for Mill. "
            "Sett miljøvariabler MILL_USERNAME/MILL_PASSWORD eller legg dem i secrets.json."
        )
    client = MillCloudClient(
        username=mill_username,
        password=mill_password,
        base_url=args.mill_base_url or secrets.get("MILL_API_URL", DEFAULT_MILL_API),
    )
    payload = client.fetch_device_status(args.mill_device_id)
    try:
        current, target = client.extract_temp(payload)
        print(f"Temperatur: {current}C, target: {target}C")
    except Exception as exc:  # noqa: BLE001
        print(f"Klarte ikke tolke temperatur automatisk: {exc}")
    print("Felt i responsen:")
    print(json.dumps(payload, indent=2, ensure_ascii=False))


def handle_mill_list(args: argparse.Namespace) -> None:
    secrets = load_secrets(Path(args.secrets))
    mill_username = resolve_secret("MILL_USERNAME", args.mill_username, secrets)
    mill_password = resolve_secret("MILL_PASSWORD", args.mill_password, secrets)
    if not mill_username or not mill_password:
        raise RuntimeError(
            "Mangler brukernavn/passord for Mill. "
            "Sett miljøvariabler MILL_USERNAME/MILL_PASSWORD eller legg dem i secrets.json."
        )
    client = MillCloudClient(
        username=mill_username,
        password=mill_password,
        base_url=args.mill_base_url or secrets.get("MILL_API_URL", DEFAULT_MILL_API),
    )
    if args.home_filter:
        # Prøv å finne houseId for navnet og bruk /houses/<id>/devices
        houses = client.list_houses()
        house_id = None
        for h in houses:
            if (h.get("name") or "").lower() == args.home_filter.lower():
                house_id = h.get("id")
                break
        if house_id:
            devices = client.list_devices_for_house(house_id)
            for dev in devices:
                dev.setdefault("homeName", args.home_filter)
        else:
            print(f"Fant ikke hus med navn {args.home_filter}, viser alle enheter.")
            devices = client.list_devices()
    else:
        devices = client.list_devices()
    def match_filter(value: Optional[str], expected: Optional[str]) -> bool:
        if expected is None:
            return True
        return (value or "").lower() == expected.lower()

    for dev in devices:
        home = dev.get("homeName") or dev.get("houseName") or dev.get("locationName")
        room = dev.get("roomName") or dev.get("room")
        name = dev.get("name")
        device_id = dev.get("id") or dev.get("deviceId") or dev.get("uuid")
        dev_type = dev.get("type") or dev.get("deviceType")
        if isinstance(dev_type, dict):
            dev_type = (
                dev_type.get("type")
                or dev_type.get("name")
                or (dev_type.get("childType") or {}).get("name")
            )
        if not match_filter(home, args.home_filter):
            continue
        if not match_filter(room, args.room_filter):
            continue
        print(
            f"id={device_id} name={name} room={room} home={home} "
            f"type={dev_type}"
        )
    print(f"Totalt funnet: {len(devices)} (filtrert vises over)")


def handle_plot(args: argparse.Namespace) -> None:
    conn = ensure_db(Path(args.db))
    readings = fetch_readings(conn, hours=args.hours, source=args.source, room=args.room)
    heater_counts = fetch_heater_online_counts(conn, hours=args.hours)
    plot_history(readings, Path(args.output), heater_counts=heater_counts)
    print(f"Lagret graf til {args.output}")


def handle_import_arp_presence(args: argparse.Namespace) -> None:
    conn = ensure_db(Path(args.db))
    summary = import_arp_presence(
        conn,
        log_path=Path(args.log_path),
        aliases_path=Path(args.aliases_file),
    )
    print(
        "Importerte ARP-presence: "
        f"{summary['events_seen']} events, "
        f"{summary['hours_written']} timer, "
        f"{summary['aliases_used']} aliaser, "
        f"{summary['hourly_rows_written']} hourly-rader"
    )


def handle_heater_status(args: argparse.Namespace) -> None:
    conn = ensure_db(Path(args.db))
    statuses = fetch_latest_heater_presence_statuses(conn)
    if not statuses:
        print("Ingen ovnstatus funnet i databasen.")
        return

    online_count = sum(1 for item in statuses if item.online)
    print(
        f"Siste time: {statuses[0].recorded_at.isoformat()} "
        f"({online_count} av {len(statuses)} online)"
    )
    for item in statuses:
        state = "online" if item.online else "nede"
        observed = item.observed_at.isoformat() if item.observed_at else "-"
        print(
            f"{item.alias}: {state} "
            f"(observert {observed}, ip={item.ip or '-'}, mac={item.mac or '-'})"
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Logg temperaturer fra Glamox og Mill til SQLite, og lag grafer."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    log_parser = sub.add_parser("log", help="Hent temperatur og lagre i databasen")
    log_parser.add_argument("--db", default=str(DEFAULT_DB), help="Sti til SQLite-fil")
    log_parser.add_argument(
        "--glamox-room",
        action="append",
        help="Romnavn i Glamox (kan angis flere ganger)",
    )
    log_parser.add_argument("--mill-device-id", help="Device-id for Mill-ovnen i skyen")
    log_parser.add_argument("--mill-room-name", help="Visningsnavn for Mill-rom")
    log_parser.add_argument("--mill-username", help="Mill brukernavn (overstyrer secrets/env)")
    log_parser.add_argument("--mill-password", help="Mill passord (overstyrer secrets/env)")
    log_parser.add_argument(
        "--mill-base-url",
        help=f"Mill API-baseurl (default {DEFAULT_MILL_API})",
    )
    log_parser.add_argument(
        "--yr",
        action="store_true",
        help="Logg utetemperatur fra Yr (default lokasjon Bjørkelangen)",
    )
    log_parser.add_argument(
        "--yr-lat",
        type=float,
        help=f"Breddegrad for Yr (default {DEFAULT_YR_LAT})",
    )
    log_parser.add_argument(
        "--yr-lon",
        type=float,
        help=f"Lengdegrad for Yr (default {DEFAULT_YR_LON})",
    )
    log_parser.add_argument(
        "--yr-altitude",
        type=float,
        help=f"Høyde over havet for Yr (default {DEFAULT_YR_ALTITUDE})",
    )
    log_parser.add_argument(
        "--yr-name",
        default="Bjørkelangen ute",
        help="Navn som vises for Yr-målingen",
    )
    log_parser.add_argument(
        "--secrets",
        default="secrets.json",
        help="JSON-fil med hemmeligheter (kan deles med Glamox)",
    )
    log_parser.set_defaults(func=handle_log)

    mill_debug_parser = sub.add_parser(
        "mill-debug", help="Hent rådata fra Mill-device for å se feltnavn"
    )
    mill_debug_parser.add_argument("--mill-device-id", required=True, help="Device-id for Mill-ovnen")
    mill_debug_parser.add_argument("--mill-username", help="Mill brukernavn (overstyrer secrets/env)")
    mill_debug_parser.add_argument("--mill-password", help="Mill passord (overstyrer secrets/env)")
    mill_debug_parser.add_argument(
        "--mill-base-url",
        help=f"Mill API-baseurl (default {DEFAULT_MILL_API})",
    )
    mill_debug_parser.add_argument(
        "--secrets",
        default="secrets.json",
        help="JSON-fil med hemmeligheter (kan deles med Glamox)",
    )
    mill_debug_parser.set_defaults(func=handle_mill_debug)

    mill_list_parser = sub.add_parser(
        "mill-list", help="List opp Mill-devices, ev. filtrert på home/room"
    )
    mill_list_parser.add_argument("--mill-username", help="Mill brukernavn (overstyrer secrets/env)")
    mill_list_parser.add_argument("--mill-password", help="Mill passord (overstyrer secrets/env)")
    mill_list_parser.add_argument(
        "--mill-base-url",
        help=f"Mill API-baseurl (default {DEFAULT_MILL_API})",
    )
    mill_list_parser.add_argument(
        "--secrets",
        default="secrets.json",
        help="JSON-fil med hemmeligheter (kan deles med Glamox)",
    )
    mill_list_parser.add_argument("--home-filter", help="Filtrer på home/house navn (eks. Bedehuset)")
    mill_list_parser.add_argument("--room-filter", help="Filtrer på romnavn")
    mill_list_parser.set_defaults(func=handle_mill_list)

    plot_parser = sub.add_parser("plot", help="Generer graf fra lagrede målinger")
    plot_parser.add_argument("--db", default=str(DEFAULT_DB), help="Sti til SQLite-fil")
    plot_parser.add_argument(
        "--hours", type=int, default=48, help="Antall timer historikk som skal plottes"
    )
    plot_parser.add_argument("--source", help="Filtrer på kilde (mill/glamox)")
    plot_parser.add_argument("--room", help="Filtrer på romnavn")
    plot_parser.add_argument(
        "--output", required=True, help="Filsti for PNG som skrives ut"
    )
    plot_parser.set_defaults(func=handle_plot)

    arp_parser = sub.add_parser(
        "import-arp-presence",
        help="Importer ovnstatus per time fra arp-scan.jsonl til egen SQLite-tabell",
    )
    arp_parser.add_argument("--db", default=str(DEFAULT_DB), help="Sti til SQLite-fil")
    arp_parser.add_argument(
        "--log-path",
        default="/var/log/bedehus/arp-scan.jsonl",
        help="JSONL-logg med arp_presence events",
    )
    arp_parser.add_argument(
        "--aliases-file",
        default="scripts/arp_alias",
        help="Fil med forventede ovn-aliaser, ett alias per linje",
    )
    arp_parser.set_defaults(func=handle_import_arp_presence)

    heater_status_parser = sub.add_parser(
        "heater-status",
        help="Vis siste times status for Glamox-ovner fra ARP-importen",
    )
    heater_status_parser.add_argument("--db", default=str(DEFAULT_DB), help="Sti til SQLite-fil")
    heater_status_parser.set_defaults(func=handle_heater_status)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
