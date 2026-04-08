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
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from temperature_logger import (  # type: ignore  # reuse Mill client/secrets helpers
    DEFAULT_MILL_API,
    MillCloudClient,
    Reading as TempReading,
    load_secrets,
    resolve_secret,
)

DEFAULT_DB = Path("data/energy_history.sqlite")
DISPLAY_TZ = ZoneInfo("Europe/Oslo")

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

CREATE_UNIQUE_INDEX_SQL = """
CREATE UNIQUE INDEX IF NOT EXISTS idx_energy_readings_source_device_recorded_at
ON energy_readings (source, device_id, recorded_at);
"""

CREATE_RECORDED_AT_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_energy_readings_recorded_at
ON energy_readings (recorded_at);
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
    deleted = cleanup_duplicate_readings(conn)
    conn.execute(CREATE_UNIQUE_INDEX_SQL)
    conn.execute(CREATE_RECORDED_AT_INDEX_SQL)
    conn.commit()
    if deleted:
        print(f"Ryddet {deleted} duplikate energimålinger i {db_path}", file=sys.stderr)
    return conn


def cleanup_duplicate_readings(conn: sqlite3.Connection) -> int:
    cur = conn.execute(
        """
        DELETE FROM energy_readings
        WHERE id IN (
            SELECT id
            FROM (
                SELECT id,
                       ROW_NUMBER() OVER (
                           PARTITION BY source, device_id, recorded_at
                           ORDER BY id DESC
                       ) AS row_num
                FROM energy_readings
            )
            WHERE row_num > 1
        )
        """
    )
    deleted = cur.rowcount or 0
    if deleted:
        conn.commit()
    return deleted


def insert_reading(conn: sqlite3.Connection, reading: EnergyReading) -> None:
    conn.execute(
        """
        INSERT INTO energy_readings
        (recorded_at, source, device_id, home, room, current_power_w, energy_wh_total, energy_wh_delta, raw)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(source, device_id, recorded_at) DO UPDATE SET
            home = excluded.home,
            room = excluded.room,
            current_power_w = excluded.current_power_w,
            energy_wh_total = excluded.energy_wh_total,
            energy_wh_delta = excluded.energy_wh_delta,
            raw = excluded.raw
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
        since = dt.datetime.now(dt.UTC) - dt.timedelta(hours=hours)
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
    now = dt.datetime.now(dt.UTC)
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

    ax.set_xlabel("Tid (Europe/Oslo)")
    ax2 = None
    if temp_series:
        ax2 = ax.twinx()
        for series in temp_series:
            if not series.readings:
                continue
            t_times = [r.recorded_at for r in series.readings]
            t_vals = [r.temperature_c for r in series.readings]
            for idx, (segment_times, segment_vals) in enumerate(split_on_gaps(t_times, t_vals)):
                ax2.plot(
                    segment_times,
                    segment_vals,
                    label=series.label if idx == 0 else None,
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
                    for idx, (segment_times, segment_vals) in enumerate(
                        split_on_gaps(list(target_times), list(target_vals))
                    ):
                        ax2.plot(
                            segment_times,
                            segment_vals,
                            linestyle="--",
                            label=f"{series.label} target" if idx == 0 else None,
                            linewidth=1.0,
                        )
        ax2.set_ylabel("Temperatur (°C)")

    if ax2:
        ax.set_title("Strømforbruk per intervall + temperatur")
    else:
        ax.set_title("Strømforbruk per intervall")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d %H:%M", tz=DISPLAY_TZ))
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
