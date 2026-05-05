package main

import (
	"context"
	"flag"
	"fmt"
	"os"
	"path/filepath"
	"sort"
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
	if err := run(); err != nil {
		fmt.Fprintf(os.Stderr, "error: %v\n", err)
		os.Exit(1)
	}
}

func run() error {
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
		return fmt.Errorf("failed to load config: %w", err)
	}

	if err := cfg.Validate(); err != nil {
		return fmt.Errorf("invalid config: %w", err)
	}

	logger, closeLoggers := setupLogger(baseDir, cfg)
	defer closeLoggers()
	timing := newStepTiming(cfg.Timing.Enabled)
	defer func() {
		if timing.Enabled {
			logger.Infof("Timing summary: %s", timing.Summary())
		}
	}()

	statePath := config.ResolvePath(baseDir, cfg.StateDB.Path)
	var store *state.Store
	err = timing.Track("state_db_open", func() error {
		var openErr error
		store, openErr = state.Open(statePath)
		return openErr
	})
	if err != nil {
		return fmt.Errorf("error opening state DB: %w", err)
	}
	defer store.Close()

	ctx := context.Background()
	var service *calendar.Service
	err = timing.Track("google_client", func() error {
		var svcErr error
		service, svcErr = gcal.NewService(ctx, config.ResolvePath(baseDir, cfg.Google.KeyFile), cfg.Google.Scopes)
		return svcErr
	})
	if err != nil {
		return fmt.Errorf("error setting up Google Calendar client: %w", err)
	}

	var glamoxClient *glamox.Client
	if cfg.Glamox.Enabled {
		glamoxClient, err = glamox.NewClient(baseDir, cfg.Glamox.RoomName, cfg.Glamox.APIURL)
		if err != nil {
			return fmt.Errorf("error setting up Glamox client: %w", err)
		}
	}

	var millController *mill.Controller
	if cfg.Mill.Enabled {
		millController = mill.New(cfg.Mill.IP, cfg.Mill.TempType)
	}

	currentTime := time.Now().UTC()
	timeWindowEnd := currentTime.Add(time.Duration(cfg.TimeWindowHours) * time.Hour)

	// Storsalen
	var events []*calendar.Event
	err = timing.Track("calendar_storsalen", func() error {
		var eventsErr error
		events, eventsErr = getEventsWithFallback(logger, store, cfg, service, cfg.Google.CalendarID, currentTime, timeWindowEnd)
		return eventsErr
	})
	if err != nil {
		return fmt.Errorf("error retrieving Storsalen calendar events: %w", err)
	}

	heatOn := processEvents(logger, events)
	var relayResult relayOutcome
	_ = timing.Track("sr201_logic", func() error {
		relayResult = checkRelayState(logger, store, cfg, heatOn)
		return nil
	})
	_ = timing.Track("glamox_logic", func() error {
		if relayResult.UpdateGlamox {
			updateStorsalenGlamox(logger, glamoxClient, relayResult.GlamoxTemp)
		}
		return nil
	})

	// Bønnerom
	err = timing.Track("calendar_pray", func() error {
		var eventsErr error
		events, eventsErr = getEventsWithFallback(logger, store, cfg, service, cfg.Google.PrayID, currentTime, timeWindowEnd)
		return eventsErr
	})
	if err != nil {
		return fmt.Errorf("error retrieving Bønnerom calendar events: %w", err)
	}

	prayHeatOn := processEvents(logger, events)
	_ = timing.Track("mill_logic", func() error {
		checkUpdatePray(logger, store, millController, cfg, prayHeatOn)
		return nil
	})

	return nil
}

type stepTiming struct {
	Name     string
	Duration time.Duration
}

type stepTimings struct {
	Enabled bool
	Entries []stepTiming
}

func newStepTiming(enabled bool) *stepTimings {
	return &stepTimings{Enabled: enabled}
}

func (s *stepTimings) Track(name string, fn func() error) error {
	if !s.Enabled {
		return fn()
	}
	start := time.Now()
	err := fn()
	s.Entries = append(s.Entries, stepTiming{Name: name, Duration: time.Since(start)})
	return err
}

func (s *stepTimings) Summary() string {
	if len(s.Entries) == 0 {
		return "no steps recorded"
	}
	entries := make([]stepTiming, len(s.Entries))
	copy(entries, s.Entries)
	sort.Slice(entries, func(i, j int) bool {
		return entries[i].Duration > entries[j].Duration
	})

	parts := make([]string, 0, len(entries))
	for _, entry := range entries {
		parts = append(parts, fmt.Sprintf("%s=%.1fms", entry.Name, float64(entry.Duration)/float64(time.Millisecond)))
	}
	return strings.Join(parts, ", ")
}

