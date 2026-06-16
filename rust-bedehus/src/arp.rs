use std::collections::{BTreeSet, HashMap};
use std::fs;
use std::path::Path;

use anyhow::{Context, Result};
use chrono::{DateTime, TimeZone, Timelike, Utc};
use rusqlite::{Connection, params};
use serde::{Deserialize, Serialize};
use serde_json::Value;

#[derive(Debug)]
pub struct ImportSummary {
    pub events_seen: usize,
    pub hours_written: usize,
    pub aliases_used: usize,
    pub hourly_rows_written: usize,
}

#[derive(Debug)]
pub struct HeaterPresenceStatus {
    pub recorded_hour: DateTime<Utc>,
    pub alias: String,
    pub online: bool,
    pub observed_at: Option<DateTime<Utc>>,
    pub mac: Option<String>,
    pub ip: Option<String>,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
struct ArpEvent {
    ts: Option<String>,
    #[serde(rename = "type")]
    event_type: Option<String>,
    alias: Option<String>,
    mac: Option<String>,
    ip: Option<String>,
    scanner: Option<String>,
    online: Option<bool>,
}

#[derive(Debug, Clone)]
struct PresenceObservation {
    recorded_at: DateTime<Utc>,
    payload: ArpEvent,
}

pub fn import_arp_presence(
    conn: &Connection,
    log_path: &Path,
    aliases_path: &Path,
) -> Result<ImportSummary> {
    let raw = fs::read_to_string(log_path)
        .with_context(|| format!("Kunne ikke lese ARP-logg {}", log_path.display()))?;

    let mut event_map: HashMap<(DateTime<Utc>, String), PresenceObservation> = HashMap::new();
    let mut summary_hours: BTreeSet<DateTime<Utc>> = BTreeSet::new();
    let mut seen_aliases: BTreeSet<String> = BTreeSet::new();
    let mut events_seen = 0usize;

    for line in raw.lines() {
        let Some(payload) = extract_payload(line)? else {
            continue;
        };

        let Some(ts_raw) = payload.ts.as_deref() else {
            continue;
        };
        let recorded_at = DateTime::parse_from_rfc3339(ts_raw)
            .with_context(|| format!("Ugyldig ts i arp-logg: {ts_raw}"))?
            .with_timezone(&Utc);
        let recorded_hour = truncate_to_hour(recorded_at);
        summary_hours.insert(recorded_hour);

        if payload.event_type.as_deref() != Some("arp_presence") {
            continue;
        }
        if payload.online != Some(true) {
            continue;
        }
        let Some(alias) = payload.alias.clone() else {
            continue;
        };
        seen_aliases.insert(alias.clone());
        conn.execute(
            r#"
            INSERT INTO heater_presence_events
            (recorded_at, recorded_hour, alias, mac, ip, scanner, online, raw)
            VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8)
            ON CONFLICT(recorded_at, alias) DO UPDATE SET
                recorded_hour = excluded.recorded_hour,
                mac = excluded.mac,
                ip = excluded.ip,
                scanner = excluded.scanner,
                online = excluded.online,
                raw = excluded.raw
            "#,
            params![
                recorded_at.naive_utc().format("%Y-%m-%dT%H:%M:%S").to_string(),
                recorded_hour.naive_utc().format("%Y-%m-%dT%H:%M:%S").to_string(),
                alias,
                payload.mac,
                payload.ip,
                payload.scanner,
                1,
                serde_json::to_string(&payload)?,
            ],
        )?;
        events_seen += 1;

        let key = (recorded_hour, payload.alias.clone().unwrap_or_default());
        match event_map.get(&key) {
            Some(existing) if existing.recorded_at > recorded_at => {}
            _ => {
                event_map.insert(key, PresenceObservation { recorded_at, payload });
            }
        }
    }

    let aliases = load_glamox_aliases(aliases_path)?;
    let aliases_to_use: Vec<String> = if aliases.is_empty() {
        seen_aliases.into_iter().collect()
    } else {
        aliases
    };
    let hours: Vec<DateTime<Utc>> = summary_hours.into_iter().collect();

