#!/usr/bin/env python3
"""
Logger strømforbruk fra Mill til SQLite og kan lage grafer.

Eksempel:
    python3 scripts/energy_logger.py log --mill-device-id <ID>
    python3 scripts/energy_logger.py plot --hours 48 --output graphs/energy_48h.png
"""
import argparse
import datetime as dt
import json
import os
import sqlite3
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from temperature_logger import (  # type: ignore  # reuse Mill client/secrets helpers
    DEFAULT_MILL_API,
    MillCloudClient,
    Reading as TempReading,
    ensure_db as ensure_temp_db,
    load_secrets,
    resolve_secret,
)

DEFAULT_DB = Path("data/energy_history.sqlite")

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS energy_readings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    recorded_at TEXT NOT NULL,
    source TEXT NOT NULL,
    device_id TEXT NOT NULL,
    home TEXT,
    room TEXT,
    current_power_w REAL,
    energy_wh_total REAL,
    energy_wh_delta REAL,
    raw JSON
);
"""


@dataclass
class EnergyReading:
    source: str
    device_id: str
    home: Optional[str]
    room: Optional[str]
    current_power_w: Optional[float]
    energy_wh_total: Optional[float]
    energy_wh_delta: Optional[float]
    recorded_at: dt.datetime
    raw: Dict[str, Any]

    @classmethod
    def from_row(cls, row: Tuple[Any, ...]) -> "EnergyReading":
        _, recorded_at, source, device_id, home, room, cp, total, delta, raw = row
        return cls(
            source=source,
            device_id=device_id,
            home=home,
            room=room,
            current_power_w=float(cp) if cp is not None else None,
            energy_wh_total=float(total) if total is not None else None,
            energy_wh_delta=float(delta) if delta is not None else None,
            recorded_at=dt.datetime.fromisoformat(recorded_at),
            raw=json.loads(raw) if raw else {},
        )


@dataclass
class TempSeries:
    label: str
    readings: List[TempReading]
    include_target: bool = False


def ensure_db(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute(CREATE_TABLE_SQL)
    return conn


def insert_reading(conn: sqlite3.Connection, reading: EnergyReading) -> None:
    conn.execute(
        """
        INSERT INTO energy_readings
        (recorded_at, source, device_id, home, room, current_power_w, energy_wh_total, energy_wh_delta, raw)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            reading.recorded_at.isoformat(),
            reading.source,
            reading.device_id,
            reading.home,
            reading.room,
            reading.current_power_w,
            reading.energy_wh_total,
            reading.energy_wh_delta,
            json.dumps(reading.raw),
        ),
    )
    conn.commit()


def fetch_readings(
    conn: sqlite3.Connection,
    hours: Optional[int] = None,
    device_id: Optional[str] = None,
) -> List[EnergyReading]:
    query = "SELECT * FROM energy_readings"
    clauses: List[str] = []
    params: List[Any] = []
    if hours is not None:
        since = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=hours)
        clauses.append("recorded_at >= ?")
        params.append(since.isoformat())
    if device_id:
        clauses.append("device_id = ?")
        params.append(device_id)
    if clauses:
        query += " WHERE " + " AND ".join(clauses)
    query += " ORDER BY recorded_at ASC"
    cur = conn.execute(query, params)
    return [EnergyReading.from_row(row) for row in cur.fetchall()]


def fetch_mill_energy(
    client: MillCloudClient, device_id: str, room_name: Optional[str] = None, home_name: Optional[str] = None
) -> EnergyReading:
    payload = client.fetch_device_status(device_id)
    metrics = payload.get("lastMetrics") or {}
    now = dt.datetime.now(dt.timezone.utc)
    return EnergyReading(
        source="mill",
        device_id=device_id,
        home=home_name or payload.get("houseName"),
        room=room_name or payload.get("roomName"),
        current_power_w=metrics.get("currentPower"),
        energy_wh_total=metrics.get("energyUsage"),
        energy_wh_delta=metrics.get("energyUsageSinceLastReport"),
        recorded_at=now,
        raw=payload,
    )


