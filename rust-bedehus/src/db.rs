use std::path::Path;

use anyhow::Result;
use rusqlite::Connection;

const CREATE_TEMPERATURE_READINGS_SQL: &str = r#"
CREATE TABLE IF NOT EXISTS readings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    recorded_at TEXT NOT NULL,
    source TEXT NOT NULL,
    room TEXT NOT NULL,
    temperature_c REAL,
    target_c REAL,
    raw JSON
);
"#;

const CREATE_TEMPERATURE_UNIQUE_INDEX_SQL: &str = r#"
CREATE UNIQUE INDEX IF NOT EXISTS idx_readings_source_room_recorded_at
ON readings (source, room, recorded_at);
"#;

const CREATE_TEMPERATURE_RECORDED_AT_INDEX_SQL: &str = r#"
CREATE INDEX IF NOT EXISTS idx_readings_recorded_at
ON readings (recorded_at);
"#;

const CREATE_HEATER_PRESENCE_EVENTS_SQL: &str = r#"
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
"#;

const CREATE_HEATER_PRESENCE_EVENTS_UNIQUE_SQL: &str = r#"
CREATE UNIQUE INDEX IF NOT EXISTS idx_heater_presence_events_recorded_at_alias
ON heater_presence_events (recorded_at, alias);
"#;

const CREATE_HEATER_PRESENCE_EVENTS_HOUR_SQL: &str = r#"
CREATE INDEX IF NOT EXISTS idx_heater_presence_events_recorded_hour
ON heater_presence_events (recorded_hour);
"#;

const CREATE_HEATER_PRESENCE_HOURLY_SQL: &str = r#"
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
"#;

const CREATE_HEATER_PRESENCE_HOURLY_UNIQUE_SQL: &str = r#"
CREATE UNIQUE INDEX IF NOT EXISTS idx_heater_presence_hourly_hour_alias
ON heater_presence_hourly (recorded_hour, alias);
"#;

const CREATE_HEATER_PRESENCE_HOURLY_HOUR_SQL: &str = r#"
CREATE INDEX IF NOT EXISTS idx_heater_presence_hourly_recorded_hour
ON heater_presence_hourly (recorded_hour);
"#;

const CREATE_ENERGY_READINGS_SQL: &str = r#"
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
"#;

const CREATE_ENERGY_UNIQUE_INDEX_SQL: &str = r#"
CREATE UNIQUE INDEX IF NOT EXISTS idx_energy_readings_source_device_recorded_at
ON energy_readings (source, device_id, recorded_at);
"#;

const CREATE_ENERGY_RECORDED_AT_INDEX_SQL: &str = r#"
CREATE INDEX IF NOT EXISTS idx_energy_readings_recorded_at
ON energy_readings (recorded_at);
"#;

pub fn open_temperature_db(path: &Path) -> Result<Connection> {
    if let Some(parent) = path.parent() {
        std::fs::create_dir_all(parent)?;
    }
    let conn = Connection::open(path)?;
    conn.execute_batch(CREATE_TEMPERATURE_READINGS_SQL)?;
    conn.execute_batch(CREATE_TEMPERATURE_UNIQUE_INDEX_SQL)?;
    conn.execute_batch(CREATE_TEMPERATURE_RECORDED_AT_INDEX_SQL)?;
    conn.execute_batch(CREATE_HEATER_PRESENCE_EVENTS_SQL)?;
    conn.execute_batch(CREATE_HEATER_PRESENCE_EVENTS_UNIQUE_SQL)?;
    conn.execute_batch(CREATE_HEATER_PRESENCE_EVENTS_HOUR_SQL)?;
    conn.execute_batch(CREATE_HEATER_PRESENCE_HOURLY_SQL)?;
    conn.execute_batch(CREATE_HEATER_PRESENCE_HOURLY_UNIQUE_SQL)?;
    conn.execute_batch(CREATE_HEATER_PRESENCE_HOURLY_HOUR_SQL)?;
    Ok(conn)
}

pub fn open_energy_db(path: &Path) -> Result<Connection> {
    if let Some(parent) = path.parent() {
        std::fs::create_dir_all(parent)?;
    }
    let conn = Connection::open(path)?;
    conn.execute_batch(CREATE_ENERGY_READINGS_SQL)?;
    conn.execute_batch(CREATE_ENERGY_UNIQUE_INDEX_SQL)?;
    conn.execute_batch(CREATE_ENERGY_RECORDED_AT_INDEX_SQL)?;
    Ok(conn)
}
