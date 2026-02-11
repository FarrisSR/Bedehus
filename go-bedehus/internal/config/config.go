package config

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
)

type Config struct {
	Google          GoogleConfig  `json:"google"`
	SR201           SR201Config   `json:"sr201"`
	Mill            MillConfig    `json:"mill"`
	Glamox          GlamoxConfig  `json:"glamox"`
	Logging         LoggingConfig `json:"logging"`
	StateDB         StateDBConfig `json:"state_db"`
	TimeWindowHours int           `json:"time_window_hours"`
}

type GoogleConfig struct {
	KeyFile    string   `json:"key_file"`
	Scopes     []string `json:"scopes"`
	CalendarID string   `json:"calendar_id"`
	PrayID     string   `json:"pray_id"`
}

type SR201Config struct {
	IP             string `json:"ip"`
	Port           int    `json:"port"`
	Relay          int    `json:"relay"`
	TimeoutSeconds int    `json:"timeout_seconds"`
}

type MillConfig struct {
	IP          string  `json:"ip"`
	TempType    string  `json:"temp_type"`
	HeatOnTemp  float64 `json:"heat_on_temp"`
	HeatOffTemp float64 `json:"heat_off_temp"`
}

type GlamoxConfig struct {
	RoomName    string  `json:"room_name"`
	APIURL      string  `json:"api_url"`
	HeatOnTemp  float64 `json:"heat_on_temp"`
	HeatOffTemp float64 `json:"heat_off_temp"`
}

type LoggingConfig struct {
	Console LogSinkConfig `json:"console"`
	File    LogFileConfig `json:"file"`
	Syslog  LogSinkConfig `json:"syslog"`
}

type LogSinkConfig struct {
	Enabled bool   `json:"enabled"`
	Level   string `json:"level"`
	Address string `json:"address"`
}

type LogFileConfig struct {
	Enabled     bool   `json:"enabled"`
	Level       string `json:"level"`
	Path        string `json:"path"`
	MaxBytes    int    `json:"max_bytes"`
	BackupCount int    `json:"backup_count"`
}

type StateDBConfig struct {
	Path string `json:"path"`
}

func DefaultConfig() Config {
	return Config{
		Google: GoogleConfig{
			Scopes: []string{"https://www.googleapis.com/auth/calendar.readonly"},
		},
		SR201: SR201Config{
			Port:           6722,
			Relay:          1,
			TimeoutSeconds: 5,
		},
		Mill: MillConfig{
			TempType:    "Normal",
			HeatOnTemp:  21,
			HeatOffTemp: 17,
		},
		Glamox: GlamoxConfig{
			HeatOnTemp:  21,
			HeatOffTemp: 17,
		},
		Logging: LoggingConfig{
			Console: LogSinkConfig{Enabled: true, Level: "INFO"},
			File: LogFileConfig{
				Enabled:     false,
				Level:       "DEBUG",
				Path:        "BedehusTemperaturProgram.log",
				MaxBytes:    1024,
				BackupCount: 31,
			},
			Syslog: LogSinkConfig{Enabled: true, Level: "INFO"},
		},
		TimeWindowHours: 2,
	}
}

func Load(path string) (Config, error) {
	cfg := DefaultConfig()

	data, err := os.ReadFile(path)
	if err != nil {
		return cfg, fmt.Errorf("read config: %w", err)
	}
	if err := json.Unmarshal(data, &cfg); err != nil {
		return cfg, fmt.Errorf("parse config: %w", err)
	}

	if cfg.TimeWindowHours <= 0 {
		cfg.TimeWindowHours = 2
	}

	return cfg, nil
}

func ResolvePath(baseDir, path string) string {
	if path == "" {
		return ""
	}
	if filepath.IsAbs(path) {
		return path
	}
	return filepath.Join(baseDir, path)
}
