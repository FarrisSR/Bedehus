use std::collections::BTreeMap;
use std::fs;
use std::path::Path;

use anyhow::{Context, Result, anyhow};
use chrono::{DateTime, Duration, NaiveDateTime, Timelike, Utc};
use chrono_tz::Europe::Oslo;
use plotters::prelude::*;
use rusqlite::Connection;

use crate::arp::{HeaterPresenceStatus, fetch_latest_heater_presence_statuses};
use crate::font::ensure_plotters_font;

const DISPLAY_TIME_FMT: &str = "%Y-%m-%d %H:%M:%S";
const DB_TIME_FMT: &str = "%Y-%m-%dT%H:%M:%S";
const DB_TIME_FMT_SUBSEC: &str = "%Y-%m-%dT%H:%M:%S%.f";

#[derive(Debug, Clone)]
pub struct TempReading {
    pub source: String,
    pub room: String,
    pub temperature_c: f64,
    pub target_c: Option<f64>,
    pub recorded_at: DateTime<Utc>,
}

#[derive(Debug, Clone)]
pub struct HeaterOnlineCount {
    pub recorded_at: DateTime<Utc>,
    pub online_count: i64,
    pub expected_count: i64,
}

#[derive(Debug, Clone)]
pub struct TemperatureReportArgs {
    pub hours: i64,
    pub output_img: std::path::PathBuf,
    pub output_img_7d: Option<std::path::PathBuf>,
    pub output_img_30d: Option<std::path::PathBuf>,
    pub output_html: std::path::PathBuf,
}

pub fn generate(conn: &Connection, args: &TemperatureReportArgs) -> Result<()> {
    let readings_48h = fetch_temp_readings(conn, Some(args.hours), None, None)?;
    let readings_7d = fetch_temp_readings(conn, Some(24 * 7), None, None)?;
    let readings_30d = fetch_temp_readings(conn, Some(24 * 30), None, None)?;
    let heater_counts_48h = fetch_heater_online_counts(conn, Some(args.hours))?;
    let latest_heater_statuses = fetch_latest_heater_presence_statuses(conn)?;

    if readings_48h.is_empty() && readings_7d.is_empty() && readings_30d.is_empty() {
        return Err(anyhow!("Ingen målinger i databasen."));
    }

    let main_img = args.output_img.clone();
    let out_dir = args
        .output_html
        .parent()
        .ok_or_else(|| anyhow!("output_html mangler parent"))?;
    let img_7d = args
        .output_img_7d
        .clone()
        .unwrap_or_else(|| main_img.parent().unwrap().join("last_7d.png"));
    let img_30d = args
        .output_img_30d
        .clone()
        .unwrap_or_else(|| main_img.parent().unwrap().join("last_30d.png"));

    let base = if !readings_48h.is_empty() {
        &readings_48h
    } else if !readings_7d.is_empty() {
        &readings_7d
    } else {
        &readings_30d
    };
    plot_temperature_history(base, &main_img, Some(&heater_counts_48h), 900)?;

    let mut extra_imgs: Vec<(String, String)> = Vec::new();
    if !readings_7d.is_empty() {
        plot_temperature_history(&readings_7d, &img_7d, None, 500)?;
        extra_imgs.push((
            "Temperatur (siste uke)".to_string(),
            relative_path(&img_7d, out_dir)?,
        ));
    }
    if !readings_30d.is_empty() {
        plot_temperature_history(&readings_30d, &img_30d, None, 500)?;
        extra_imgs.push((
            "Temperatur (siste måned)".to_string(),
            relative_path(&img_30d, out_dir)?,
        ));
    }

    let latest = latest_per_source_room(base);
    render_html(
        &relative_path(&main_img, out_dir)?,
        &extra_imgs,
        &latest,
        heater_counts_48h.last(),
        &latest_heater_statuses,
        &args.output_html,
    )?;
    Ok(())
}

