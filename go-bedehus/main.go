package main

import (
	"context"
	"flag"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"time"

	"go-bedehus/internal/config"
	"go-bedehus/internal/gcal"
	"go-bedehus/internal/glamox"
	"go-bedehus/internal/logging"
	"go-bedehus/internal/mill"
	"go-bedehus/internal/sr201"
	"go-bedehus/internal/state"
	"google.golang.org/api/calendar/v3"
)

func main() {
	configPath := flag.String("config", "config/config.json", "path to config.json")
	flag.Parse()

	baseDir := resolveBaseDir()
	cfgPath := config.ResolvePath(baseDir, *configPath)
	if _, err := os.Stat(cfgPath); err != nil {
		if cwd, err := os.Getwd(); err == nil {
			altPath := config.ResolvePath(cwd, *configPath)
			if _, altErr := os.Stat(altPath); altErr == nil {
				cfgPath = altPath
			}
		}
	}

	cfg, err := config.Load(cfgPath)
	if err != nil {
		fmt.Fprintf(os.Stderr, "failed to load config: %v\n", err)
		os.Exit(1)
	}

	logger, closeLoggers := setupLogger(baseDir, cfg)
	defer closeLoggers()

	statePath := config.ResolvePath(baseDir, cfg.StateDB.Path)
	store, err := state.Open(statePath)
	if err != nil {
		logger.Errorf("Error opening state DB: %v", err)
		os.Exit(1)
	}
	defer store.Close()

	ctx := context.Background()
	service, err := gcal.NewService(ctx, config.ResolvePath(baseDir, cfg.Google.KeyFile), cfg.Google.Scopes)
	if err != nil {
		logger.Errorf("Error setting up Google Calendar client: %v", err)
		os.Exit(1)
	}

	glamoxClient, err := glamox.NewClient(baseDir, cfg.Glamox.RoomName, cfg.Glamox.APIURL)
	if err != nil {
		logger.Errorf("Error setting up Glamox client: %v", err)
		os.Exit(1)
	}

	millController := mill.New(cfg.Mill.IP, cfg.Mill.TempType)

	currentTime := time.Now().UTC()
	timeWindowEnd := currentTime.Add(time.Duration(cfg.TimeWindowHours) * time.Hour)

	// Storsalen
	events, err := gcal.EventsInWindow(service, cfg.Google.CalendarID, currentTime, timeWindowEnd)
	if err != nil {
		logger.Errorf("Error retrieving calendar events: %v", err)
		os.Exit(1)
	}

	heatOn := processEvents(logger, events)
	checkRelayState(logger, store, cfg, glamoxClient, heatOn)

	// Bønnerom
	events, err = gcal.EventsInWindow(service, cfg.Google.PrayID, currentTime, timeWindowEnd)
	if err != nil {
		logger.Errorf("Error retrieving calendar events: %v", err)
		os.Exit(1)
	}

	prayHeatOn := processEvents(logger, events)
	checkUpdatePray(logger, millController, cfg, prayHeatOn)
}

func resolveBaseDir() string {
	if base := os.Getenv("BEDEHUS_BASE_DIR"); base != "" {
		return base
	}
	exe, err := os.Executable()
	if err != nil {
		cwd, _ := os.Getwd()
		return cwd
	}
	exeDir := filepath.Dir(exe)
	if filepath.Base(exeDir) == "go-bedehus" {
		return filepath.Dir(exeDir)
	}
	return exeDir
}

func setupLogger(baseDir string, cfg config.Config) (*logging.Logger, func()) {
	var sinks []logging.Sink
	var closers []func() error

	hostname, _ := os.Hostname()

	if cfg.Logging.Console.Enabled {
		level, _ := logging.ParseLevel(cfg.Logging.Console.Level)
		sinks = append(sinks, logging.Sink{
			MinLevel: level,
			Writer:   os.Stdout,
			Format:   logging.SimpleFormatter(),
		})
	}

	if cfg.Logging.File.Enabled {
		level, _ := logging.ParseLevel(cfg.Logging.File.Level)
		path := config.ResolvePath(baseDir, cfg.Logging.File.Path)
		writer, err := logging.NewRotatingFileWriter(path, cfg.Logging.File.MaxBytes, cfg.Logging.File.BackupCount)
		if err == nil {
			sinks = append(sinks, logging.Sink{
				MinLevel: level,
				Writer:   writer,
				Format:   logging.SimpleFormatter(),
			})
			closers = append(closers, writer.Close)
		}
	}

	if cfg.Logging.Syslog.Enabled {
		level, _ := logging.ParseLevel(cfg.Logging.Syslog.Level)
		writer, err := logging.NewSyslogWriter(cfg.Logging.Syslog.Address)
		if err == nil {
			sinks = append(sinks, logging.Sink{
				MinLevel: level,
				Writer:   writer,
				Format:   logging.SyslogFormatter(),
			})
			closers = append(closers, writer.Close)
		}
	}

	if len(sinks) == 0 {
		sinks = append(sinks, logging.Sink{MinLevel: logging.LevelInfo, Writer: os.Stdout, Format: logging.SimpleFormatter()})
	}

	logger := logging.New("main", hostname, sinks)
	return logger, func() {
		for _, closeFn := range closers {
			_ = closeFn()
		}
	}
}

