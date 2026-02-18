package main

import (
	"flag"
	"fmt"
	"os"
	"path/filepath"
	"time"

	"go-bedehus/internal/config"
	"go-bedehus/internal/sr201"
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
		if cwd, cwdErr := os.Getwd(); cwdErr == nil {
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
	if cfg.SR201.IP == "" {
		return fmt.Errorf("invalid config: sr201.ip is required")
	}
	if !cfg.SR201.Enabled {
		return fmt.Errorf("invalid config: sr201.enabled is false")
	}
	if cfg.SR201.Relay < 1 || cfg.SR201.Relay > 8 {
		return fmt.Errorf("invalid config: sr201.relay must be 1-8, got %d", cfg.SR201.Relay)
	}

	client := sr201.Client{
		IP:      cfg.SR201.IP,
		Port:    cfg.SR201.Port,
		Relay:   cfg.SR201.Relay,
		Timeout: time.Duration(cfg.SR201.TimeoutSeconds) * time.Second,
	}
	if err := client.OpenRelay(); err != nil {
		return fmt.Errorf("failed to open relay %d: %w", cfg.SR201.Relay, err)
	}

	fmt.Printf("relay %d opened on %s\n", cfg.SR201.Relay, cfg.SR201.IP)
	return nil
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