    let mut hourly_rows_written = 0usize;
    for hour in &hours {
        for alias in &aliases_to_use {
            let observation = event_map.get(&(*hour, alias.clone()));
            let payload = observation.map(|item| &item.payload);
            conn.execute(
                r#"
                INSERT INTO heater_presence_hourly
                (recorded_hour, alias, online, observed_at, mac, ip, scanner, raw)
                VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8)
                ON CONFLICT(recorded_hour, alias) DO UPDATE SET
                    online = excluded.online,
                    observed_at = excluded.observed_at,
                    mac = excluded.mac,
                    ip = excluded.ip,
                    scanner = excluded.scanner,
                    raw = excluded.raw
                "#,
                params![
                    hour.naive_utc().format("%Y-%m-%dT%H:%M:%S").to_string(),
                    alias,
                    if observation.is_some() { 1 } else { 0 },
                    observation.map(|item| {
                        item.recorded_at
                            .naive_utc()
                            .format("%Y-%m-%dT%H:%M:%S")
                            .to_string()
                    }),
                    payload.and_then(|item| item.mac.clone()),
                    payload.and_then(|item| item.ip.clone()),
                    payload.and_then(|item| item.scanner.clone()),
                    payload.map(serde_json::to_string).transpose()?,
                ],
            )?;
            hourly_rows_written += 1;
        }
    }

    Ok(ImportSummary {
        events_seen,
        hours_written: hours.len(),
        aliases_used: aliases_to_use.len(),
        hourly_rows_written,
    })
}

pub fn fetch_latest_heater_presence_statuses(conn: &Connection) -> Result<Vec<HeaterPresenceStatus>> {
    let latest_hour: Option<String> = conn
        .query_row(
            "SELECT MAX(recorded_hour) FROM heater_presence_hourly",
            [],
            |row| row.get(0),
        )
        .ok()
        .flatten();

    let Some(latest_hour) = latest_hour else {
        return Ok(Vec::new());
    };

    let mut stmt = conn.prepare(
        r#"
        SELECT recorded_hour, alias, online, observed_at, mac, ip
        FROM heater_presence_hourly
        WHERE recorded_hour = ?1
        ORDER BY alias ASC
        "#,
    )?;

    let rows = stmt.query_map([latest_hour], |row| {
        let recorded_hour: String = row.get(0)?;
        let alias: String = row.get(1)?;
        let online: i64 = row.get(2)?;
        let observed_at: Option<String> = row.get(3)?;
        let mac: Option<String> = row.get(4)?;
        let ip: Option<String> = row.get(5)?;
        Ok((recorded_hour, alias, online, observed_at, mac, ip))
    })?;

    let mut results = Vec::new();
    for row in rows {
        let (recorded_hour, alias, online, observed_at, mac, ip) = row?;
        results.push(HeaterPresenceStatus {
            recorded_hour: parse_naive_utc(&recorded_hour)?,
            alias,
            online: online != 0,
            observed_at: observed_at
                .as_deref()
                .map(parse_naive_utc)
                .transpose()?,
            mac,
            ip,
        });
    }
    Ok(results)
}

fn load_glamox_aliases(path: &Path) -> Result<Vec<String>> {
    if !path.exists() {
        return Ok(Vec::new());
    }
    let raw = fs::read_to_string(path)?;
    let mut aliases = Vec::new();
    let mut seen = BTreeSet::new();
    for line in raw.lines() {
        let clean = line.split('#').next().unwrap_or("").trim();
        if clean.is_empty() {
            continue;
        }
        let columns: Vec<&str> = clean.split_whitespace().collect();
        let Some(candidate) = columns.last() else {
            continue;
        };
        if !candidate.starts_with("glamox_ovn_") {
            continue;
        }
        if seen.insert((*candidate).to_string()) {
            aliases.push((*candidate).to_string());
        }
    }
    Ok(aliases)
}

fn extract_payload(line: &str) -> Result<Option<ArpEvent>> {
    let Some(brace_index) = line.find('{') else {
        return Ok(None);
    };
    let value: Value = serde_json::from_str(&line[brace_index..])?;
    if !value.is_object() {
        return Ok(None);
    }
    Ok(Some(serde_json::from_value(value)?))
}

fn truncate_to_hour(value: DateTime<Utc>) -> DateTime<Utc> {
    Utc.with_ymd_and_hms(value.year(), value.month(), value.day(), value.hour(), 0, 0)
        .single()
        .expect("valid timestamp")
}

fn parse_naive_utc(value: &str) -> Result<DateTime<Utc>> {
    let naive = chrono::NaiveDateTime::parse_from_str(value, "%Y-%m-%dT%H:%M:%S")?;
    Ok(DateTime::<Utc>::from_naive_utc_and_offset(naive, Utc))
}

use chrono::Datelike;

#[cfg(test)]
mod tests {
    use super::*;
    use chrono::Timelike;

    fn make_temp_db() -> (tempfile::TempDir, rusqlite::Connection) {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("test.sqlite");
        let conn = crate::db::open_temperature_db(&path).unwrap();
        (dir, conn)
    }

