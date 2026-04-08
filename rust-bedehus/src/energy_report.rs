use std::collections::BTreeMap;
use std::fs;
use std::path::Path;

use anyhow::{Context, Result, anyhow};
use chrono::{DateTime, Duration, NaiveDateTime, Utc};
use chrono_tz::Europe::Oslo;
use plotters::prelude::*;
use rusqlite::Connection;

use crate::temperature_report::{TempReading, fetch_temp_readings, format_display_time};
use crate::font::ensure_plotters_font;

const DB_TIME_FMT: &str = "%Y-%m-%dT%H:%M:%S";
const DB_TIME_FMT_SUBSEC: &str = "%Y-%m-%dT%H:%M:%S%.f";

#[derive(Debug, Clone)]
pub struct EnergyReading {
    pub device_id: String,
    pub home: Option<String>,
    pub room: Option<String>,
    pub current_power_w: Option<f64>,
    pub energy_wh_total: Option<f64>,
    pub energy_wh_delta: Option<f64>,
    pub recorded_at: DateTime<Utc>,
}

#[derive(Debug, Clone)]
pub struct TempSeries {
    pub label: String,
    pub readings: Vec<TempReading>,
    pub include_target: bool,
}

#[derive(Debug, Clone)]
pub struct EnergyReportArgs {
    pub hours: i64,
    pub temp_outdoor_source: String,
    pub temp_outdoor_room: String,
    pub temp_room_source: String,
    pub temp_room: String,
    pub output_img: std::path::PathBuf,
    pub output_html: std::path::PathBuf,
}

pub fn generate(energy_conn: &Connection, temp_conn: &Connection, args: &EnergyReportArgs) -> Result<()> {
    let readings = fetch_energy_readings(energy_conn, Some(args.hours), None)?;
    if readings.is_empty() {
        return Err(anyhow!("Ingen energimålinger i databasen."));
    }
    let temp_series = build_temp_series(
        temp_conn,
        args.hours,
        Some(&args.temp_outdoor_source),
        Some(&args.temp_outdoor_room),
        Some(&args.temp_room_source),
        Some(&args.temp_room),
    )?;
    plot_energy(&readings, &args.output_img, &temp_series)?;

    let out_dir = args
        .output_html
        .parent()
        .ok_or_else(|| anyhow!("output_html mangler parent"))?;
    let latest_list = latest_per_device(&readings);
    render_html(
        &relative_path(&args.output_img, out_dir)?,
        &latest_list,
        &args.output_html,
    )?;
    Ok(())
}

pub fn fetch_energy_readings(
    conn: &Connection,
    hours: Option<i64>,
    device_id: Option<&str>,
) -> Result<Vec<EnergyReading>> {
    let mut query = String::from(
        "SELECT recorded_at, device_id, home, room, current_power_w, energy_wh_total, energy_wh_delta FROM energy_readings",
    );
    let mut clauses = Vec::new();
    let mut values = Vec::new();
    if let Some(hours) = hours {
        let since = Utc::now() - Duration::hours(hours);
        clauses.push("recorded_at >= ?".to_string());
        values.push(since.to_rfc3339());
    }
    if let Some(device_id) = device_id {
        clauses.push("device_id = ?".to_string());
        values.push(device_id.to_string());
    }
    if !clauses.is_empty() {
        query.push_str(" WHERE ");
        query.push_str(&clauses.join(" AND "));
    }
    query.push_str(" ORDER BY recorded_at ASC");

    let mut stmt = conn.prepare(&query)?;
    let rows = stmt.query_map(rusqlite::params_from_iter(values.iter()), |row| {
        let recorded_at: String = row.get(0)?;
        Ok(EnergyReading {
            recorded_at: parse_datetime(&recorded_at).map_err(to_sql_err)?,
            device_id: row.get(1)?,
            home: row.get(2)?,
            room: row.get(3)?,
            current_power_w: row.get(4)?,
            energy_wh_total: row.get(5)?,
            energy_wh_delta: row.get(6)?,
        })
    })?;
    let mut result = Vec::new();
    for row in rows {
        result.push(row?);
    }
    Ok(result)
}

