use std::collections::BTreeMap;
use std::env;
use std::fs;
use std::io::{Read, Write};
use std::net::{TcpStream, ToSocketAddrs};
use std::path::{Path, PathBuf};
use std::sync::{
    Arc,
    atomic::{AtomicBool, Ordering},
};
use std::thread;
use std::time::{Duration as StdDuration, Instant, SystemTime};

use anyhow::{Context, Result, anyhow};
use chrono::{DateTime, Duration, Local, Utc};
use jsonwebtoken::{Algorithm, EncodingKey, Header, encode};
use reqwest::blocking::Client;
use rusqlite::{Connection, OptionalExtension, params};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use signal_hook::consts::signal::{SIGHUP, SIGINT, SIGTERM};
use signal_hook::flag;

#[derive(Debug, Clone)]
pub struct ControllerArgs {
    pub config: PathBuf,
    pub interval_seconds: Option<u64>,
    pub dry_run: bool,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(default)]
pub struct Config {
    pub google: GoogleConfig,
    pub sr201: Sr201Config,
    pub mill: MillConfig,
    pub glamox: GlamoxConfig,
    pub cache: CacheConfig,
    pub systemd: SystemdConfig,
    pub state_db: StateDbConfig,
    pub time_window_hours: i64,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(default)]
pub struct GoogleConfig {
    pub key_file: String,
    pub scopes: Vec<String>,
    pub calendar_id: String,
    pub pray_id: String,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(default)]
pub struct Sr201Config {
    pub enabled: bool,
    pub ip: String,
    pub port: u16,
    pub relay: i64,
    pub timeout_seconds: u64,
    pub relay_pause_seconds: i64,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(default)]
pub struct MillConfig {
    pub enabled: bool,
    pub ip: String,
    pub temp_type: String,
    pub heat_on_temp: f64,
    pub heat_off_temp: f64,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(default)]
pub struct GlamoxConfig {
    pub enabled: bool,
    pub room_name: String,
    pub heat_on_temp: f64,
    pub heat_off_temp: f64,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(default)]
pub struct CacheConfig {
    pub google_max_age_hours: i64,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(default)]
pub struct SystemdConfig {
    pub interval_seconds: u64,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(default)]
pub struct StateDbConfig {
    pub path: String,
}

impl Default for Config {
    fn default() -> Self {
        Self {
            google: GoogleConfig::default(),
            sr201: Sr201Config::default(),
            mill: MillConfig::default(),
            glamox: GlamoxConfig::default(),
            cache: CacheConfig::default(),
            systemd: SystemdConfig::default(),
            state_db: StateDbConfig::default(),
            time_window_hours: 2,
        }
    }
}

impl Default for GoogleConfig {
    fn default() -> Self {
        Self {
            key_file: "service-account-key.json".to_string(),
            scopes: vec!["https://www.googleapis.com/auth/calendar.readonly".to_string()],
            calendar_id: String::new(),
            pray_id: String::new(),
        }
    }
}

impl Default for Sr201Config {
    fn default() -> Self {
        Self {
            enabled: false,
            ip: String::new(),
            port: 6722,
            relay: 1,
            timeout_seconds: 5,
            relay_pause_seconds: 5,
        }
    }
}

impl Default for MillConfig {
    fn default() -> Self {
        Self {
            enabled: true,
            ip: String::new(),
            temp_type: "Normal".to_string(),
            heat_on_temp: 21.0,
            heat_off_temp: 17.0,
        }
    }
}

impl Default for GlamoxConfig {
    fn default() -> Self {
        Self {
            enabled: true,
            room_name: "Storsalen".to_string(),
            heat_on_temp: 21.0,
            heat_off_temp: 17.0,
        }
    }
}

impl Default for CacheConfig {
    fn default() -> Self {
        Self {
            google_max_age_hours: 24,
        }
    }
}

impl Default for SystemdConfig {
    fn default() -> Self {
        Self {
            interval_seconds: 300,
        }
    }
}

impl Default for StateDbConfig {
    fn default() -> Self {
        Self {
            path: "config/relay_state.db".to_string(),
        }
    }
}