def plot_energy(
    readings: Iterable[EnergyReading],
    output: Path,
    temp_series: Optional[List[TempSeries]] = None,
) -> None:
    import matplotlib.dates as mdates
    import matplotlib.pyplot as plt

    items = list(readings)
    if not items:
        raise RuntimeError("Ingen energimålinger å plotte")
    times = [r.recorded_at for r in items]

    intervals: List[float] = []
    prev_total: Optional[float] = None
    for r in items:
        delta = r.energy_wh_delta
        if delta is None:
            if r.energy_wh_total is not None and prev_total is not None:
                delta = r.energy_wh_total - prev_total
            else:
                delta = 0.0
        if delta < 0:
            delta = 0.0
        intervals.append(float(delta))
        if r.energy_wh_total is not None:
            prev_total = r.energy_wh_total

    fig, ax = plt.subplots(figsize=(10, 5))
    x = mdates.date2num(times)
    if len(x) > 1:
        diffs = [x[i] - x[i - 1] for i in range(1, len(x)) if x[i] - x[i - 1] > 0]
        width = (sum(diffs) / len(diffs)) * 0.8 if diffs else 0.03
    else:
        width = 0.03
    ax.bar(times, intervals, width=width, color="tab:orange", label="Forbruk per intervall (Wh)")
    ax.set_ylabel("Intervall (Wh)")

    ax.set_xlabel("Tid (UTC)")
    ax2 = None
    if temp_series:
        ax2 = ax.twinx()
        for series in temp_series:
            if not series.readings:
                continue
            t_times = [r.recorded_at for r in series.readings]
            t_vals = [r.temperature_c for r in series.readings]
            ax2.plot(
                t_times,
                t_vals,
                label=series.label,
                linewidth=1.2,
            )
            if series.include_target:
                target_points = [
                    (r.recorded_at, r.target_c)
                    for r in series.readings
                    if r.target_c is not None
                ]
                if target_points:
                    target_times, target_vals = zip(*target_points)
                    ax2.plot(
                        list(target_times),
                        list(target_vals),
                        linestyle="--",
                        label=f"{series.label} target",
                        linewidth=1.0,
                    )
        ax2.set_ylabel("Temperatur (°C)")

    if ax2:
        ax.set_title("Strømforbruk per intervall + temperatur")
    else:
        ax.set_title("Strømforbruk per intervall")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d %H:%M"))
    fig.autofmt_xdate()
    ax.grid(True, axis="y")
    if ax2:
        handles1, labels1 = ax.get_legend_handles_labels()
        handles2, labels2 = ax2.get_legend_handles_labels()
        ax2.legend(handles1 + handles2, labels1 + labels2, loc="upper left")
    fig.tight_layout()
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output)


def handle_log(args: argparse.Namespace) -> None:
    secrets = load_secrets(Path(args.secrets))
    conn = ensure_db(Path(args.db))
    # Reuse temp-db creation to ensure path exists
    ensure_temp_db(Path(args.db))

    mill_username = resolve_secret("MILL_USERNAME", args.mill_username, secrets)
    mill_password = resolve_secret("MILL_PASSWORD", args.mill_password, secrets)
    if not mill_username or not mill_password:
        raise RuntimeError("Mangler Mill brukernavn/passord (env/secrets.json).")
    client = MillCloudClient(
        username=mill_username,
        password=mill_password,
        base_url=args.mill_base_url or secrets.get("MILL_API_URL", DEFAULT_MILL_API),
    )
    reading = fetch_mill_energy(
        client, args.mill_device_id, room_name=args.mill_room_name, home_name=args.mill_home_name
    )
    insert_reading(conn, reading)
    print(
        f"[{reading.recorded_at.isoformat()}] {reading.home}/{reading.room or ''} "
        f"power={reading.current_power_w}W total={reading.energy_wh_total}Wh delta={reading.energy_wh_delta}Wh"
    )


def handle_plot(args: argparse.Namespace) -> None:
    conn = ensure_db(Path(args.db))
    readings = fetch_readings(conn, hours=args.hours, device_id=args.device_id)
    plot_energy(readings, Path(args.output))
    print(f"Lagret energigraf til {args.output}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Logg og plott energibruk fra Mill")
    sub = parser.add_subparsers(dest="command", required=True)

    log_parser = sub.add_parser("log", help="Hent og lagre energidata")
    log_parser.add_argument("--db", default=str(DEFAULT_DB), help="Sti til SQLite-fil")
    log_parser.add_argument("--mill-device-id", required=True, help="Device-id for Mill-ovnen")
    log_parser.add_argument("--mill-room-name", help="Visningsnavn for rom")
    log_parser.add_argument("--mill-home-name", help="Visningsnavn for hus")
    log_parser.add_argument("--mill-username", help="Mill brukernavn (overstyrer secrets/env)")
    log_parser.add_argument("--mill-password", help="Mill passord (overstyrer secrets/env)")
    log_parser.add_argument("--mill-base-url", help=f"Mill API-baseurl (default {DEFAULT_MILL_API})")
    log_parser.add_argument("--secrets", default="secrets.json", help="JSON-fil med hemmeligheter")
    log_parser.set_defaults(func=handle_log)

    plot_parser = sub.add_parser("plot", help="Plott energihistorikk")
    plot_parser.add_argument("--db", default=str(DEFAULT_DB), help="Sti til SQLite-fil")
    plot_parser.add_argument("--hours", type=int, default=48, help="Antall timer")
    plot_parser.add_argument("--device-id", help="Filtrer på device-id")
    plot_parser.add_argument("--output", required=True, help="PNG-fil for graf")
    plot_parser.set_defaults(func=handle_plot)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