fn build_temp_series(
    conn: &Connection,
    hours: i64,
    outdoor_source: Option<&str>,
    outdoor_room: Option<&str>,
    room_source: Option<&str>,
    room_name: Option<&str>,
) -> Result<Vec<TempSeries>> {
    let mut series = Vec::new();
    if let (Some(source), Some(room)) = (outdoor_source, outdoor_room) {
        let readings = fetch_temp_readings(conn, Some(hours), Some(source), Some(room))?;
        if !readings.is_empty() {
            let label = if room.to_lowercase().contains("ute") {
                room.to_string()
            } else {
                format!("{room} ute")
            };
            series.push(TempSeries {
                label,
                readings,
                include_target: false,
            });
        }
    }
    if let (Some(source), Some(room)) = (room_source, room_name) {
        let readings = fetch_temp_readings(conn, Some(hours), Some(source), Some(room))?;
        if !readings.is_empty() {
            series.push(TempSeries {
                label: room.to_string(),
                readings,
                include_target: true,
            });
        }
    }
    Ok(series)
}

fn latest_per_device(readings: &[EnergyReading]) -> Vec<EnergyReading> {
    let mut latest = BTreeMap::new();
    for reading in readings {
        latest.insert(reading.device_id.clone(), reading.clone());
    }
    latest.into_values().collect()
}

fn render_html(img_rel_path: &str, latest: &[EnergyReading], out_html: &Path) -> Result<()> {
    if let Some(parent) = out_html.parent() {
        fs::create_dir_all(parent)?;
    }
    let rows = latest
        .iter()
        .map(|r| {
            format!(
                "<tr><td>{}</td><td>{}</td><td>{}</td><td>{}</td><td>{}</td><td>{}</td><td>{}</td></tr>",
                r.device_id,
                r.home.clone().unwrap_or_default(),
                r.room.clone().unwrap_or_default(),
                r.current_power_w.map(|v| v.to_string()).unwrap_or_default(),
                r.energy_wh_total.map(|v| v.to_string()).unwrap_or_default(),
                r.energy_wh_delta.map(|v| v.to_string()).unwrap_or_default(),
                format_display_time(r.recorded_at)
            )
        })
        .collect::<Vec<_>>()
        .join("");

    let html = format!(
        r#"<!doctype html>
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
  <p>Siden oppdateres hver time via cron. Alle tider vises i Europe/Oslo.</p>
  <p><a href="../www/energy.html">Se Python-versjonen av energirapporten</a></p>
  <img src="{img_rel_path}" alt="Strømforbruk">
  <h2>Siste målinger</h2>
  <table>
    <thead><tr><th>Device</th><th>Hus</th><th>Rom</th><th>Power (W)</th><th>Total (Wh)</th><th>Delta (Wh)</th><th>Tid (Europe/Oslo)</th></tr></thead>
    <tbody>{rows}</tbody>
  </table>
</body>
</html>"#
    );
    fs::write(out_html, html)?;
    Ok(())
}