pub fn fetch_temp_readings(
    conn: &Connection,
    hours: Option<i64>,
    source: Option<&str>,
    room: Option<&str>,
) -> Result<Vec<TempReading>> {
    let mut query = String::from(
        "SELECT recorded_at, source, room, temperature_c, target_c FROM readings",
    );
    let mut clauses = Vec::new();
    let mut values: Vec<String> = Vec::new();
    if let Some(hours) = hours {
        let since = Utc::now() - Duration::hours(hours);
        clauses.push("recorded_at >= ?".to_string());
        values.push(since.format(DB_TIME_FMT).to_string());
    }
    if let Some(source) = source {
        clauses.push("source = ?".to_string());
        values.push(source.to_string());
    }
    if let Some(room) = room {
        clauses.push("room = ?".to_string());
        values.push(room.to_string());
    }
    if !clauses.is_empty() {
        query.push_str(" WHERE ");
        query.push_str(&clauses.join(" AND "));
    }
    query.push_str(" ORDER BY recorded_at ASC");

    let mut stmt = conn.prepare(&query)?;
    let rows = stmt.query_map(rusqlite::params_from_iter(values.iter()), |row| {
        let recorded_at: String = row.get(0)?;
        Ok(TempReading {
            recorded_at: parse_naive_utc(&recorded_at).map_err(to_sql_err)?,
            source: row.get(1)?,
            room: row.get(2)?,
            temperature_c: row.get(3)?,
            target_c: row.get(4)?,
        })
    })?;

    let mut result = Vec::new();
    for row in rows {
        result.push(row?);
    }
    Ok(result)
}

pub fn fetch_heater_online_counts(
    conn: &Connection,
    hours: Option<i64>,
) -> Result<Vec<HeaterOnlineCount>> {
    let mut query = String::from(
        "SELECT recorded_hour, SUM(online) AS online_count, COUNT(*) AS expected_count FROM heater_presence_hourly",
    );
    let mut values: Vec<String> = Vec::new();
    if let Some(hours) = hours {
        let since = (Utc::now() - Duration::hours(hours))
            .with_minute(0)
            .unwrap()
            .with_second(0)
            .unwrap()
            .with_nanosecond(0)
            .unwrap();
        query.push_str(" WHERE recorded_hour >= ?");
        values.push(since.format(DB_TIME_FMT).to_string());
    }
    query.push_str(" GROUP BY recorded_hour ORDER BY recorded_hour ASC");

    let mut stmt = conn.prepare(&query)?;
    let rows = stmt.query_map(rusqlite::params_from_iter(values.iter()), |row| {
        let recorded_hour: String = row.get(0)?;
        Ok(HeaterOnlineCount {
            recorded_at: parse_naive_utc(&recorded_hour).map_err(to_sql_err)?,
            online_count: row.get(1)?,
            expected_count: row.get(2)?,
        })
    })?;

    let mut result = Vec::new();
    for row in rows {
        result.push(row?);
    }
    Ok(result)
}

fn latest_per_source_room(readings: &[TempReading]) -> Vec<TempReading> {
    let mut latest: BTreeMap<(String, String), TempReading> = BTreeMap::new();
    for reading in readings {
        latest.insert(
            (reading.source.clone(), reading.room.clone()),
            reading.clone(),
        );
    }
    latest.into_values().collect()
}

