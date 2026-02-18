#!/usr/bin/env python3
"""
Genererer statisk energirapport (HTML + PNG) fra energy_history.sqlite.
"""
import argparse
from pathlib import Path
from typing import List, Optional

from energy_logger import (
    DEFAULT_DB,
    EnergyReading,
    TempSeries,
    ensure_db,
    fetch_readings,
    plot_energy,
)
from temperature_logger import DEFAULT_DB as DEFAULT_TEMP_DB
from temperature_logger import ensure_db as ensure_temp_db
from temperature_logger import fetch_readings as fetch_temp_readings


def latest_per_device(readings: List[EnergyReading]) -> List[EnergyReading]:
    latest = {}
    for r in readings:
        latest[r.device_id] = r
    return list(latest.values())


def render_html(img_rel_path: str, latest: List[EnergyReading], out_html: Path):
    out_html.parent.mkdir(parents=True, exist_ok=True)
    latest_rows = "".join(
        f"<tr><td>{r.device_id}</td><td>{r.home or ''}</td><td>{r.room or ''}</td>"
        f"<td>{r.current_power_w or ''}</td><td>{r.energy_wh_total or ''}</td>"
        f"<td>{r.energy_wh_delta or ''}</td><td>{r.recorded_at.isoformat()}</td></tr>"
        for r in latest
    )
    html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Energirapport</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 20px; }}
    table {{ border-collapse: collapse; width: 100%; max-width: 900px; }}
    th, td {{ border: 1px solid #ccc; padding: 6px 8px; text-align: left; }}
    th {{ background: #f5f5f5; }}
    img {{ max-width: 100%; height: auto; border: 1px solid #ddd; }}
  </style>
  <meta http-equiv="refresh" content="300">
</head>
<body>
  <h1>Energirapport (siste 48 timer)</h1>
  <p>Siden oppdateres hver time via cron.</p>
  <img src="{img_rel_path}" alt="Strømforbruk">
  <h2>Siste målinger</h2>
  <table>
    <thead><tr><th>Device</th><th>Hus</th><th>Rom</th><th>Power (W)</th><th>Total (Wh)</th><th>Delta (Wh)</th><th>Tid (UTC)</th></tr></thead>
    <tbody>
    {latest_rows}
    </tbody>
  </table>
</body>
</html>
"""
    out_html.write_text(html)


def build_temp_series(
    db_path: Path,
    hours: int,
    outdoor_source: Optional[str],
    outdoor_room: Optional[str],
    room_source: Optional[str],
    room_name: Optional[str],
) -> List[TempSeries]:
    if not db_path.exists():
        return []
    conn = ensure_temp_db(db_path)
    series: List[TempSeries] = []
    if outdoor_source and outdoor_room:
        outdoor = fetch_temp_readings(
            conn, hours=hours, source=outdoor_source, room=outdoor_room
        )
        if outdoor:
            label = outdoor_room if "ute" in outdoor_room.lower() else f"{outdoor_room} ute"
            series.append(TempSeries(label=label, readings=outdoor))
    if room_source and room_name:
        room_readings = fetch_temp_readings(
            conn, hours=hours, source=room_source, room=room_name
        )
        if room_readings:
            series.append(
                TempSeries(label=room_name, readings=room_readings, include_target=True)
            )
    return series


def main():
    parser = argparse.ArgumentParser(description="Generer statisk energirapport")
    parser.add_argument("--db", default=str(DEFAULT_DB), help="Sti til energy SQLite-fil")
    parser.add_argument("--hours", type=int, default=48, help="Antall timer som skal plottes")
    parser.add_argument(
        "--temp-db",
        default=str(DEFAULT_TEMP_DB),
        help="Sti til temperature SQLite-fil",
    )
    parser.add_argument(
        "--temp-outdoor-source",
        default="yr",
        help="Kilde for utetemperatur (default yr)",
    )
    parser.add_argument(
        "--temp-outdoor-room",
        default="Bjørkelangen ute",
        help="Romnavn for utetemperatur",
    )
    parser.add_argument(
        "--temp-room-source",
        default="mill",
        help="Kilde for romtemperatur (default mill)",
    )
    parser.add_argument(
        "--temp-room",
        default="Bønnerom",
        help="Romnavn for romtemperatur/target",
    )
    parser.add_argument("--output-img", default="www/graphs/energy_48h.png", help="Sti til PNG")
    parser.add_argument("--output-html", default="www/energy.html", help="Sti til HTML")
    args = parser.parse_args()

    conn = ensure_db(Path(args.db))
    readings = fetch_readings(conn, hours=args.hours)
    if not readings:
        raise SystemExit("Ingen energimålinger i databasen.")

    img_path = Path(args.output_img)
    temp_series = build_temp_series(
        db_path=Path(args.temp_db),
        hours=args.hours,
        outdoor_source=args.temp_outdoor_source,
        outdoor_room=args.temp_outdoor_room,
        room_source=args.temp_room_source,
        room_name=args.temp_room,
    )
    plot_energy(readings, img_path, temp_series=temp_series)

    latest_list = sorted(latest_per_device(readings), key=lambda r: r.device_id)
    render_html(img_path.relative_to(Path(args.output_html).parent), latest_list, Path(args.output_html))


if __name__ == "__main__":
    main()
