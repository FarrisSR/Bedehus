mod arp;
mod controller;
mod db;
mod logging;
mod energy_report;
mod font;
mod temperature_report;

use std::path::PathBuf;

use anyhow::Result;
use clap::{Parser, Subcommand};

#[derive(Parser, Debug)]
#[command(name = "bedehus-rs")]
#[command(about = "Rust-MVP for Bedehus tooling")]
struct Cli {
    #[command(subcommand)]
    command: Command,
}

#[derive(Subcommand, Debug)]
enum Command {
    /// Importer ovnstatus per time fra arp-scan.jsonl til SQLite
    ImportArpPresence {
        #[arg(long, default_value = "../data/temperature_history.sqlite")]
        db: PathBuf,
        #[arg(long, default_value = "/var/log/bedehus/arp-scan.jsonl")]
        log_path: PathBuf,
        #[arg(long, default_value = "../scripts/arp_alias")]
        aliases_file: PathBuf,
    },
    /// Vis siste times status for Glamox-ovner fra ARP-importen
    HeaterStatus {
        #[arg(long, default_value = "../data/temperature_history.sqlite")]
        db: PathBuf,
    },
    /// Generer statisk temperatur-rapport (HTML + PNG)
    GenerateStaticReport {
        #[arg(long, default_value = "../data/temperature_history.sqlite")]
        db: PathBuf,
        #[arg(long, default_value_t = 48)]
        hours: i64,
        #[arg(long, default_value = "www/graphs/last_48h.png")]
        output_img: PathBuf,
        #[arg(long)]
        output_img_7d: Option<PathBuf>,
        #[arg(long)]
        output_img_30d: Option<PathBuf>,
        #[arg(long, default_value = "www/index.html")]
        output_html: PathBuf,
    },
    /// Generer statisk energi-rapport (HTML + PNG)
    GenerateEnergyReport {
        #[arg(long, default_value = "../data/energy_history.sqlite")]
        db: PathBuf,
        #[arg(long, default_value_t = 48)]
        hours: i64,
        #[arg(long, default_value = "../data/temperature_history.sqlite")]
        temp_db: PathBuf,
        #[arg(long, default_value = "yr")]
        temp_outdoor_source: String,
        #[arg(long, default_value = "Bjørkelangen ute")]
        temp_outdoor_room: String,
        #[arg(long, default_value = "mill")]
        temp_room_source: String,
        #[arg(long, default_value = "Bønnerom")]
        temp_room: String,
        #[arg(long, default_value = "www/graphs/energy_48h.png")]
        output_img: PathBuf,
        #[arg(long, default_value = "www/energy.html")]
        output_html: PathBuf,
    },
    /// Kjør én runde av varmestyringslogikken (foreløpig med no-op drivere)
    ControllerRunOnce {
        #[arg(long, default_value = "config/config.json")]
        config: PathBuf,
        #[arg(long)]
        dry_run: bool,
    },
    /// Kjør varmestyringslogikken i en vedvarende løkke for systemd (foreløpig med no-op drivere)
    ControllerDaemon {
        #[arg(long, default_value = "config/config.json")]
        config: PathBuf,
        #[arg(long)]
        interval_seconds: Option<u64>,
        #[arg(long)]
        dry_run: bool,
    },
}

fn main() -> Result<()> {
    let cli = Cli::parse();
    match cli.command {
        Command::ImportArpPresence {
            db,
            log_path,
            aliases_file,
        } => {
            let conn = db::open_temperature_db(&db)?;
            let summary = arp::import_arp_presence(&conn, &log_path, &aliases_file)?;
            println!(
                "Importerte ARP-presence: {} events, {} timer, {} aliaser, {} hourly-rader",
                summary.events_seen,
                summary.hours_written,
                summary.aliases_used,
                summary.hourly_rows_written
            );
        }
        Command::HeaterStatus { db } => {
            let conn = db::open_temperature_db(&db)?;
            let statuses = arp::fetch_latest_heater_presence_statuses(&conn)?;
            if statuses.is_empty() {
                println!("Ingen ovnstatus funnet i databasen.");
                return Ok(());
            }
            let online_count = statuses.iter().filter(|item| item.online).count();
            println!(
                "Siste time: {} ({} av {} online)",
                statuses[0].recorded_hour.to_rfc3339(),
                online_count,
                statuses.len()
            );
            for item in statuses {
                let state = if item.online { "online" } else { "nede" };
                let observed = item
                    .observed_at
                    .map(|value| value.to_rfc3339())
                    .unwrap_or_else(|| "-".to_string());
                println!(
                    "{}: {} (observert {}, ip={}, mac={})",
                    item.alias,
                    state,
                    observed,
                    item.ip.unwrap_or_else(|| "-".to_string()),
                    item.mac.unwrap_or_else(|| "-".to_string())
                );
            }
        }
        Command::GenerateStaticReport {
            db,
            hours,
            output_img,
            output_img_7d,
            output_img_30d,
            output_html,
        } => {
            let conn = db::open_temperature_db(&db)?;
            temperature_report::generate(
                &conn,
                &temperature_report::TemperatureReportArgs {
                    hours,
                    output_img,
                    output_img_7d,
                    output_img_30d,
                    output_html,
                },
            )?;
        }
        Command::GenerateEnergyReport {
            db,
            hours,
            temp_db,
            temp_outdoor_source,
            temp_outdoor_room,
            temp_room_source,
            temp_room,
            output_img,
            output_html,
        } => {
            let energy_conn = db::open_energy_db(&db)?;
            let temp_conn = db::open_temperature_db(&temp_db)?;
            energy_report::generate(
                &energy_conn,
                &temp_conn,
                &energy_report::EnergyReportArgs {
                    hours,
                    temp_outdoor_source,
                    temp_outdoor_room,
                    temp_room_source,
                    temp_room,
                    output_img,
                    output_html,
                },
            )?;
        }
        Command::ControllerRunOnce { config, dry_run } => {
            controller::controller_run_once(&controller::ControllerArgs {
                config,
                interval_seconds: None,
                dry_run,
            })?;
        }
        Command::ControllerDaemon {
            config,
            interval_seconds,
            dry_run,
        } => {
            controller::controller_daemon(&controller::ControllerArgs {
                config,
                interval_seconds,
                dry_run,
            })?;
        }
    }
    Ok(())
}