#[derive(Debug)]
struct Runtime {
    cfg: Config,
    conn: Connection,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
struct CalendarEvent {
    start: String,
    summary: String,
}

#[derive(Debug, Deserialize)]
struct GoogleServiceAccountKey {
    client_email: String,
    private_key: String,
    token_uri: Option<String>,
}

#[derive(Debug, Serialize)]
struct GoogleJwtClaims {
    iss: String,
    scope: String,
    aud: String,
    exp: i64,
    iat: i64,
}

#[derive(Debug, Deserialize)]
struct GoogleTokenResponse {
    access_token: String,
}

#[derive(Debug, Deserialize)]
struct GoogleCalendarEventsResponse {
    #[serde(default)]
    items: Vec<GoogleCalendarEventItem>,
}

#[derive(Debug, Deserialize)]
struct GoogleCalendarEventItem {
    start: GoogleCalendarEventStart,
    #[serde(default)]
    summary: Option<String>,
}

#[derive(Debug, Deserialize)]
struct GoogleCalendarEventStart {
    #[serde(rename = "dateTime")]
    date_time: Option<String>,
    date: Option<String>,
}

fn log_line(level: &str, message: impl AsRef<str>) {
    println!(
        "{} bedehus-rs {:<5} {}",
        Local::now().format("%Y-%m-%d %H:%M:%S"),
        level,
        message.as_ref()
    );
}

fn resolve_path(base_dir: &Path, raw_path: &str) -> PathBuf {
    let path = PathBuf::from(raw_path);
    if path.is_absolute() {
        path
    } else {
        base_dir.join(path)
    }
}

fn load_config(base_dir: &Path, config_path: &Path) -> Result<Config> {
    let resolved = if config_path.is_absolute() {
        config_path.to_path_buf()
    } else {
        base_dir.join(config_path)
    };
    let text = fs::read_to_string(&resolved)
        .with_context(|| format!("Kunne ikke lese config {}", resolved.display()))?;
    let mut cfg: Config = serde_json::from_str(&text)
        .with_context(|| format!("Ugyldig JSON i {}", resolved.display()))?;
    if cfg.time_window_hours <= 0 {
        cfg.time_window_hours = 2;
    }
    if cfg.sr201.relay_pause_seconds <= 0 {
        cfg.sr201.relay_pause_seconds = 5;
    }
    if cfg.cache.google_max_age_hours <= 0 {
        cfg.cache.google_max_age_hours = 24;
    }
    if cfg.systemd.interval_seconds == 0 {
        cfg.systemd.interval_seconds = 300;
    }
    validate_config(&cfg)?;
    Ok(cfg)
}

fn validate_config(cfg: &Config) -> Result<()> {
    if cfg.google.key_file.trim().is_empty() {
        return Err(anyhow!("google.key_file is required"));
    }
    if cfg.google.calendar_id.trim().is_empty() {
        return Err(anyhow!("google.calendar_id is required"));
    }
    if cfg.google.pray_id.trim().is_empty() {
        return Err(anyhow!("google.pray_id is required"));
    }
    if cfg.sr201.enabled {
        if cfg.sr201.ip.trim().is_empty() {
            return Err(anyhow!("sr201.ip is required when sr201 is enabled"));
        }
        if !(1..=8).contains(&cfg.sr201.relay) {
            return Err(anyhow!(
                "sr201.relay must be 1-8 when sr201 is enabled, got {}",
                cfg.sr201.relay
            ));
        }
        if cfg.sr201.port == 0 {
            return Err(anyhow!("sr201.port must be > 0 when sr201 is enabled"));
        }
        if cfg.sr201.timeout_seconds == 0 {
            return Err(anyhow!(
                "sr201.timeout_seconds must be > 0 when sr201 is enabled"
            ));
        }
    }
    Ok(())
}

fn open_state_db(path: &Path) -> Result<Connection> {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent)?;
    }
    let conn = Connection::open(path)?;
    conn.execute_batch(
        r#"
        CREATE TABLE IF NOT EXISTS calendar_cache (
            calendar_id TEXT NOT NULL,
            window_start TEXT NOT NULL,
            window_end TEXT NOT NULL,
            fetched_at TEXT NOT NULL,
            events_json TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_calendar_cache_lookup
        ON calendar_cache(calendar_id, fetched_at);
        CREATE TABLE IF NOT EXISTS relay_state (
            id INTEGER PRIMARY KEY CHECK(id = 1),
            state INTEGER NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS heat_zone_state (
            zone TEXT PRIMARY KEY,
            state INTEGER NOT NULL,
            updated_at TEXT NOT NULL
        );
        "#,
    )?;
    Ok(conn)
}

fn load_runtime(base_dir: &Path, config_path: &Path) -> Result<Runtime> {
    let cfg = load_config(base_dir, config_path)?;
    let state_path = resolve_path(base_dir, &cfg.state_db.path);
    let conn = open_state_db(&state_path)?;
    Ok(Runtime { cfg, conn })
}

fn read_relay_state(conn: &Connection) -> Result<bool> {
    let row = conn
        .query_row("SELECT state FROM relay_state WHERE id = 1", [], |row| {
            row.get::<_, i64>(0)
        })
        .optional()?;
    Ok(row.unwrap_or(0) != 0)
}

fn save_relay_state(conn: &Connection, state: bool) -> Result<()> {
    conn.execute(
        r#"
        INSERT INTO relay_state (id, state, updated_at)
        VALUES (1, ?, ?)
        ON CONFLICT(id) DO UPDATE SET state=excluded.state, updated_at=excluded.updated_at
        "#,
        params![if state { 1 } else { 0 }, Utc::now().to_rfc3339()],
    )?;
    Ok(())
}

fn read_heat_zone_state(conn: &Connection, zone: &str) -> Result<bool> {
    let row = conn
        .query_row(
            "SELECT state FROM heat_zone_state WHERE zone = ?",
            [zone],
            |row| row.get::<_, i64>(0),
        )
        .optional()?;
    Ok(row.unwrap_or(0) != 0)
}

fn save_heat_zone_state(conn: &Connection, zone: &str, state: bool) -> Result<()> {
    conn.execute(
        r#"
        INSERT INTO heat_zone_state (zone, state, updated_at)
        VALUES (?, ?, ?)
        ON CONFLICT(zone) DO UPDATE SET state=excluded.state, updated_at=excluded.updated_at
        "#,
        params![zone, if state { 1 } else { 0 }, Utc::now().to_rfc3339()],
    )?;
    Ok(())
}

fn heat_zone_transition_target(
    conn: &Connection,
    zone: &str,
    heat_on: bool,
    heat_on_temp: f64,
    heat_off_temp: f64,
) -> Result<Option<f64>> {
    let last_state = read_heat_zone_state(conn, zone)?;
    save_heat_zone_state(conn, zone, heat_on)?;

    if heat_on == last_state {
        log_line(
            "INFO",
            format!("{zone} heat state unchanged ({heat_on}); skipping temperature update."),
        );
        return Ok(None);
    }

    log_line(
        "INFO",
        format!("{zone} heat state changed: {last_state} -> {heat_on}"),
    );
    Ok(Some(if heat_on { heat_on_temp } else { heat_off_temp }))
}

fn save_calendar_cache(
    conn: &Connection,
    calendar_id: &str,
    start_time: DateTime<Utc>,
    end_time: DateTime<Utc>,
    events: &[CalendarEvent],
) -> Result<()> {
    conn.execute(
        r#"
        INSERT INTO calendar_cache (calendar_id, window_start, window_end, fetched_at, events_json)
        VALUES (?, ?, ?, ?, ?)
        "#,
        params![
            calendar_id,
            start_time.to_rfc3339(),
            end_time.to_rfc3339(),
            Utc::now().to_rfc3339(),
            serde_json::to_string(events)?,
        ],
    )?;
    Ok(())
}

fn load_calendar_cache(
    conn: &Connection,
    calendar_id: &str,
    start_time: DateTime<Utc>,
    max_age_hours: i64,
) -> Result<Option<Vec<CalendarEvent>>> {
    let cutoff = Utc::now() - Duration::hours(max_age_hours);
    let row = conn
        .query_row(
            r#"
            SELECT events_json
            FROM calendar_cache
            WHERE calendar_id = ?
              AND fetched_at >= ?
              AND window_end >= ?
            ORDER BY fetched_at DESC
            LIMIT 1
            "#,
            params![calendar_id, cutoff.to_rfc3339(), start_time.to_rfc3339()],
            |row| row.get::<_, String>(0),
        )
        .optional()?;
    row.map(|value| serde_json::from_str::<Vec<CalendarEvent>>(&value).map_err(Into::into))
        .transpose()
}

fn google_http_client() -> Result<Client> {
    Ok(Client::builder()
        .timeout(StdDuration::from_secs(20))
        .build()?)
}

fn fetch_google_access_token(client: &Client, cfg: &Config) -> Result<String> {
    let key_text = fs::read_to_string(&cfg.google.key_file).with_context(|| {
        format!(
            "Kunne ikke lese Google service account key {}",
            cfg.google.key_file
        )
    })?;
    let key: GoogleServiceAccountKey = serde_json::from_str(&key_text)
        .with_context(|| format!("Ugyldig JSON i Google key file {}", cfg.google.key_file))?;

    let token_uri = key
        .token_uri
        .unwrap_or_else(|| "https://oauth2.googleapis.com/token".to_string());
    let now = Utc::now().timestamp();
    let claims = GoogleJwtClaims {
        iss: key.client_email,
        scope: cfg.google.scopes.join(" "),
        aud: token_uri.clone(),
        iat: now,
        exp: now + 3600,
    };

    let assertion = encode(
        &Header::new(Algorithm::RS256),
        &claims,
        &EncodingKey::from_rsa_pem(key.private_key.as_bytes())?,
    )?;

    let response = client
        .post(&token_uri)
        .form(&[
            ("grant_type", "urn:ietf:params:oauth:grant-type:jwt-bearer"),
            ("assertion", assertion.as_str()),
        ])
        .send()?
        .error_for_status()?
        .json::<GoogleTokenResponse>()?;

    Ok(response.access_token)
}

fn fetch_google_calendar_events(
    cfg: &Config,
    calendar_id: &str,
    start_time: DateTime<Utc>,
    end_time: DateTime<Utc>,
) -> Result<Vec<CalendarEvent>> {
    let client = google_http_client()?;
    let token = fetch_google_access_token(&client, cfg)?;
    let url = format!(
        "https://www.googleapis.com/calendar/v3/calendars/{calendar_id}/events"
    );
    let response = client
        .get(url)
        .bearer_auth(token)
        .query(&[
            ("timeMin", start_time.to_rfc3339().replace("+00:00", "Z")),
            ("timeMax", end_time.to_rfc3339().replace("+00:00", "Z")),
            ("singleEvents", "true".to_string()),
            ("orderBy", "startTime".to_string()),
        ])
        .send()?
        .error_for_status()?
        .json::<GoogleCalendarEventsResponse>()?;

    Ok(response
        .items
        .into_iter()
        .map(|item| CalendarEvent {
            start: item
                .start
                .date_time
                .or(item.start.date)
                .unwrap_or_else(|| "unknown".to_string()),
            summary: item
                .summary
                .unwrap_or_else(|| "No Summary Available".to_string()),
        })
        .collect())
}

fn get_calendar_events_with_fallback(
    conn: &Connection,
    cfg: &Config,
    calendar_id: &str,
    start_time: DateTime<Utc>,
    end_time: DateTime<Utc>,
) -> Result<Vec<CalendarEvent>> {
    match fetch_google_calendar_events(cfg, calendar_id, start_time, end_time) {
        Ok(events) => {
            save_calendar_cache(conn, calendar_id, start_time, end_time, &events)?;
            Ok(events)
        }
        Err(err) => {
            log_line(
                "WARN",
                format!("Google API unavailable for {calendar_id}: {err}. Trying cache."),
            );
            if let Some(events) = load_calendar_cache(
                conn,
                calendar_id,
                start_time,
                cfg.cache.google_max_age_hours,
            )? {
                log_line(
                    "WARN",
                    format!(
                        "Using cached calendar data for {calendar_id} (max age {}h)",
                        cfg.cache.google_max_age_hours
                    ),
                );
                Ok(events)
            } else {
                log_line(
                    "WARN",
                    format!(
                        "No cached calendar data for {calendar_id}; assuming no upcoming events"
                    ),
                );
                Ok(Vec::new())
            }
        }
    }
}

fn process_events(zone: &str, events: &[CalendarEvent]) -> bool {
    if events.is_empty() {
        log_line(
            "INFO",
            format!("No upcoming events found for {zone}; heat not required"),
        );
        return false;
    }

    log_line(
        "INFO",
        format!(
            "Found {} upcoming event(s) for {zone}; heat required",
            events.len()
        ),
    );
    for event in events {
        log_line(
            "INFO",
            format!("  Event start: {} Summary: {}", event.start, event.summary),
        );
    }
    true
}

fn sr201_addr(cfg: &Config) -> String {
    format!("{}:{}", cfg.sr201.ip, cfg.sr201.port)
}

fn sr201_send_command(cfg: &Config, command: &str) -> Result<String> {
    let timeout = StdDuration::from_secs(cfg.sr201.timeout_seconds);
    let addr = sr201_addr(cfg);
    let socket_addr = addr
        .to_socket_addrs()
        .with_context(|| format!("Kunne ikke slå opp SR201-adresse {addr}"))?
        .next()
        .ok_or_else(|| anyhow!("Ingen gyldig SR201-adresse funnet for {addr}"))?;
    let mut stream = TcpStream::connect_timeout(&socket_addr, timeout)
        .with_context(|| format!("Kunne ikke koble til SR201 på {addr}"))?;
    stream.set_read_timeout(Some(timeout))?;
    stream.set_write_timeout(Some(timeout))?;
    stream.write_all(command.as_bytes())?;

    let mut buf = [0_u8; 4096];
    let n = stream.read(&mut buf)?;
    Ok(String::from_utf8_lossy(&buf[..n]).trim().to_string())
}

fn sr201_status(cfg: &Config) -> Result<bool> {
    let resp = sr201_send_command(cfg, "00")?;
    let idx = (cfg.sr201.relay - 1) as usize;
    if idx >= resp.len() {
        return Err(anyhow!(
            "relay {} out of range (response length {})",
            cfg.sr201.relay,
            resp.len()
        ));
    }
    Ok(resp.as_bytes()[idx] == b'1')
}

fn sr201_close_relay(cfg: &Config) -> Result<()> {
    sr201_send_command(cfg, &format!("1{}", cfg.sr201.relay))?;
    Ok(())
}

fn sr201_open_relay(cfg: &Config) -> Result<()> {
    sr201_send_command(cfg, &format!("2{}", cfg.sr201.relay))?;
    Ok(())
}

fn sr201_sleep_pause(cfg: &Config) {
    thread::sleep(StdDuration::from_secs(cfg.sr201.relay_pause_seconds as u64));
}

fn sr201_heat_on(cfg: &Config) -> Result<()> {
    sr201_close_relay(cfg)?;
    sr201_sleep_pause(cfg);
    sr201_open_relay(cfg)?;
    sr201_sleep_pause(cfg);
    sr201_close_relay(cfg)?;
    Ok(())
}

fn sr201_heat_off(cfg: &Config) -> Result<()> {
    sr201_close_relay(cfg)?;
    sr201_sleep_pause(cfg);
    sr201_open_relay(cfg)?;
    sr201_sleep_pause(cfg);
    sr201_close_relay(cfg)?;
    sr201_sleep_pause(cfg);
    sr201_open_relay(cfg)?;
    Ok(())
}

fn update_storsalen_glamox(cfg: &Config, heat_on: bool, dry_run: bool) {
    if !cfg.glamox.enabled {
        log_line("INFO", "Glamox disabled; skipping update.");
        return;
    }

    let target = if heat_on {
        cfg.glamox.heat_on_temp
    } else {
        cfg.glamox.heat_off_temp
    };
    log_line(
        "INFO",
        format!(
            "Glamox Rust driver not implemented yet; would set {} to {:.1}C{}",
            cfg.glamox.room_name,
            target,
            if dry_run { " (dry-run)" } else { "" }
        ),
    );
}

fn check_update_pray(conn: &Connection, cfg: &Config, heat_on: bool, dry_run: bool) -> Result<()> {
    if !cfg.mill.enabled {
        log_line("INFO", "Mill disabled; skipping PRAY update.");
        return Ok(());
    }

    let Some(target) = heat_zone_transition_target(
        conn,
        "pray",
        heat_on,
        cfg.mill.heat_on_temp,
        cfg.mill.heat_off_temp,
    )?
    else {
        return Ok(());
    };

    log_line(
        "INFO",
        format!(
            "Mill Rust driver not implemented yet; would set PRAY to {:.1}C{}",
            target,
            if dry_run { " (dry-run)" } else { "" }
        ),
    );
    Ok(())
}

fn check_relay_state(
    conn: &Connection,
    cfg: &Config,
    heat_on: bool,
    dry_run: bool,
) -> Result<Option<bool>> {
    let last_state = read_relay_state(conn)?;
    log_line("INFO", format!("Last state: {last_state}"));

    if !cfg.sr201.enabled {
        log_line("INFO", "SR201 disabled; skipping relay operations.");
        save_relay_state(conn, heat_on)?;
        if heat_on != last_state {
            log_line("INFO", "Change of state detected");
            return Ok(Some(heat_on));
        }
        return Ok(None);
    }

    let relay_status = sr201_status(cfg)?;
    save_relay_state(conn, heat_on)?;

    if heat_on != last_state {
        log_line("INFO", "Change of state detected");
    }

    if heat_on {
        if !relay_status {
            log_line(
                "INFO",
                format!(
                    "Turning heat on via SR201 relay {}{}.",
                    cfg.sr201.relay,
                    if dry_run { " (dry-run)" } else { "" }
                ),
            );
            if !dry_run {
                sr201_heat_on(cfg)?;
            }
            return Ok(Some(true));
        }

        log_line("INFO", "Relay is already on, not turning heat on.");
        return Ok(None);
    }

    if relay_status {
        log_line(
            "INFO",
            format!(
                "Turning heat off via SR201 relay {}{}.",
                cfg.sr201.relay,
                if dry_run { " (dry-run)" } else { "" }
            ),
        );
        if !dry_run {
            sr201_heat_off(cfg)?;
        }
        return Ok(Some(false));
    }

    log_line("INFO", "Relay is already off, not turning heat off.");
    Ok(None)
}

fn timed<T, F>(timing: &mut BTreeMap<String, f64>, name: &str, mut f: F) -> Result<T>
where
    F: FnMut() -> Result<T>,
{
    let start = Instant::now();
    let out = f()?;
    timing.insert(name.to_string(), start.elapsed().as_secs_f64() * 1000.0);
    Ok(out)
}

fn run_cycle(conn: &Connection, cfg: &Config, dry_run: bool) -> Result<()> {
    let mut timing = BTreeMap::new();
    let current_time = Utc::now();
    let end_time = current_time + Duration::hours(cfg.time_window_hours);

    let events = timed(&mut timing, "calendar_storsalen", || {
        get_calendar_events_with_fallback(
            conn,
            cfg,
            &cfg.google.calendar_id,
            current_time,
            end_time,
        )
    })?;
    let heat_on = process_events("storsalen", &events);

    let glamox_update = timed(&mut timing, "sr201_logic", || {
        check_relay_state(conn, cfg, heat_on, dry_run)
    })?;

    timed(&mut timing, "glamox_logic", || {
        if let Some(heat_on) = glamox_update {
            update_storsalen_glamox(cfg, heat_on, dry_run);
        }
        Ok(())
    })?;

    let pray_events = timed(&mut timing, "calendar_pray", || {
        get_calendar_events_with_fallback(conn, cfg, &cfg.google.pray_id, current_time, end_time)
    })?;
    let pray_heat_on = process_events("pray", &pray_events);

    timed(&mut timing, "mill_logic", || {
        check_update_pray(conn, cfg, pray_heat_on, dry_run)
    })?;

    let pretty = timing
        .iter()
        .map(|(key, value)| format!("{key}={value:.1}ms"))
        .collect::<Vec<_>>()
        .join(", ");
    log_line("INFO", format!("Timing summary: {pretty}"));
    Ok(())
}

fn file_mtime(path: &Path) -> Option<SystemTime> {
    fs::metadata(path).ok()?.modified().ok()
}

fn flatten_config(prefix: &str, value: &Value, out: &mut BTreeMap<String, String>) {
    match value {
        Value::Object(map) => {
            for (key, value) in map {
                let next_prefix = if prefix.is_empty() {
                    key.clone()
                } else {
                    format!("{prefix}.{key}")
                };
                flatten_config(&next_prefix, value, out);
            }
        }
        _ => {
            out.insert(prefix.to_string(), value.to_string());
        }
    }
}

fn config_diff_summary(old_cfg: &Config, new_cfg: &Config, max_items: usize) -> String {
    let old_value = serde_json::to_value(old_cfg).unwrap_or(Value::Null);
    let new_value = serde_json::to_value(new_cfg).unwrap_or(Value::Null);
    let mut old_flat = BTreeMap::new();
    let mut new_flat = BTreeMap::new();
    flatten_config("", &old_value, &mut old_flat);
    flatten_config("", &new_value, &mut new_flat);
    let mut changes = Vec::new();
    let keys = old_flat
        .keys()
        .chain(new_flat.keys())
        .cloned()
        .collect::<std::collections::BTreeSet<_>>();
    for key in keys {
        let old_val = old_flat
            .get(&key)
            .cloned()
            .unwrap_or_else(|| "<missing>".to_string());
        let new_val = new_flat
            .get(&key)
            .cloned()
            .unwrap_or_else(|| "<missing>".to_string());
        if old_val != new_val {
            changes.push(format!("{key}: {old_val} -> {new_val}"));
        }
    }
    if changes.is_empty() {
        return "no config value changes".to_string();
    }
    if changes.len() > max_items {
        let shown = changes[..max_items].join(", ");
        return format!("{shown} (+{} more)", changes.len() - max_items);
    }
    changes.join(", ")
}

pub fn controller_run_once(args: &ControllerArgs) -> Result<()> {
    let base_dir = env::current_dir()?;
    let runtime = load_runtime(&base_dir, &args.config)?;
    log_line(
        "INFO",
        format!(
            "controller-run-once starting (config={}, dry_run={})",
            args.config.display(),
            args.dry_run
        ),
    );
    run_cycle(&runtime.conn, &runtime.cfg, args.dry_run)
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::path::Path;

    fn minimal_valid_config() -> Config {
        Config {
            google: GoogleConfig {
                key_file: "key.json".to_string(),
                calendar_id: "cal@group.calendar.google.com".to_string(),
                pray_id: "pray@group.calendar.google.com".to_string(),
                ..Default::default()
            },
            ..Default::default()
        }
    }

    #[test]
    fn validate_config_defaults_fail_missing_required_fields() {
        assert!(validate_config(&Config::default()).is_err());
    }

    #[test]
    fn validate_config_valid_config_passes() {
        assert!(validate_config(&minimal_valid_config()).is_ok());
    }

    #[test]
    fn validate_config_empty_calendar_id_fails() {
        let mut cfg = minimal_valid_config();
        cfg.google.calendar_id = String::new();
        assert!(validate_config(&cfg).is_err());
    }

    #[test]
    fn validate_config_sr201_enabled_requires_ip() {
        let mut cfg = minimal_valid_config();
        cfg.sr201.enabled = true;
        cfg.sr201.relay = 1;
        // ip is empty
        assert!(validate_config(&cfg).is_err());
    }

    #[test]
    fn validate_config_sr201_relay_out_of_range_fails() {
        let mut cfg = minimal_valid_config();
        cfg.sr201.enabled = true;
        cfg.sr201.ip = "192.168.1.1".to_string();
        cfg.sr201.relay = 0;
        assert!(validate_config(&cfg).is_err());

        cfg.sr201.relay = 9;
        assert!(validate_config(&cfg).is_err());
    }

    #[test]
    fn validate_config_sr201_enabled_zero_port_fails() {
        let mut cfg = minimal_valid_config();
        cfg.sr201.enabled = true;
        cfg.sr201.ip = "192.168.1.1".to_string();
        cfg.sr201.relay = 1;
        cfg.sr201.port = 0;
        assert!(validate_config(&cfg).is_err());
    }

    #[test]
    fn resolve_path_absolute_is_unchanged() {
        let result = resolve_path(Path::new("/some/base"), "/absolute/path");
        assert_eq!(result, PathBuf::from("/absolute/path"));
    }

    #[test]
    fn resolve_path_relative_is_joined_to_base() {
        let result = resolve_path(Path::new("/some/base"), "relative/path");
        assert_eq!(result, PathBuf::from("/some/base/relative/path"));
    }

    #[test]
    fn flatten_config_nested_object() {
        let value = serde_json::json!({"a": {"b": 1, "c": true}, "d": "hello"});
        let mut out = BTreeMap::new();
        flatten_config("", &value, &mut out);
        assert_eq!(out["a.b"], "1");
        assert_eq!(out["a.c"], "true");
        assert_eq!(out["d"], "\"hello\"");
    }

    #[test]
    fn flatten_config_with_prefix() {
        let value = serde_json::json!({"x": 42});
        let mut out = BTreeMap::new();
        flatten_config("root", &value, &mut out);
        assert_eq!(out["root.x"], "42");
    }

    #[test]
    fn config_diff_summary_no_changes() {
        let cfg = minimal_valid_config();
        let result = config_diff_summary(&cfg, &cfg, 10);
        assert_eq!(result, "no config value changes");
    }

    #[test]
    fn config_diff_summary_detects_changed_field() {
        let old = minimal_valid_config();
        let mut new = old.clone();
        new.time_window_hours = 4;
        let result = config_diff_summary(&old, &new, 10);
        assert!(result.contains("time_window_hours"));
        assert!(result.contains("2"));
        assert!(result.contains("4"));
    }

    #[test]
    fn config_diff_summary_truncates_at_max_items() {
        let old = minimal_valid_config();
        let mut new = old.clone();
        new.time_window_hours = 4;
        new.sr201.enabled = true;
        new.sr201.ip = "1.2.3.4".to_string();
        new.mill.heat_on_temp = 22.0;
        new.glamox.heat_on_temp = 23.0;
        let result = config_diff_summary(&old, &new, 2);
        assert!(result.contains("more"));
    }
}

pub fn controller_daemon(args: &ControllerArgs) -> Result<()> {
    let base_dir = env::current_dir()?;
    let config_path = if args.config.is_absolute() {
        args.config.clone()
    } else {
        base_dir.join(&args.config)
    };

    let stop_event = Arc::new(AtomicBool::new(false));
    let reload_event = Arc::new(AtomicBool::new(false));
    flag::register(SIGTERM, Arc::clone(&stop_event))?;
    flag::register(SIGINT, Arc::clone(&stop_event))?;
    flag::register(SIGHUP, Arc::clone(&reload_event))?;

    let mut runtime = load_runtime(&base_dir, &args.config)?;
    let mut config_mtime = file_mtime(&config_path);
    let mut interval_seconds = args
        .interval_seconds
        .unwrap_or(runtime.cfg.systemd.interval_seconds)
        .max(1);

    log_line(
        "INFO",
        format!(
            "controller-daemon started (interval={}s, dry_run={})",
            interval_seconds, args.dry_run
        ),
    );

    while !stop_event.load(Ordering::Relaxed) {
        let current_mtime = file_mtime(&config_path);
        let config_file_changed =
            current_mtime.is_some() && config_mtime.is_some() && current_mtime != config_mtime;
        if reload_event.swap(false, Ordering::Relaxed) || config_file_changed {
            let reason = if config_file_changed {
                "config file changed"
            } else {
                "SIGHUP"
            };
            log_line("INFO", format!("Reloading runtime config ({reason})..."));
            match load_runtime(&base_dir, &args.config) {
                Ok(new_runtime) => {
                    let diff = config_diff_summary(&runtime.cfg, &new_runtime.cfg, 20);
                    runtime = new_runtime;
                    if args.interval_seconds.is_none() {
                        interval_seconds = runtime.cfg.systemd.interval_seconds.max(1);
                    }
                    config_mtime = file_mtime(&config_path);
                    log_line("INFO", format!("Config changes: {diff}"));
                    log_line("INFO", "Runtime config reload completed");
                }
                Err(err) => {
                    log_line(
                        "WARN",
                        format!("Config reload failed; keeping current runtime: {err:#}"),
                    );
                }
            }
        }

        if let Err(err) = run_cycle(&runtime.conn, &runtime.cfg, args.dry_run) {
            log_line("WARN", format!("Error in cycle: {err:#}"));
        }

        let deadline = Instant::now() + StdDuration::from_secs(interval_seconds);
        while Instant::now() < deadline {
            if stop_event.load(Ordering::Relaxed) || reload_event.load(Ordering::Relaxed) {
                break;
            }
            thread::sleep(StdDuration::from_millis(200));
        }
    }

    log_line("INFO", "controller-daemon stopped");
    Ok(())
}
