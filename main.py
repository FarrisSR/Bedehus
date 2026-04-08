import argparse
import datetime
import json
import logging
import logging.config
import os
import socket
import sqlite3
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional

from google.oauth2 import service_account
from googleapiclient.discovery import build

from glamox.glamox_controller import glamox_controller
from mill_controller.mill_controller import mill_controller
from sr201.sr201class import Sr201

DEFAULT_CONFIG: Dict[str, Any] = {
    "google": {
        "key_file": "service-account-key.json",
        "scopes": ["https://www.googleapis.com/auth/calendar.readonly"],
        "calendar_id": "",
        "pray_id": "",
    },
    "sr201": {
        "enabled": False,
        "ip": "",
        "relay": 1,
        "relay_pause_seconds": 5,
    },
    "mill": {
        "enabled": True,
        "ip": "",
        "temp_type": "Normal",
        "heat_on_temp": 21,
        "heat_off_temp": 17,
    },
    "glamox": {
        "enabled": True,
        "room_name": "Storsalen",
        "heat_on_temp": 21,
        "heat_off_temp": 17,
    },
    "logging": {
        "python_config_file": "logging.config",
    },
    "state_db": {
        "path": "config/relay_state.db",
    },
    "cache": {
        "google_max_age_hours": 24,
    },
    "time_window_hours": 2,
}


class HostnameFilter(logging.Filter):
    hostname = socket.gethostname()

    def filter(self, record: logging.LogRecord) -> bool:
        record.hostname = self.hostname
        return True


def merge_dict(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = merge_dict(out[key], value)
        else:
            out[key] = value
    return out


def setup_logging(base_dir: Path, cfg: Dict[str, Any]) -> logging.Logger:
    logger = logging.getLogger("bedehus-varme")
    log_cfg = cfg.get("logging", {}).get("python_config_file", "logging.config")
    log_path = resolve_path(base_dir, log_cfg)
    try:
        logging.config.fileConfig(fname=str(log_path), disable_existing_loggers=False)
    except Exception:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s %(name)-12s %(levelname)-8s %(message)s",
        )
    logger.setLevel(logging.INFO)
    logger.addFilter(HostnameFilter())
    return logger


def resolve_path(base_dir: Path, raw_path: str) -> Path:
    path = Path(raw_path)
    if path.is_absolute():
        return path
    return base_dir / path


def load_config(base_dir: Path, config_path: str) -> Dict[str, Any]:
    resolved = resolve_path(base_dir, config_path)
    with resolved.open("r", encoding="utf-8") as f:
        loaded = json.load(f)
    cfg = merge_dict(DEFAULT_CONFIG, loaded)

    if cfg["time_window_hours"] <= 0:
        cfg["time_window_hours"] = 2
    if cfg["sr201"].get("relay_pause_seconds", 0) <= 0:
        cfg["sr201"]["relay_pause_seconds"] = 5
    if cfg["cache"].get("google_max_age_hours", 0) <= 0:
        cfg["cache"]["google_max_age_hours"] = 24
    if not cfg["logging"].get("python_config_file"):
        cfg["logging"]["python_config_file"] = "logging.config"
    return cfg


@contextmanager
def timed_step(logger: logging.Logger, timing: Dict[str, float], name: str):
    start = time.perf_counter()
    try:
        yield
    finally:
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        timing[name] = elapsed_ms
        logger.debug("Step %s took %.1f ms", name, elapsed_ms)


def setup_google_calendar_client(cfg: Dict[str, Any], base_dir: Path):
    key_file = str(resolve_path(base_dir, cfg["google"]["key_file"]))
    credentials = service_account.Credentials.from_service_account_file(
        key_file,
        scopes=cfg["google"]["scopes"],
    )
    return build("calendar", "v3", credentials=credentials, cache_discovery=False)


def close_google_calendar_client(service: Any) -> None:
    close_fn = getattr(service, "close", None)
    if callable(close_fn):
        close_fn()
        return

    http = getattr(service, "_http", None)
    if http is None:
        return
    close_http = getattr(http, "close", None)
    if callable(close_http):
        close_http()


def get_calendar_events(calendar_id: str, service, start_time: datetime.datetime, end_time: datetime.datetime) -> List[Dict[str, Any]]:
    result = service.events().list(
        calendarId=calendar_id,
        timeMin=start_time.isoformat().replace("+00:00", "Z"),
        timeMax=end_time.isoformat().replace("+00:00", "Z"),
        singleEvents=True,
        orderBy="startTime",
    ).execute()
    return result.get("items", [])


def process_events(logger: logging.Logger, events: List[Dict[str, Any]]) -> bool:
    if not events:
        logger.info("No upcoming events found; heat not required")
        return False

    logger.info("Found %d upcoming event(s); heat required", len(events))
    for event in events:
        start = event.get("start", {}).get("dateTime", event.get("start", {}).get("date", "unknown"))
        summary = event.get("summary", "No Summary Available")
        logger.info("  Event start: %s Summary: %s", start, summary)
    return True