fn plot_energy(readings: &[EnergyReading], output: &Path, temp_series: &[TempSeries]) -> Result<()> {
    if readings.is_empty() {
        return Err(anyhow!("Ingen energimålinger å plotte"));
    }
    ensure_plotters_font()?;
    if let Some(parent) = output.parent() {
        fs::create_dir_all(parent)?;
    }

    let root = BitMapBackend::new(output, (1200, 600)).into_drawing_area();
    root.fill(&WHITE)?;

    let min_time = readings.first().unwrap().recorded_at;
    let max_time = readings.last().unwrap().recorded_at;

    let intervals = calculate_intervals(readings);
    let max_energy = intervals.iter().map(|(_, _, v)| *v).fold(0.0, f64::max).max(1.0);

    let temp_values = temp_series
        .iter()
        .flat_map(|series| {
            series.readings.iter().flat_map(|reading| {
                let mut values = vec![reading.temperature_c];
                if let Some(target) = reading.target_c {
                    values.push(target);
                }
                values
            })
        })
        .collect::<Vec<_>>();
    let min_temp = temp_values.iter().copied().fold(f64::INFINITY, f64::min).min(0.0) - 1.0;
    let max_temp = temp_values.iter().copied().fold(f64::NEG_INFINITY, f64::max).max(10.0) + 1.0;

    let mut chart = ChartBuilder::on(&root)
        .margin(20)
        .caption("Strømforbruk per intervall + temperatur", ("sans-serif", 24))
        .set_label_area_size(LabelAreaPosition::Left, 60)
        .set_label_area_size(LabelAreaPosition::Right, 60)
        .set_label_area_size(LabelAreaPosition::Bottom, 50)
        .build_cartesian_2d(min_time..max_time, 0.0..(max_energy * 1.2))?
        .set_secondary_coord(min_time..max_time, min_temp..max_temp);

    chart
        .configure_mesh()
        .x_desc("Tid (Europe/Oslo)")
        .y_desc("Intervall (Wh)")
        .x_label_formatter(&|value| value.with_timezone(&Oslo).format("%m-%d %H:%M").to_string())
        .draw()?;
    chart
        .configure_secondary_axes()
        .y_desc("Temperatur (°C)")
        .draw()?;

    chart
        .draw_series(intervals.iter().map(|(start, end, value)| {
            Rectangle::new([(*start, 0.0), (*end, *value)], RGBColor(255, 165, 0).filled())
        }))?
        .label("Forbruk per intervall (Wh)")
        .legend(|(x, y)| Rectangle::new([(x, y - 5), (x + 20, y + 5)], RGBColor(255, 165, 0).filled()));

    let palette = [&BLUE, &GREEN, &MAGENTA, &CYAN];
    for (series_idx, series) in temp_series.iter().enumerate() {
        let color = palette[series_idx % palette.len()];
        for segment in split_temp_segments(&series.readings) {
            chart
                .draw_secondary_series(LineSeries::new(
                    segment.iter().map(|item| (item.recorded_at, item.temperature_c)),
                    color.stroke_width(2),
                ))?
                .label(series.label.clone())
                .legend(move |(x, y)| PathElement::new(vec![(x, y), (x + 20, y)], color));
        }
        if series.include_target {
            let target_points = series
                .readings
                .iter()
                .filter_map(|reading| reading.target_c.map(|target| (reading.recorded_at, target)))
                .collect::<Vec<_>>();
            for segment in split_xy_segments(&target_points) {
                chart
                    .draw_secondary_series(LineSeries::new(
                        segment.into_iter(),
                        color.mix(0.5).stroke_width(1),
                    ))?
                    .label(format!("{} target", series.label))
                    .legend(move |(x, y)| {
                        PathElement::new(vec![(x, y), (x + 20, y)], color.mix(0.5))
                    });
            }
        }
    }

    chart
        .configure_series_labels()
        .background_style(WHITE.mix(0.8))
        .border_style(BLACK)
        .draw()?;
    root.present()?;
    Ok(())
}

fn calculate_intervals(readings: &[EnergyReading]) -> Vec<(DateTime<Utc>, DateTime<Utc>, f64)> {
    let mut intervals = Vec::new();
    let mut prev_total: Option<f64> = None;
    let width = average_step(readings);
    for reading in readings {
        let mut delta = reading.energy_wh_delta.unwrap_or(0.0);
        if reading.energy_wh_delta.is_none() {
            if let (Some(total), Some(prev)) = (reading.energy_wh_total, prev_total) {
                delta = (total - prev).max(0.0);
            }
        }
        if let Some(total) = reading.energy_wh_total {
            prev_total = Some(total);
        }
        let half = width / 2;
        intervals.push((reading.recorded_at - half, reading.recorded_at + half, delta.max(0.0)));
    }
    intervals
}

