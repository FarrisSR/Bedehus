#!/usr/bin/env python3
import argparse
import datetime
import os
import signal
import sys
import threading
import traceback
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from main import (
    check_relay_state,
    check_update_pray,
    close_google_calendar_client,
    get_calendar_events_with_fallback,
    load_config,
    open_state_db,
    process_events,
    resolve_path,
    setup_google_calendar_client,
    setup_logging,
    timed_step,
    update_storsalen_glamox,
    validate_config,
)


def run_cycle(logger, conn, cfg: Dict[str, Any], service) -> None:
    timing: Dict[str, float] = {}

    current_time = datetime.datetime.now(datetime.UTC)
    end_time = current_time + datetime.timedelta(hours=cfg["time_window_hours"])

    with timed_step(logger, timing, "calendar_storsalen"):
        events = get_calendar_events_with_fallback(
            logger,
            conn,
            cfg,
            service,
            cfg["google"]["calendar_id"],
            current_time,
            end_time,
        )
    heat_on = process_events(logger, events)

    with timed_step(logger, timing, "sr201_logic"):
        glamox_update = check_relay_state(logger, conn, cfg, heat_on)

    with timed_step(logger, timing, "glamox_logic"):
        if glamox_update is not None:
            update_storsalen_glamox(logger, cfg, glamox_update)

    with timed_step(logger, timing, "calendar_pray"):
        pray_events = get_calendar_events_with_fallback(
            logger,
            conn,
            cfg,
            service,
            cfg["google"]["pray_id"],
            current_time,
            end_time,
        )
    pray_heat_on = process_events(logger, pray_events)

    with timed_step(logger, timing, "mill_logic"):
        check_update_pray(logger, cfg, pray_heat_on)

    pretty = ", ".join(f"{k}={v:.1f}ms" for k, v in sorted(timing.items(), key=lambda kv: kv[1], reverse=True))
    logger.info("Timing summary: %s", pretty)


def load_runtime(base_dir: Path, config_path: str) -> Tuple[Dict[str, Any], Any, Any]:
    cfg = load_config(base_dir, config_path)
    validate_config(cfg)

    state_path = resolve_path(base_dir, cfg["state_db"]["path"])
    state_path.parent.mkdir(parents=True, exist_ok=True)
    conn = open_state_db(state_path)
    service = setup_google_calendar_client(cfg, base_dir)
    return cfg, conn, service


def file_mtime(path: Path) -> Optional[float]:
    try:
        return path.stat().st_mtime
    except FileNotFoundError:
        return None


def _flatten_config(prefix: str, value: Any, out: Dict[str, Any]) -> None:
    if isinstance(value, dict):
        for key in sorted(value.keys()):
            next_prefix = f"{prefix}.{key}" if prefix else str(key)
            _flatten_config(next_prefix, value[key], out)
        return
    out[prefix] = value


def config_diff_summary(old_cfg: Dict[str, Any], new_cfg: Dict[str, Any], max_items: int = 20) -> str:
    old_flat: Dict[str, Any] = {}
    new_flat: Dict[str, Any] = {}
    _flatten_config("", old_cfg, old_flat)
    _flatten_config("", new_cfg, new_flat)

    keys = sorted(set(old_flat.keys()) | set(new_flat.keys()))
    changes: List[str] = []
    for key in keys:
        old_val = old_flat.get(key, "<missing>")
        new_val = new_flat.get(key, "<missing>")
        if old_val != new_val:
            changes.append(f"{key}: {old_val!r} -> {new_val!r}")

    if not changes:
        return "no config value changes"
    if len(changes) > max_items:
        shown = ", ".join(changes[:max_items])
        return f"{shown} (+{len(changes) - max_items} more)"
    return ", ".join(changes)


def main() -> None:
    parser = argparse.ArgumentParser(description="Bedehus heating controller (systemd daemon)")
    parser.add_argument("--config", default="config/config.json", help="Path to config file")
    parser.add_argument("--interval-seconds", type=int, default=None, help="Override poll interval")
    parser.add_argument("--run-once", action="store_true", help="Run one cycle and exit")
    args = parser.parse_args()

    base_dir = Path(__file__).resolve().parent
    os.chdir(base_dir)

    config_path = resolve_path(base_dir, args.config)

    try:
        cfg = load_config(base_dir, str(config_path))
        validate_config(cfg)
    except Exception as e:
        print(f"Error loading config: {e}", file=sys.stderr)
        raise SystemExit(1) from e

    logger = setup_logging(base_dir, cfg)

    cfg_interval = int(cfg.get("systemd", {}).get("interval_seconds", 300))
    interval_seconds = args.interval_seconds if args.interval_seconds is not None else cfg_interval
    if interval_seconds <= 0:
        interval_seconds = 300

    stop_event = threading.Event()
    reload_event = threading.Event()

    def _handle_shutdown(signum, _frame):
        logger.info("Received signal %s, shutting down...", signum)
        stop_event.set()

    def _handle_reload(signum, _frame):
        logger.info("Received signal %s, scheduling config reload...", signum)
        reload_event.set()

    signal.signal(signal.SIGTERM, _handle_shutdown)
    signal.signal(signal.SIGINT, _handle_shutdown)
    if hasattr(signal, "SIGHUP"):
        signal.signal(signal.SIGHUP, _handle_reload)

    conn = None
    service = None
    config_mtime = file_mtime(config_path)

    try:
        cfg, conn, service = load_runtime(base_dir, str(config_path))

        logger.info("systemd_main started (interval=%ss, run_once=%s)", interval_seconds, args.run_once)

        if args.run_once:
            run_cycle(logger, conn, cfg, service)
            return

        while not stop_event.is_set():
            current_mtime = file_mtime(config_path)
            config_file_changed = current_mtime is not None and config_mtime is not None and current_mtime != config_mtime
            if reload_event.is_set() or config_file_changed:
                reason = "SIGHUP" if reload_event.is_set() else "config file changed"
                logger.info("Reloading runtime config (%s)...", reason)
                try:
                    new_cfg, new_conn, new_service = load_runtime(base_dir, str(config_path))
                    old_conn = conn
                    old_service = service
                    diff_summary = config_diff_summary(cfg, new_cfg)
                    cfg, conn, service = new_cfg, new_conn, new_service
                    if args.interval_seconds is None:
                        new_interval = int(cfg.get("systemd", {}).get("interval_seconds", 300))
                        if new_interval <= 0:
                            new_interval = 300
                        if new_interval != interval_seconds:
                            logger.info("Updating interval from %ss to %ss from config", interval_seconds, new_interval)
                            interval_seconds = new_interval
                    config_mtime = file_mtime(config_path)
                    reload_event.clear()
                    if old_conn is not None:
                        old_conn.close()
                    if old_service is not None:
                        close_google_calendar_client(old_service)
                    logger.info("Config changes: %s", diff_summary)
                    logger.info("Runtime config reload completed")
                except Exception as exc:
                    logger.error("Config reload failed; keeping current runtime: %s", exc)
                    logger.debug("%s", traceback.format_exc())
                    reload_event.clear()

            try:
                run_cycle(logger, conn, cfg, service)
            except Exception as exc:
                logger.error("Error in cycle: %s", exc)
                logger.debug("%s", traceback.format_exc())

            if stop_event.wait(interval_seconds):
                break

    except Exception as e:
        logger.error("Fatal error in systemd_main: %s", e)
        raise SystemExit(1) from e
    finally:
        if service is not None:
            close_google_calendar_client(service)
        if conn is not None:
            conn.close()
        logger.info("systemd_main stopped")


if __name__ == "__main__":
    main()