    #[test]
    fn extract_payload_from_syslog_line() {
        let line = r#"Jun 15 12:34:56 pi arp_logger: {"ts":"2024-06-15T12:34:56Z","type":"arp_presence","alias":"glamox_ovn_1","online":true}"#;
        let event = extract_payload(line).unwrap().unwrap();
        assert_eq!(event.alias.as_deref(), Some("glamox_ovn_1"));
        assert_eq!(event.online, Some(true));
    }

    #[test]
    fn extract_payload_from_plain_json() {
        let line = r#"{"ts":"2024-06-15T10:00:00Z","type":"arp_presence","alias":"glamox_ovn_2","mac":"aa:bb:cc:dd:ee:ff","ip":"10.0.0.1","online":true}"#;
        let event = extract_payload(line).unwrap().unwrap();
        assert_eq!(event.mac.as_deref(), Some("aa:bb:cc:dd:ee:ff"));
        assert_eq!(event.ip.as_deref(), Some("10.0.0.1"));
    }

    #[test]
    fn extract_payload_no_json_returns_none() {
        let result = extract_payload("Jun 15 12:34:56 pi arp_logger: no json here").unwrap();
        assert!(result.is_none());
    }

    #[test]
    fn extract_payload_empty_line_returns_none() {
        assert!(extract_payload("").unwrap().is_none());
    }

    #[test]
    fn truncate_to_hour_clears_minutes_and_seconds() {
        use chrono::TimeZone;
        let dt = Utc.with_ymd_and_hms(2024, 6, 15, 14, 37, 52).unwrap();
        let truncated = truncate_to_hour(dt);
        assert_eq!(truncated.hour(), 14);
        assert_eq!(truncated.minute(), 0);
        assert_eq!(truncated.second(), 0);
    }

    #[test]
    fn truncate_to_hour_preserves_date_and_hour() {
        use chrono::TimeZone;
        let dt = Utc.with_ymd_and_hms(2024, 12, 31, 23, 59, 59).unwrap();
        let truncated = truncate_to_hour(dt);
        assert_eq!(truncated.hour(), 23);
        assert_eq!(truncated.date_naive(), dt.date_naive());
    }

    #[test]
    fn parse_naive_utc_valid() {
        let dt = parse_naive_utc("2024-06-15T14:00:00").unwrap();
        assert_eq!(dt.hour(), 14);
        assert_eq!(dt.minute(), 0);
    }

    #[test]
    fn parse_naive_utc_invalid_returns_err() {
        assert!(parse_naive_utc("not-a-date").is_err());
        assert!(parse_naive_utc("2024-06-15").is_err());
    }