fn average_step(readings: &[EnergyReading]) -> Duration {
    if readings.len() < 2 {
        return Duration::minutes(15);
    }
    let mut steps = readings
        .windows(2)
        .map(|pair| pair[1].recorded_at - pair[0].recorded_at)
        .filter(|delta| *delta > Duration::zero())
        .collect::<Vec<_>>();
    if steps.is_empty() {
        return Duration::minutes(15);
    }
    steps.sort();
    steps[steps.len() / 2]
}

fn split_temp_segments(readings: &[TempReading]) -> Vec<Vec<TempReading>> {
    if readings.is_empty() {
        return Vec::new();
    }
    let mut segments = Vec::new();
    let mut current = vec![readings[0].clone()];
    let threshold = gap_threshold(
        &readings
            .windows(2)
            .map(|pair| pair[1].recorded_at - pair[0].recorded_at)
            .collect::<Vec<_>>(),
    );
    for idx in 1..readings.len() {
        if threshold
            .map(|value| readings[idx].recorded_at - readings[idx - 1].recorded_at > value)
            .unwrap_or(false)
        {
            segments.push(current);
            current = Vec::new();
        }
        current.push(readings[idx].clone());
    }
    if !current.is_empty() {
        segments.push(current);
    }
    segments
}

fn split_xy_segments(points: &[(DateTime<Utc>, f64)]) -> Vec<Vec<(DateTime<Utc>, f64)>> {
    if points.is_empty() {
        return Vec::new();
    }
    let mut segments = Vec::new();
    let mut current = vec![points[0]];
    let threshold = gap_threshold(
        &points
            .windows(2)
            .map(|pair| pair[1].0 - pair[0].0)
            .collect::<Vec<_>>(),
    );
    for idx in 1..points.len() {
        if threshold
            .map(|value| points[idx].0 - points[idx - 1].0 > value)
            .unwrap_or(false)
        {
            segments.push(current);
            current = Vec::new();
        }
        current.push(points[idx]);
    }
    if !current.is_empty() {
        segments.push(current);
    }
    segments
}

fn gap_threshold(deltas: &[Duration]) -> Option<Duration> {
    let mut positives = deltas
        .iter()
        .copied()
        .filter(|delta| *delta > Duration::zero())
        .collect::<Vec<_>>();
    if positives.is_empty() {
        return None;
    }
    positives.sort();
    let typical = positives[positives.len() / 2];
    Some(std::cmp::max(typical * 3, Duration::hours(1)))
}

fn parse_datetime(value: &str) -> Result<DateTime<Utc>> {
    if let Ok(parsed) = DateTime::parse_from_rfc3339(value) {
        return Ok(parsed.with_timezone(&Utc));
    }
    let naive = NaiveDateTime::parse_from_str(value, DB_TIME_FMT_SUBSEC)
        .or_else(|_| NaiveDateTime::parse_from_str(value, DB_TIME_FMT))?;
    Ok(DateTime::<Utc>::from_naive_utc_and_offset(naive, Utc))
}

fn relative_path(path: &Path, base: &Path) -> Result<String> {
    let rel = path
        .strip_prefix(base)
        .with_context(|| format!("Kunne ikke gjøre {} relativ til {}", path.display(), base.display()))?;
    Ok(rel.display().to_string())
}

fn to_sql_err(err: anyhow::Error) -> rusqlite::Error {
    rusqlite::Error::FromSqlConversionFailure(
        0,
        rusqlite::types::Type::Text,
        Box::new(std::io::Error::new(std::io::ErrorKind::InvalidData, err.to_string())),
    )
}