def open_state_db(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path))
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS calendar_cache (
            calendar_id TEXT NOT NULL,
            window_start TEXT NOT NULL,
            window_end TEXT NOT NULL,
            fetched_at TEXT NOT NULL,
            events_json TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_calendar_cache_lookup
        ON calendar_cache(calendar_id, fetched_at)
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS relay_state (
            id INTEGER PRIMARY KEY CHECK(id = 1),
            state INTEGER NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    conn.commit()
    return conn


def read_relay_state(conn: sqlite3.Connection) -> bool:
    row = conn.execute("SELECT state FROM relay_state WHERE id = 1").fetchone()
    if row is None:
        return False
    return bool(row[0])


def save_relay_state(conn: sqlite3.Connection, state: bool) -> None:
    conn.execute(
        """
        INSERT INTO relay_state (id, state, updated_at)
        VALUES (1, ?, ?)
        ON CONFLICT(id) DO UPDATE SET state=excluded.state, updated_at=excluded.updated_at
        """,
        (1 if state else 0, datetime.datetime.now(datetime.UTC).isoformat()),
    )
    conn.commit()


def save_calendar_cache(
    conn: sqlite3.Connection,
    calendar_id: str,
    start_time: datetime.datetime,
    end_time: datetime.datetime,
    events: List[Dict[str, Any]],
) -> None:
    conn.execute(
        """
        INSERT INTO calendar_cache (calendar_id, window_start, window_end, fetched_at, events_json)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            calendar_id,
            start_time.isoformat(),
            end_time.isoformat(),
            datetime.datetime.now(datetime.UTC).isoformat(),
            json.dumps(events),
        ),
    )
    conn.commit()


def load_calendar_cache(
    conn: sqlite3.Connection,
    calendar_id: str,
    start_time: datetime.datetime,
    max_age_hours: int,
) -> Optional[List[Dict[str, Any]]]:
    cutoff = datetime.datetime.now(datetime.UTC) - datetime.timedelta(hours=max_age_hours)
    row = conn.execute(
        """
        SELECT events_json, fetched_at
        FROM calendar_cache
        WHERE calendar_id = ?
          AND fetched_at >= ?
          AND window_end >= ?
        ORDER BY fetched_at DESC
        LIMIT 1
        """,
        (calendar_id, cutoff.isoformat(), start_time.isoformat()),
    ).fetchone()
    if row is None:
        return None
    return json.loads(row[0])


def get_calendar_events_with_fallback(
    logger: logging.Logger,
    conn: sqlite3.Connection,
    cfg: Dict[str, Any],
    service,
    calendar_id: str,
    start_time: datetime.datetime,
    end_time: datetime.datetime,
) -> List[Dict[str, Any]]:
    try:
        events = get_calendar_events(calendar_id, service, start_time, end_time)
        save_calendar_cache(conn, calendar_id, start_time, end_time, events)
        return events
    except Exception as exc:
        logger.error("Google API failed for %s: %s", calendar_id, exc)
        max_age_hours = int(cfg["cache"].get("google_max_age_hours", 24))
        cached_events = load_calendar_cache(conn, calendar_id, start_time, max_age_hours)
        if cached_events is None:
            raise
        logger.warning(
            "Using cached calendar data for %s (max age %sh)",
            calendar_id,
            max_age_hours,
        )
        return cached_events


def sr201_status(sr201_ip: str, relay: int) -> bool:
    sr = Sr201(sr201_ip)
    try:
        states = sr.do_return_status("status")
    finally:
        sr.close()

    if relay < 1 or relay > len(states):
        raise RuntimeError(f"relay {relay} out of range (response length {len(states)})")
    return states[relay - 1] == "1"


def sr201_heat_on(sr201_ip: str, relay: int, pause_seconds: int) -> None:
    sr = Sr201(sr201_ip)
    try:
        sr.do_close(f"close:{relay}")
        time.sleep(pause_seconds)
        sr.do_open(f"open:{relay}")
        time.sleep(pause_seconds)
        sr.do_close(f"close:{relay}")
    finally:
        sr.close()


def sr201_heat_off(sr201_ip: str, relay: int, pause_seconds: int) -> None:
    sr = Sr201(sr201_ip)
    try:
        sr.do_close(f"close:{relay}")
        time.sleep(pause_seconds)
        sr.do_open(f"open:{relay}")
        time.sleep(pause_seconds)
        sr.do_close(f"close:{relay}")
        time.sleep(pause_seconds)
        sr.do_open(f"open:{relay}")
    finally:
        sr.close()


def update_storsalen_glamox(logger: logging.Logger, cfg: Dict[str, Any], heat_on: bool) -> None:
    if not cfg["glamox"].get("enabled", True):
        logger.info("Glamox disabled; skipping update.")
        return

    target = cfg["glamox"]["heat_on_temp"] if heat_on else cfg["glamox"]["heat_off_temp"]
    ctrl = glamox_controller(room_name=cfg["glamox"]["room_name"])
    ctrl.set_temperature(target)
    logger.info("STORSALEN status: %s", ctrl.get_control_status())


def check_update_pray(logger: logging.Logger, cfg: Dict[str, Any], heat_on: bool) -> None:
    if not cfg["mill"].get("enabled", True):
        logger.info("Mill disabled; skipping PRAY update.")
        return

    controller = mill_controller(ip_address=cfg["mill"]["ip"], temp_type=cfg["mill"]["temp_type"])
    target = cfg["mill"]["heat_on_temp"] if heat_on else cfg["mill"]["heat_off_temp"]
    logger.info("Set PRAY heat to %.0fC.", target)
    result = controller.set_temperature(target)
    logger.info("PRAY%s", result)
    logger.debug("%s", controller.get_control_status())


def check_relay_state(logger: logging.Logger, conn: sqlite3.Connection, cfg: Dict[str, Any], heat_on: bool) -> Optional[bool]:
    last_state = read_relay_state(conn)
    logger.info("Last state: %s", last_state)

    if not cfg["sr201"].get("enabled", False):
        logger.info("SR201 disabled; skipping relay operations.")
        save_relay_state(conn, heat_on)
        if heat_on != last_state:
            logger.info("Change of state detected")
            return heat_on
        return None

    relay_status = sr201_status(cfg["sr201"]["ip"], cfg["sr201"]["relay"])
    save_relay_state(conn, heat_on)

    if heat_on != last_state:
        logger.info("Change of state detected")

    if heat_on:
        if not relay_status:
            logger.info("Turning heat on.")
            sr201_heat_on(
                cfg["sr201"]["ip"],
                cfg["sr201"]["relay"],
                int(cfg["sr201"]["relay_pause_seconds"]),
            )
            return True
        else:
            logger.info("Relay is already on, not turning heat on.")
        return None

    if relay_status:
        logger.info("Turning heat off.")
        sr201_heat_off(
            cfg["sr201"]["ip"],
            cfg["sr201"]["relay"],
            int(cfg["sr201"]["relay_pause_seconds"]),
        )
        return False

    logger.info("Relay is already off, not turning heat off.")
    return None


def validate_config(cfg: Dict[str, Any]) -> None:
    if not cfg["google"]["key_file"]:
        raise ValueError("google.key_file is required")
    if not cfg["google"]["calendar_id"]:
        raise ValueError("google.calendar_id is required")
    if not cfg["google"]["pray_id"]:
        raise ValueError("google.pray_id is required")
    if cfg["sr201"].get("enabled", False):
        if not cfg["sr201"]["ip"]:
            raise ValueError("sr201.ip is required when sr201 is enabled")
        relay = cfg["sr201"]["relay"]
        if relay < 1 or relay > 8:
            raise ValueError(f"sr201.relay must be 1-8 when sr201 is enabled, got {relay}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Bedehus heating controller")
    parser.add_argument("--config", default="config/config.json", help="Path to config file")
    args = parser.parse_args()

    base_dir = Path(__file__).resolve().parent
    os.chdir(base_dir)

    try:
        cfg = load_config(base_dir, args.config)
        validate_config(cfg)
    except Exception as e:
        print(f"Error loading config: {e}", file=sys.stderr)
        raise SystemExit(1) from e

    logger = setup_logging(base_dir, cfg)
    timing: Dict[str, float] = {}
    conn = None
    service = None

    try:
        state_path = resolve_path(base_dir, cfg["state_db"]["path"])
        state_path.parent.mkdir(parents=True, exist_ok=True)
        with timed_step(logger, timing, "state_db_open"):
            conn = open_state_db(state_path)

        with conn:
            with timed_step(logger, timing, "google_client"):
                service = setup_google_calendar_client(cfg, base_dir)

            current_time = datetime.datetime.now(datetime.UTC)
            end_time = current_time + datetime.timedelta(hours=cfg["time_window_hours"])

            with timed_step(logger, timing, "calendar_storsalen"):
                events = get_calendar_events_with_fallback(
                    logger,
                    conn,
                    cfg,
                    service,
                    cfg["google"]["calendar_id"],
                    current_time,
                    end_time,
                )
            heat_on = process_events(logger, events)

            with timed_step(logger, timing, "sr201_logic"):
                glamox_update = check_relay_state(logger, conn, cfg, heat_on)

            with timed_step(logger, timing, "glamox_logic"):
                if glamox_update is not None:
                    update_storsalen_glamox(logger, cfg, glamox_update)

            with timed_step(logger, timing, "calendar_pray"):
                pray_events = get_calendar_events_with_fallback(
                    logger,
                    conn,
                    cfg,
                    service,
                    cfg["google"]["pray_id"],
                    current_time,
                    end_time,
                )
            pray_heat_on = process_events(logger, pray_events)

            with timed_step(logger, timing, "mill_logic"):
                check_update_pray(logger, cfg, pray_heat_on)

    except Exception as e:
        logger.error("Error in main: %s", e)
        raise SystemExit(1) from e
    finally:
        if service is not None:
            close_google_calendar_client(service)
        if conn is not None:
            conn.close()
        if timing:
            pretty = ", ".join(f"{key}={value:.1f}ms" for key, value in sorted(timing.items(), key=lambda kv: kv[1], reverse=True))
            logger.info("Timing summary: %s", pretty)


if __name__ == "__main__":
    main()