    #[test]
    fn load_glamox_aliases_extracts_correctly() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("arp_alias");
        std::fs::write(
            &path,
            "# comment\naa:bb:cc:dd:ee:ff glamox_ovn_1\nff:ee:dd:cc:bb:aa glamox_ovn_2\n11:22:33:44:55:66 other_device\n",
        )
        .unwrap();
        let aliases = load_glamox_aliases(&path).unwrap();
        assert_eq!(aliases, vec!["glamox_ovn_1", "glamox_ovn_2"]);
    }

    #[test]
    fn load_glamox_aliases_deduplicates() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("arp_alias");
        std::fs::write(
            &path,
            "aa:bb:cc:dd:ee:ff glamox_ovn_1\nff:ee:dd:cc:bb:aa glamox_ovn_1\n",
        )
        .unwrap();
        let aliases = load_glamox_aliases(&path).unwrap();
        assert_eq!(aliases.len(), 1);
        assert_eq!(aliases[0], "glamox_ovn_1");
    }

    #[test]
    fn load_glamox_aliases_ignores_comments_and_blanks() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("arp_alias");
        std::fs::write(&path, "# full comment line\naa:bb glamox_ovn_1 # inline comment\n\n").unwrap();
        let aliases = load_glamox_aliases(&path).unwrap();
        assert_eq!(aliases, vec!["glamox_ovn_1"]);
    }

    #[test]
    fn load_glamox_aliases_missing_file_returns_empty() {
        let result = load_glamox_aliases(std::path::Path::new("/nonexistent/arp_alias")).unwrap();
        assert!(result.is_empty());
    }

    #[test]
    fn import_arp_presence_round_trip() {
        let (_dir, conn) = make_temp_db();
        let tmp = tempfile::tempdir().unwrap();

        let log_path = tmp.path().join("arp-scan.jsonl");
        let aliases_path = tmp.path().join("arp_alias");

        std::fs::write(
            &log_path,
            concat!(
                "{\"ts\":\"2024-06-15T10:00:00Z\",\"type\":\"arp_presence\",\"alias\":\"glamox_ovn_1\",\"mac\":\"aa:bb:cc:dd:ee:ff\",\"ip\":\"10.0.0.1\",\"online\":true}\n",
                "{\"ts\":\"2024-06-15T10:15:00Z\",\"type\":\"arp_presence\",\"alias\":\"glamox_ovn_1\",\"mac\":\"aa:bb:cc:dd:ee:ff\",\"ip\":\"10.0.0.1\",\"online\":true}\n",
                "{\"ts\":\"2024-06-15T11:00:00Z\",\"type\":\"arp_presence\",\"alias\":\"glamox_ovn_2\",\"mac\":\"bb:cc:dd:ee:ff:00\",\"ip\":\"10.0.0.2\",\"online\":true}\n",
            ),
        )
        .unwrap();
        std::fs::write(
            &aliases_path,
            "aa:bb:cc:dd:ee:ff glamox_ovn_1\nbb:cc:dd:ee:ff:00 glamox_ovn_2\n",
        )
        .unwrap();

        let summary = import_arp_presence(&conn, &log_path, &aliases_path).unwrap();
        assert_eq!(summary.events_seen, 3);
        assert_eq!(summary.aliases_used, 2);
        // Unique hours: 10:00 and 11:00
        assert_eq!(summary.hours_written, 2);
        // 2 aliases × 2 hours = 4 hourly rows
        assert_eq!(summary.hourly_rows_written, 4);
    }

    #[test]
    fn import_arp_presence_idempotent() {
        let (_dir, conn) = make_temp_db();
        let tmp = tempfile::tempdir().unwrap();

        let log_path = tmp.path().join("arp-scan.jsonl");
        let aliases_path = tmp.path().join("arp_alias");

        std::fs::write(
            &log_path,
            "{\"ts\":\"2024-06-15T10:00:00Z\",\"type\":\"arp_presence\",\"alias\":\"glamox_ovn_1\",\"online\":true}\n",
        )
        .unwrap();
        std::fs::write(&aliases_path, "aa:bb:cc:dd:ee:ff glamox_ovn_1\n").unwrap();

        import_arp_presence(&conn, &log_path, &aliases_path).unwrap();
        // Second import of same data must not fail or duplicate rows
        let summary2 = import_arp_presence(&conn, &log_path, &aliases_path).unwrap();
        assert_eq!(summary2.events_seen, 1);
        assert_eq!(summary2.hourly_rows_written, 1);
    }

    #[test]
    fn import_arp_presence_skips_offline_events() {
        let (_dir, conn) = make_temp_db();
        let tmp = tempfile::tempdir().unwrap();

        let log_path = tmp.path().join("arp-scan.jsonl");
        let aliases_path = tmp.path().join("arp_alias");

        std::fs::write(
            &log_path,
            concat!(
                "{\"ts\":\"2024-06-15T10:00:00Z\",\"type\":\"arp_presence\",\"alias\":\"glamox_ovn_1\",\"online\":false}\n",
                "{\"ts\":\"2024-06-15T10:00:00Z\",\"type\":\"arp_presence\",\"alias\":\"glamox_ovn_1\",\"online\":true}\n",
            ),
        )
        .unwrap();
        std::fs::write(&aliases_path, "aa:bb:cc:dd:ee:ff glamox_ovn_1\n").unwrap();

        let summary = import_arp_presence(&conn, &log_path, &aliases_path).unwrap();
        // Only the online=true event is counted
        assert_eq!(summary.events_seen, 1);
    }

    #[test]
    fn fetch_latest_heater_presence_statuses_empty_db() {
        let (_dir, conn) = make_temp_db();
        let statuses = fetch_latest_heater_presence_statuses(&conn).unwrap();
        assert!(statuses.is_empty());
    }

    #[test]
    fn fetch_latest_heater_presence_statuses_after_import() {
        let (_dir, conn) = make_temp_db();
        let tmp = tempfile::tempdir().unwrap();

        let log_path = tmp.path().join("arp-scan.jsonl");
        let aliases_path = tmp.path().join("arp_alias");

        std::fs::write(
            &log_path,
            "{\"ts\":\"2024-06-15T10:00:00Z\",\"type\":\"arp_presence\",\"alias\":\"glamox_ovn_1\",\"mac\":\"aa:bb\",\"ip\":\"10.0.0.1\",\"online\":true}\n",
        )
        .unwrap();
        std::fs::write(&aliases_path, "aa:bb glamox_ovn_1\n").unwrap();

        import_arp_presence(&conn, &log_path, &aliases_path).unwrap();

        let statuses = fetch_latest_heater_presence_statuses(&conn).unwrap();
        assert_eq!(statuses.len(), 1);
        assert_eq!(statuses[0].alias, "glamox_ovn_1");
        assert!(statuses[0].online);
        assert_eq!(statuses[0].mac.as_deref(), Some("aa:bb"));
    }
}
