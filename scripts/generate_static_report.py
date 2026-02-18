#!/usr/bin/env python3
"""
Genererer statisk rapport (HTML + PNG-graf) fra SQLite-data.

Bruk:
    python3 scripts/generate_static_report.py \
        --db data/temperature_history.sqlite \
        --hours 48 \
        --output-html www/index.html \
        --output-img www/graphs/last_48h.png
"""
import argparse
from pathlib import Path
from typing import List, Optional

from temperature_logger import (
    DEFAULT_DB,
    fetch_readings,
    ensure_db,
    plot_history,
    Reading,
)


def latest_per_source_room(readings: List[Reading]):
    latest = {}
    for r in readings:
        key = (r.source, r.room)
        latest[key] = r
    return latest


def render_html(img_rel_path: str, extra_imgs: List[tuple], latest: List[Reading], out_html: Path):
    out_html.parent.mkdir(parents=True, exist_ok=True)

    def format_temp(value: Optional[float]):
        if value is None:
            return "-"
        return f"{value:.1f}"

    latest_rows = "".join(
        f"<tr><td>{r.source}</td><td>{r.room}</td><td>{r.temperature_c:.1f}</td>"
        f"<td>{format_temp(r.target_c)}</td><td>{r.recorded_at.isoformat()}</td></tr>"
        for r in latest
    )
    extra_sections = "".join(
        f'<h2>{title}</h2><img src="{rel}" alt="{title}">' for title, rel in extra_imgs
    )
    html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Temperaturlogg</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 20px; }}
    table {{ border-collapse: collapse; width: 100%; max-width: 800px; }}
    th, td {{ border: 1px solid #ccc; padding: 6px 8px; text-align: left; }}
    th {{ background: #f5f5f5; }}
    img {{ max-width: 100%; height: auto; border: 1px solid #ddd; }}
  </style>
  <meta http-equiv="refresh" content="300">
</head>
<body>
  <h1>Temperaturlogg (siste 48 timer)</h1>
  <p>Siden oppdateres hver time via cron.</p>
  <img src="{img_rel_path}" alt="Temperatur vs target">
  {extra_sections}
  <h2>Siste målinger</h2>
  <table>
    <thead><tr><th>Kilde</th><th>Rom</th><th>Målt (C)</th><th>Target (C)</th><th>Tid (UTC)</th></tr></thead>
    <tbody>
    {latest_rows}
    </tbody>
  </table>
</body>
</html>
"""
    out_html.write_text(html)


def main():
    parser = argparse.ArgumentParser(description="Generer statisk HTML-rapport fra loggede temperaturer")
    parser.add_argument("--db", default=str(DEFAULT_DB), help="Sti til SQLite-fil")
    parser.add_argument("--hours", type=int, default=48, help="Antall timer som skal plottes")
    parser.add_argument("--output-img", default="www/graphs/last_48h.png", help="Sti til PNG-graf")
    parser.add_argument(
        "--output-img-7d",
        default=None,
        help="Sti til PNG-graf (siste uke). Default: samme mappe som --output-img, filnavn last_7d.png",
    )
    parser.add_argument(
        "--output-img-30d",
        default=None,
        help="Sti til PNG-graf (siste måned). Default: samme mappe som --output-img, filnavn last_30d.png",
    )
    parser.add_argument("--output-html", default="www/index.html", help="Sti til HTML-rapport")
    args = parser.parse_args()

    # Sett fornuftige defaults for 7d/30d i samme mappe som hovedbildet dersom de ikke er spesifisert.
    img_base_dir = Path(args.output_img).parent
    if args.output_img_7d is None:
        args.output_img_7d = str(img_base_dir / "last_7d.png")
    if args.output_img_30d is None:
        args.output_img_30d = str(img_base_dir / "last_30d.png")

    conn = ensure_db(Path(args.db))
    readings_48h = fetch_readings(conn, hours=args.hours)
    readings_7d = fetch_readings(conn, hours=24 * 7)
    readings_30d = fetch_readings(conn, hours=24 * 30)
    if not (readings_48h or readings_7d or readings_30d):
        raise SystemExit("Ingen målinger i databasen.")

    img_path = Path(args.output_img)
    plot_history(readings_48h or readings_7d or readings_30d, img_path, max_points=900)

    extra_imgs: List[tuple] = []
    out_dir = Path(args.output_html).parent

    def plot_if_data(readings: List[Reading], output_path: Path, title: str, max_points: int) -> None:
        if readings:
            plot_history(readings, output_path, max_points=max_points)
            extra_imgs.append((title, output_path.relative_to(out_dir)))

    plot_if_data(readings_7d, Path(args.output_img_7d), "Temperatur (siste uke)", max_points=500)
    plot_if_data(readings_30d, Path(args.output_img_30d), "Temperatur (siste måned)", max_points=500)

    latest_map = latest_per_source_room(readings_48h or readings_7d or readings_30d)
    latest_list = sorted(latest_map.values(), key=lambda r: (r.source, r.room))
    render_html(
        img_path.relative_to(out_dir),
        extra_imgs,
        latest_list,
        Path(args.output_html),
    )


if __name__ == "__main__":
    main()
