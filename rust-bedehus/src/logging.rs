use std::net::UdpSocket;
use std::sync::Mutex;

use anyhow::Result;
use chrono::Local;

#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord)]
#[allow(dead_code)]
pub enum Level {
    Debug,
    Info,
    Warn,
    Error,
}

impl Level {
    pub fn as_str(self) -> &'static str {
        match self {
            Level::Debug => "DEBUG",
            Level::Info => "INFO",
            Level::Warn => "WARN",
            Level::Error => "ERROR",
        }
    }
}

pub struct Logger {
    pub name: String,
    pub hostname: String,
    syslog: Mutex<Option<UdpSocket>>,
    pub min_level: Level,
}

impl std::fmt::Debug for Logger {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("Logger")
            .field("name", &self.name)
            .field("hostname", &self.hostname)
            .field("min_level", &self.min_level)
            .finish()
    }
}

impl Logger {
    pub fn new(name: &str, syslog_addr: Option<&str>) -> Result<Self> {
        let hostname = read_hostname();
        let syslog = if let Some(addr) = syslog_addr {
            let socket = UdpSocket::bind("0.0.0.0:0")?;
            socket.connect(addr)?;
            Mutex::new(Some(socket))
        } else {
            Mutex::new(None)
        };
        Ok(Self {
            name: name.to_string(),
            hostname,
            syslog,
            min_level: Level::Info,
        })
    }

    pub fn log(&self, level: Level, message: &str, file: &str, line: u32) {
        if level < self.min_level {
            return;
        }
        let now = Local::now();
        let ts = format!(
            "{},{:03}",
            now.format("%Y-%m-%d %H:%M:%S"),
            now.timestamp_subsec_millis()
        );

        // Console: same format as Go SimpleFormatter
        println!("{ts} {:<12} {:<8} {message}", self.name, level.as_str());

        // Syslog: same format as Go SyslogFormatter
        if let Ok(guard) = self.syslog.lock() {
            if let Some(ref socket) = *guard {
                let file_short = file.rsplit('/').next().unwrap_or(file);
                let msg = format!(
                    "{ts} | {level} | {hostname} | {name}:{file_short}:{line} - {message}\n",
                    level = level.as_str(),
                    hostname = self.hostname,
                    name = self.name,
                );
                let _ = socket.send(msg.as_bytes());
            }
        }
    }
}

fn read_hostname() -> String {
    std::fs::read_to_string("/etc/hostname")
        .map(|s| s.trim().to_string())
        .unwrap_or_else(|_| "unknown".to_string())
}