func getEventsWithFallback(
	logger *logging.Logger,
	store *state.Store,
	cfg config.Config,
	service *calendar.Service,
	calendarID string,
	start time.Time,
	end time.Time,
) ([]*calendar.Event, error) {
	events, err := gcal.EventsInWindow(service, calendarID, start, end)
	if err == nil {
		if saveErr := store.SaveCalendarCache(calendarID, start, end, events); saveErr != nil {
			logger.Warnf("Failed to save calendar cache for %s: %v", calendarID, saveErr)
		}
		return events, nil
	}

	logger.Errorf("Google Calendar request failed for %s: %v", calendarID, err)
	maxAge := time.Duration(cfg.Cache.GoogleMaxAgeHours) * time.Hour
	cachedEvents, ok, cacheErr := store.GetCachedEvents(calendarID, start, maxAge)
	if cacheErr != nil {
		return nil, fmt.Errorf("calendar request failed and cache read failed: %w (google error: %v)", cacheErr, err)
	}
	if !ok {
		return nil, err
	}
	logger.Warnf("Using cached calendar data for %s (max age %dh)", calendarID, cfg.Cache.GoogleMaxAgeHours)
	return cachedEvents, nil
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
		level, err := logging.ParseLevel(cfg.Logging.Console.Level)
		if err != nil {
			fmt.Fprintf(os.Stderr, "warning: console log level %q invalid, defaulting to INFO\n", cfg.Logging.Console.Level)
		}
		sinks = append(sinks, logging.Sink{
			MinLevel: level,
			Writer:   os.Stdout,
			Format:   logging.SimpleFormatter(),
		})
	}

	if cfg.Logging.File.Enabled {
		level, err := logging.ParseLevel(cfg.Logging.File.Level)
		if err != nil {
			fmt.Fprintf(os.Stderr, "warning: file log level %q invalid, defaulting to INFO\n", cfg.Logging.File.Level)
		}
		path := config.ResolvePath(baseDir, cfg.Logging.File.Path)
		writer, err := logging.NewRotatingFileWriter(path, cfg.Logging.File.MaxBytes, cfg.Logging.File.BackupCount)
		if err != nil {
			fmt.Fprintf(os.Stderr, "warning: failed to open log file %s: %v\n", path, err)
		} else {
			sinks = append(sinks, logging.Sink{
				MinLevel: level,
				Writer:   writer,
				Format:   logging.SimpleFormatter(),
			})
			closers = append(closers, writer.Close)
		}
	}

	if cfg.Logging.Syslog.Enabled {
		level, err := logging.ParseLevel(cfg.Logging.Syslog.Level)
		if err != nil {
			fmt.Fprintf(os.Stderr, "warning: syslog log level %q invalid, defaulting to INFO\n", cfg.Logging.Syslog.Level)
		}
		writer, err := logging.NewSyslogWriter(cfg.Logging.Syslog.Address)
		if err != nil {
			fmt.Fprintf(os.Stderr, "warning: failed to connect to syslog at %s: %v\n", cfg.Logging.Syslog.Address, err)
		} else {
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
	if len(events) == 0 {
		logger.Infof("No upcoming events found; heat not required")
		return false
	}
	logger.Infof("Found %d upcoming event(s); heat required", len(events))
	for _, event := range events {
		start := event.Start.DateTime
		if start == "" {
			start = event.Start.Date
		}
		summary := event.Summary
		if strings.TrimSpace(summary) == "" {
			summary = "No Summary Available"
		}
		logger.Infof("  Event start: %s Summary: %s", start, summary)
	}
	return true
}

type relayOutcome struct {
	UpdateGlamox bool
	GlamoxTemp   float64
}

func checkRelayState(logger *logging.Logger, store *state.Store, cfg config.Config, heatOn bool) relayOutcome {
	lastState, err := store.GetRelayState()
	if err != nil {
		logger.Errorf("Error reading relay state: %v", err)
		lastState = false
	}
	logger.Infof("Last state: %v", lastState)

	if !cfg.SR201.Enabled {
		logger.Infof("SR201 disabled; skipping relay operations.")
		if err := store.SetRelayState(heatOn); err != nil {
			logger.Errorf("Error saving relay state: %v", err)
		}
		if heatOn != lastState {
			logger.Infof("Change of state detected")
			if heatOn {
				return relayOutcome{UpdateGlamox: true, GlamoxTemp: cfg.Glamox.HeatOnTemp}
			}
			return relayOutcome{UpdateGlamox: true, GlamoxTemp: cfg.Glamox.HeatOffTemp}
		}
		return relayOutcome{}
	}

	relayStatus, err := getRelayStatus(cfg)
	if err != nil {
		logger.Errorf("Error interacting with SR201: %v", err)
		return relayOutcome{}
	}

	if err := store.SetRelayState(heatOn); err != nil {
		logger.Errorf("Error saving relay state: %v", err)
	}

	return heatLogic(logger, cfg, heatOn, lastState, relayStatus)
}

func newSR201Client(cfg config.Config) sr201.Client {
	return sr201.Client{
		IP:      cfg.SR201.IP,
		Port:    cfg.SR201.Port,
		Relay:   cfg.SR201.Relay,
		Timeout: time.Duration(cfg.SR201.TimeoutSeconds) * time.Second,
	}
}

func getRelayStatus(cfg config.Config) (bool, error) {
	client := newSR201Client(cfg)
	return client.CheckStatus()
}

func heatLogic(logger *logging.Logger, cfg config.Config, heatOn bool, lastState bool, relayStatus bool) relayOutcome {
	if heatOn != lastState {
		logger.Infof("Change of state detected")
	}
	if heatOn {
		if !relayStatus {
			logger.Infof("Turning heat on.")
			if err := relayHeatOn(cfg); err != nil {
				logger.Errorf("Error turning heat on: %v", err)
				return relayOutcome{}
			}
			return relayOutcome{UpdateGlamox: true, GlamoxTemp: cfg.Glamox.HeatOnTemp}
		} else {
			logger.Infof("Relay is already on, not turning heat on.")
		}
		return relayOutcome{}
	}

	if relayStatus {
		logger.Infof("Turning heat off.")
		if err := relayHeatOff(cfg); err != nil {
			logger.Errorf("Error turning heat off: %v", err)
			return relayOutcome{}
		}
		return relayOutcome{UpdateGlamox: true, GlamoxTemp: cfg.Glamox.HeatOffTemp}
	} else {
		logger.Infof("Relay is already off, not turning heat off.")
	}
	return relayOutcome{}
}

func relayHeatOn(cfg config.Config) error {
	client := newSR201Client(cfg)
	pause := time.Duration(cfg.SR201.RelayPauseSeconds) * time.Second
	if err := client.CloseRelay(); err != nil {
		return err
	}
	time.Sleep(pause)
	if err := client.OpenRelay(); err != nil {
		return err
	}
	time.Sleep(pause)
	return client.CloseRelay()
}

func relayHeatOff(cfg config.Config) error {
	client := newSR201Client(cfg)
	pause := time.Duration(cfg.SR201.RelayPauseSeconds) * time.Second
	if err := client.CloseRelay(); err != nil {
		return err
	}
	time.Sleep(pause)
	if err := client.OpenRelay(); err != nil {
		return err
	}
	time.Sleep(pause)
	if err := client.CloseRelay(); err != nil {
		return err
	}
	time.Sleep(pause)
	return client.OpenRelay()
}

func updateStorsalenGlamox(logger *logging.Logger, client *glamox.Client, temp float64) {
	if client == nil {
		logger.Infof("Glamox disabled; skipping update.")
		return
	}
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

func heatZoneTransitionTarget(
	logger *logging.Logger,
	store *state.Store,
	zone string,
	heatOn bool,
	heatOnTemp float64,
	heatOffTemp float64,
) (float64, bool) {
	lastState, err := store.GetHeatZoneState(zone)
	if err != nil {
		logger.Errorf("Error reading %s heat state: %v", zone, err)
		lastState = false
	}
	if err := store.SetHeatZoneState(zone, heatOn); err != nil {
		logger.Errorf("Error saving %s heat state: %v", zone, err)
	}

	if heatOn == lastState {
		logger.Infof("%s heat state unchanged (%v); skipping temperature update.", zone, heatOn)
		return 0, false
	}

	logger.Infof("%s heat state changed: %v -> %v", zone, lastState, heatOn)
	if heatOn {
		return heatOnTemp, true
	}
	return heatOffTemp, true
}

func checkUpdatePray(logger *logging.Logger, store *state.Store, controller *mill.Controller, cfg config.Config, heatOn bool) {
	if controller == nil {
		logger.Infof("Mill disabled; skipping PRAY update.")
		return
	}

	target, shouldUpdate := heatZoneTransitionTarget(logger, store, "pray", heatOn, cfg.Mill.HeatOnTemp, cfg.Mill.HeatOffTemp)
	if !shouldUpdate {
		return
	}

	logger.Infof("Set PRAY heat to %.0fC.", target)
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