func processEvents(logger *logging.Logger, events []*calendar.Event) bool {
	heatOn := false
	if len(events) > 0 {
		logger.Infof("Relay turned ON for upcoming events: %d", len(events))
		for _, event := range events {
			start := event.Start.DateTime
			if start == "" {
				start = event.Start.Date
			}
			summary := event.Summary
			if strings.TrimSpace(summary) == "" {
				summary = "No Summary Available"
			}
			logger.Infof("Found event start: %s Summary: %s", start, summary)
		}
		heatOn = true
	} else {
		logger.Infof("Relay turned OFF (no upcoming events)")
	}
	return heatOn
}

func checkRelayState(logger *logging.Logger, store *state.Store, cfg config.Config, glamoxClient *glamox.Client, heatOn bool) {
	lastState, err := store.GetRelayState()
	if err != nil {
		logger.Errorf("Error reading relay state: %v", err)
		lastState = false
	}
	logger.Infof("Last state: %v", lastState)

	relayStatus, err := getRelayStatus(cfg)
	if err != nil {
		logger.Errorf("Error interacting with SR201: %v", err)
		return
	}

	if err := store.SetRelayState(heatOn); err != nil {
		logger.Errorf("Error saving relay state: %v", err)
	}

	heatLogic(logger, cfg, glamoxClient, heatOn, lastState, relayStatus)
}

func getRelayStatus(cfg config.Config) (bool, error) {
	client := sr201.Client{
		IP:      cfg.SR201.IP,
		Port:    cfg.SR201.Port,
		Relay:   cfg.SR201.Relay,
		Timeout: time.Duration(cfg.SR201.TimeoutSeconds) * time.Second,
	}
	return client.CheckStatus()
}

func heatLogic(logger *logging.Logger, cfg config.Config, glamoxClient *glamox.Client, heatOn bool, lastState bool, relayStatus bool) {
	if heatOn != lastState {
		logger.Infof("Change of state detected")
	}
	if heatOn {
		if !relayStatus {
			logger.Infof("Turning heat on.")
			if err := relayHeatOn(cfg); err != nil {
				logger.Errorf("Error turning heat on: %v", err)
				return
			}
			updateStorsalenGlamox(logger, glamoxClient, cfg.Glamox.HeatOnTemp)
		} else {
			logger.Infof("Relay is already on, not turning heat on.")
		}
		return
	}

	if relayStatus {
		logger.Infof("Turning heat off.")
		if err := relayHeatOff(cfg); err != nil {
			logger.Errorf("Error turning heat off: %v", err)
			return
		}
		updateStorsalenGlamox(logger, glamoxClient, cfg.Glamox.HeatOffTemp)
	} else {
		logger.Infof("Relay is already off, not turning heat off.")
	}
}

func relayHeatOn(cfg config.Config) error {
	client := sr201.Client{
		IP:      cfg.SR201.IP,
		Port:    cfg.SR201.Port,
		Relay:   cfg.SR201.Relay,
		Timeout: time.Duration(cfg.SR201.TimeoutSeconds) * time.Second,
	}
	if err := client.CloseRelay(); err != nil {
		return err
	}
	time.Sleep(5 * time.Second)
	if err := client.OpenRelay(); err != nil {
		return err
	}
	time.Sleep(5 * time.Second)
	return client.CloseRelay()
}

func relayHeatOff(cfg config.Config) error {
	client := sr201.Client{
		IP:      cfg.SR201.IP,
		Port:    cfg.SR201.Port,
		Relay:   cfg.SR201.Relay,
		Timeout: time.Duration(cfg.SR201.TimeoutSeconds) * time.Second,
	}
	if err := client.CloseRelay(); err != nil {
		return err
	}
	time.Sleep(5 * time.Second)
	if err := client.OpenRelay(); err != nil {
		return err
	}
	time.Sleep(5 * time.Second)
	if err := client.CloseRelay(); err != nil {
		return err
	}
	time.Sleep(5 * time.Second)
	return client.OpenRelay()
}

func updateStorsalenGlamox(logger *logging.Logger, client *glamox.Client, temp float64) {
	if _, err := client.SetTemperature(temp); err != nil {
		logger.Errorf("Error setting Glamox temperature: %v", err)
		return
	}
	status, err := client.GetRoomStatus()
	if err != nil {
		logger.Errorf("Error getting Glamox status: %v", err)
		return
	}
	logger.Debugf("STORSALEN status: %v", status)
}

func checkUpdatePray(logger *logging.Logger, controller *mill.Controller, cfg config.Config, heatOn bool) {
	var target float64
	if heatOn {
		logger.Infof("Set PRAY heat to %.0fC.", cfg.Mill.HeatOnTemp)
		target = cfg.Mill.HeatOnTemp
	} else {
		logger.Infof("Set PRAY heat to %.0fC.", cfg.Mill.HeatOffTemp)
		target = cfg.Mill.HeatOffTemp
	}
	result, err := controller.SetTemperature(target)
	if err != nil {
		logger.Errorf("Error interacting with PRAY: %v", err)
		return
	}
	status, err := controller.GetControlStatus()
	if err == nil {
		logger.Debugf("%v", status)
	}
	logger.Infof("PRAY%v", result)
}