fn render_html(
    img_rel_path: &str,
    extra_imgs: &[(String, String)],
    latest: &[TempReading],
    latest_heater_count: Option<&HeaterOnlineCount>,
    latest_heater_statuses: &[HeaterPresenceStatus],
    out_html: &Path,
) -> Result<()> {
    if let Some(parent) = out_html.parent() {
        fs::create_dir_all(parent)?;
    }
    let latest_rows = latest
        .iter()
        .map(|r| {
            format!(
                "<tr><td>{}</td><td>{}</td><td>{:.1}</td><td>{}</td><td>{}</td></tr>",
                r.source,
                r.room,
                r.temperature_c,
                r.target_c
                    .map(|value| format!("{value:.1}"))
                    .unwrap_or_else(|| "-".to_string()),
                format_display_time(r.recorded_at)
            )
        })
        .collect::<Vec<_>>()
        .join("");
    let extra_sections = extra_imgs
        .iter()
        .map(|(title, rel)| format!(r#"<h2>{title}</h2><img src="{rel}" alt="{title}">"#))
        .collect::<Vec<_>>()
        .join("");
    let heater_summary = latest_heater_count
        .map(|count| {
            format!(
                "<p>Tilgjengelige Glamox-ovner siste time: {} av {}.</p>",
                count.online_count, count.expected_count
            )
        })
        .unwrap_or_default();
    let heater_status_section = if latest_heater_statuses.is_empty() {
        String::new()
    } else {
        let rows = latest_heater_statuses
            .iter()
            .map(|item| {
                format!(
                    "<tr><td>{}</td><td>{}</td><td>{}</td><td>{}</td><td>{}</td></tr>",
                    item.alias,
                    if item.online { "online" } else { "nede" },
                    item.observed_at
                        .map(format_display_time)
                        .unwrap_or_else(|| "-".to_string()),
                    item.ip.clone().unwrap_or_else(|| "-".to_string()),
                    item.mac.clone().unwrap_or_else(|| "-".to_string()),
                )
            })
            .collect::<Vec<_>>()
            .join("");
        format!(
            "<h2>Ovnstatus Siste Time</h2><table><thead><tr><th>Alias</th><th>Status</th><th>Sist Sett</th><th>IP</th><th>MAC</th></tr></thead><tbody>{rows}</tbody></table>"
        )
    };
    let html = format!(
        r#"<!doctype html>
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
  <p>Siden oppdateres hver time via cron. Alle tider vises i Europe/Oslo.</p>
  <p><a href="../www/index.html">Se Python-versjonen av temperaturrapporten</a></p>
  {heater_summary}
  <img src="{img_rel_path}" alt="Temperatur vs target">
  {extra_sections}
  {heater_status_section}
  <h2>Siste målinger</h2>
  <table>
    <thead><tr><th>Kilde</th><th>Rom</th><th>Målt (C)</th><th>Target (C)</th><th>Tid (Europe/Oslo)</th></tr></thead>
    <tbody>{latest_rows}</tbody>
  </table>
</body>
</html>"#
    );
    fs::write(out_html, html)?;
    Ok(())
}

fn plot_temperature_history(
    readings: &[TempReading],
    output: &Path,
    heater_counts: Option<&[HeaterOnlineCount]>,
    max_points: usize,
) -> Result<()> {
    if readings.is_empty() {
        return Err(anyhow!("Ingen målinger å plotte"));
    }
    ensure_plotters_font()?;
    if let Some(parent) = output.parent() {
        fs::create_dir_all(parent)?;
    }

    let root = BitMapBackend::new(output, (1200, 600)).into_drawing_area();
    root.fill(&WHITE)?;

    let min_time = readings.first().unwrap().recorded_at;
    let max_time = readings.last().unwrap().recorded_at;
    let mut min_temp = readings
        .iter()
        .map(|r| r.temperature_c)
        .fold(f64::INFINITY, f64::min);
    let mut max_temp = readings
        .iter()
        .map(|r| r.temperature_c)
        .fold(f64::NEG_INFINITY, f64::max);
    for value in readings.iter().filter_map(|r| r.target_c) {
        min_temp = min_temp.min(value);
        max_temp = max_temp.max(value);
    }
    min_temp -= 1.0;
    max_temp += 1.0;

    let max_count = heater_counts
        .map(|items| items.iter().map(|item| item.expected_count).max().unwrap_or(0))
        .unwrap_or(0)
        .max(1) as f64;

    let mut chart = ChartBuilder::on(&root)
        .margin(20)
        .caption("Temperatur vs target", ("sans-serif", 24))
        .set_label_area_size(LabelAreaPosition::Left, 60)
        .set_label_area_size(LabelAreaPosition::Right, 60)
        .set_label_area_size(LabelAreaPosition::Bottom, 50)
        .build_cartesian_2d(min_time..max_time, min_temp..max_temp)?
        .set_secondary_coord(min_time..max_time, 0.0..(max_count + 0.5));

    chart
        .configure_mesh()
        .x_desc("Tid (Europe/Oslo)")
        .y_desc("Temperatur (°C)")
        .x_label_formatter(&|value| value.with_timezone(&Oslo).format("%m-%d %H:%M").to_string())
        .draw()?;
    chart
        .configure_secondary_axes()
        .y_desc("Antall ovner")
        .draw()?;

    let palette = [&RED, &BLUE, &MAGENTA, &CYAN, &GREEN, &BLACK];
    let mut grouped: BTreeMap<(String, String), Vec<TempReading>> = BTreeMap::new();
    for reading in readings {
        grouped
            .entry((reading.source.clone(), reading.room.clone()))
            .or_default()
            .push(reading.clone());
    }

    for (series_idx, ((source, room), items)) in grouped.into_iter().enumerate() {
        let color = palette[series_idx % palette.len()];
        for segment in split_temp_segments(&items, max_points) {
            chart
                .draw_series(LineSeries::new(
                    segment.iter().map(|item| (item.recorded_at, item.temperature_c)),
                    color.stroke_width(2),
                ))?
                .label(format!("{source}/{room} målt"))
                .legend(move |(x, y)| PathElement::new(vec![(x, y), (x + 20, y)], color));
        }

        let target_points = items
            .iter()
            .filter_map(|item| item.target_c.map(|target| (item.recorded_at, target)))
            .collect::<Vec<_>>();
        for segment in split_xy_segments(&target_points, max_points) {
            chart
                .draw_series(LineSeries::new(segment.into_iter(), color.mix(0.5).stroke_width(1)))?
                .label(format!("{source}/{room} target"))
                .legend(move |(x, y)| {
                    PathElement::new(vec![(x, y), (x + 20, y)], color.mix(0.5))
                });
        }
    }

    if let Some(counts) = heater_counts {
        chart
            .draw_secondary_series(LineSeries::new(
                counts
                    .iter()
                    .map(|item| (item.recorded_at, item.online_count as f64)),
                GREEN.stroke_width(2),
            ))?
            .label("Ovner online")
            .legend(|(x, y)| PathElement::new(vec![(x, y), (x + 20, y)], GREEN));

        chart
            .draw_secondary_series(LineSeries::new(
                counts
                    .iter()
                    .map(|item| (item.recorded_at, item.expected_count as f64)),
                BLACK.mix(0.4).stroke_width(1),
            ))?
            .label("Forventede ovner")
            .legend(|(x, y)| PathElement::new(vec![(x, y), (x + 20, y)], BLACK.mix(0.4)));
    }

    chart
        .configure_series_labels()
        .background_style(WHITE.mix(0.8))
        .border_style(BLACK)
        .draw()?;
    root.present()?;
    Ok(())
}

fn split_temp_segments(readings: &[TempReading], max_points: usize) -> Vec<Vec<TempReading>> {
    let points = readings
        .iter()
        .map(|item| (item.recorded_at, item.temperature_c, item.clone()))
        .collect::<Vec<_>>();
    let deltas = readings
        .windows(2)
        .map(|pair| pair[1].recorded_at - pair[0].recorded_at)
        .collect::<Vec<_>>();
    let threshold = gap_threshold(&deltas);
    let mut segments = Vec::new();
    let mut current = Vec::new();
    for (idx, (_, _, item)) in points.into_iter().enumerate() {
        if idx > 0 && threshold.map(|value| readings[idx].recorded_at - readings[idx - 1].recorded_at > value).unwrap_or(false) {
            segments.push(downsample_temp_segment(&current, max_points));
            current = Vec::new();
        }
        current.push(item);
    }
    if !current.is_empty() {
        segments.push(downsample_temp_segment(&current, max_points));
    }
    segments
}

fn split_xy_segments(
    points: &[(DateTime<Utc>, f64)],
    max_points: usize,
) -> Vec<Vec<(DateTime<Utc>, f64)>> {
    if points.is_empty() {
        return Vec::new();
    }
    let deltas = points
        .windows(2)
        .map(|pair| pair[1].0 - pair[0].0)
        .collect::<Vec<_>>();
    let threshold = gap_threshold(&deltas);
    let mut segments = Vec::new();
    let mut current = vec![points[0]];
    for idx in 1..points.len() {
        if threshold
            .map(|value| points[idx].0 - points[idx - 1].0 > value)
            .unwrap_or(false)
        {
            segments.push(downsample_xy_segment(&current, max_points));
            current = Vec::new();
        }
        current.push(points[idx]);
    }
    if !current.is_empty() {
        segments.push(downsample_xy_segment(&current, max_points));
    }
    segments
}

fn gap_threshold(deltas: &[Duration]) -> Option<Duration> {
    if deltas.is_empty() {
        return None;
    }
    let mut positives = deltas
        .iter()
        .copied()
        .filter(|delta| *delta > Duration::zero())
        .collect::<Vec<_>>();
    positives.sort();
    let typical = positives.get(positives.len() / 2).copied()?;
    Some(std::cmp::max(typical * 3, Duration::hours(1)))
}

fn downsample_temp_segment(points: &[TempReading], max_points: usize) -> Vec<TempReading> {
    if points.len() <= max_points {
        return points.to_vec();
    }
    let step = ((points.len() as f64) / (max_points as f64)).ceil() as usize;
    let mut result = points.iter().step_by(step).cloned().collect::<Vec<_>>();
    if result.last().map(|item| item.recorded_at) != points.last().map(|item| item.recorded_at) {
        result.push(points.last().unwrap().clone());
    }
    result
}

fn downsample_xy_segment(points: &[(DateTime<Utc>, f64)], max_points: usize) -> Vec<(DateTime<Utc>, f64)> {
    if points.len() <= max_points {
        return points.to_vec();
    }
    let step = ((points.len() as f64) / (max_points as f64)).ceil() as usize;
    let mut result = points.iter().step_by(step).copied().collect::<Vec<_>>();
    if result.last().map(|item| item.0) != points.last().map(|item| item.0) {
        result.push(*points.last().unwrap());
    }
    result
}

pub fn format_display_time(value: DateTime<Utc>) -> String {
    value.with_timezone(&Oslo).format(DISPLAY_TIME_FMT).to_string()
}

fn parse_naive_utc(value: &str) -> Result<DateTime<Utc>> {
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
