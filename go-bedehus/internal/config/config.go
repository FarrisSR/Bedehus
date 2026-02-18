package config

import (
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"path/filepath"
)

type Config struct {
	Google          GoogleConfig  `json:"google"`
	SR201           SR201Config   `json:"sr201"`
	Mill            MillConfig    `json:"mill"`
	Glamox          GlamoxConfig  `json:"glamox"`
	Cache           CacheConfig   `json:"cache"`
	Timing          TimingConfig  `json:"timing"`
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
	Enabled           bool   `json:"enabled"`
	IP                string `json:"ip"`
	Port              int    `json:"port"`
	Relay             int    `json:"relay"`
	TimeoutSeconds    int    `json:"timeout_seconds"`
	RelayPauseSeconds int    `json:"relay_pause_seconds"`
}

type MillConfig struct {
	Enabled     bool    `json:"enabled"`
	IP          string  `json:"ip"`
	TempType    string  `json:"temp_type"`
	HeatOnTemp  float64 `json:"heat_on_temp"`
	HeatOffTemp float64 `json:"heat_off_temp"`
}

type GlamoxConfig struct {
	Enabled     bool    `json:"enabled"`
	RoomName    string  `json:"room_name"`
	APIURL      string  `json:"api_url"`
	HeatOnTemp  float64 `json:"heat_on_temp"`
	HeatOffTemp float64 `json:"heat_off_temp"`
}

type CacheConfig struct {
	GoogleMaxAgeHours int `json:"google_max_age_hours"`
}

type TimingConfig struct {
	Enabled bool `json:"enabled"`
}

type LoggingConfig struct {
	PythonConfigFile string        `json:"python_config_file"`
	Console          LogSinkConfig `json:"console"`
	File             LogFileConfig `json:"file"`
	Syslog           LogSinkConfig `json:"syslog"`
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
			Enabled:           false,
			Port:              6722,
			Relay:             1,
			TimeoutSeconds:    5,
			RelayPauseSeconds: 5,
		},
		Mill: MillConfig{
			Enabled:     true,
			TempType:    "Normal",
			HeatOnTemp:  21,
			HeatOffTemp: 17,
		},
		Glamox: GlamoxConfig{
			Enabled:     true,
			HeatOnTemp:  24,
			HeatOffTemp: 18,
		},
		Cache: CacheConfig{
			GoogleMaxAgeHours: 24,
		},
		Timing: TimingConfig{
			Enabled: false,
		},
		Logging: LoggingConfig{
			PythonConfigFile: "logging.config",
			Console:          LogSinkConfig{Enabled: true, Level: "INFO"},
			File: LogFileConfig{
				Enabled:     false,
				Level:       "DEBUG",
				Path:        "BedehusTemperaturProgram.log",
				MaxBytes:    10 * 1024 * 1024,
				BackupCount: 31,
			},
			Syslog: LogSinkConfig{Enabled: true, Level: "INFO"},
		},
		TimeWindowHours: 5,
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
	if cfg.SR201.RelayPauseSeconds <= 0 {
		cfg.SR201.RelayPauseSeconds = 5
	}
	if cfg.Cache.GoogleMaxAgeHours <= 0 {
		cfg.Cache.GoogleMaxAgeHours = 24
	}
	if cfg.Logging.PythonConfigFile == "" {
		cfg.Logging.PythonConfigFile = "logging.config"
	}

	return cfg, nil
}

func (c Config) Validate() error {
	var errs []error

	if c.Google.KeyFile == "" {
		errs = append(errs, errors.New("google.key_file is required"))
	}
	if c.Google.CalendarID == "" {
		errs = append(errs, errors.New("google.calendar_id is required"))
	}
	if c.Google.PrayID == "" {
		errs = append(errs, errors.New("google.pray_id is required"))
	}
	if c.SR201.Enabled {
		if c.SR201.IP == "" {
			errs = append(errs, errors.New("sr201.ip is required when sr201 is enabled"))
		}
		if c.SR201.Relay < 1 || c.SR201.Relay > 8 {
			errs = append(errs, fmt.Errorf("sr201.relay must be 1-8 when sr201 is enabled, got %d", c.SR201.Relay))
		}
	}
	if c.Mill.Enabled && c.Mill.IP == "" {
		errs = append(errs, errors.New("mill.ip is required when mill is enabled"))
	}
	if c.Glamox.Enabled && c.Glamox.RoomName == "" {
		errs = append(errs, errors.New("glamox.room_name is required when glamox is enabled"))
	}
	if c.StateDB.Path == "" {
		errs = append(errs, errors.New("state_db.path is required"))
	}

	return errors.Join(errs...)
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
