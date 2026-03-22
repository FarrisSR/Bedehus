#!/usr/bin/env python3
"""Scanner lokalnettet med arp-scan og sender JSON-lines til syslog/stdout."""

import argparse
import datetime as dt
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from common.logging_utils import resolve_path, setup_logging

DEFAULT_CONFIG: Dict[str, Any] = {
    "logging": {
        "python_config_file": "logging_arp.config",
    },
    "arp": {
        "interface": "wlan0",
        "alias_file": "scripts/arp_alias",
        "alias_prefix": "glamox_ovn_",
        "command": ["sudo", "arp-scan", "-I", "{interface}", "--localnet"],
        "emit_summary": True,
    },
}


def merge_dict(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = merge_dict(out[key], value)
        else:
            out[key] = value
    return out


def load_config(base_dir: Path, config_path: Optional[str]) -> Dict[str, Any]:
    cfg = dict(DEFAULT_CONFIG)
    if not config_path:
        return cfg
    resolved = resolve_path(base_dir, config_path)
    with resolved.open("r", encoding="utf-8") as fh:
        loaded = json.load(fh)
    cfg = merge_dict(DEFAULT_CONFIG, loaded)
    if not cfg.get("logging", {}).get("python_config_file"):
        cfg.setdefault("logging", {})["python_config_file"] = "logging_arp.config"
    return cfg


def load_aliases(alias_file: Path, alias_prefix: str) -> Dict[str, str]:
    aliases: Dict[str, str] = {}
    with alias_file.open("r", encoding="utf-8") as fh:
        for raw_line in fh:
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            if len(parts) < 2:
                continue
            mac, alias = parts[0].lower(), parts[1]
            if alias.startswith(alias_prefix):
                aliases[mac] = alias
    return aliases


def parse_arp_scan(output: str, alias_map: Dict[str, str]) -> Dict[str, Dict[str, Optional[str]]]:
    seen: Dict[str, Dict[str, Optional[str]]] = {}
    for line in output.splitlines():
        parts = line.split("\t")
        if len(parts) < 2:
            parts = line.split()
        if len(parts) < 2:
            continue
        ip = parts[0].strip()
        mac = parts[1].strip().lower()
        if mac not in alias_map:
            continue
        vendor = parts[2].strip() if len(parts) > 2 else None
        seen[mac] = {"ip": ip, "vendor": vendor}
    return seen


def run_arp_scan(interface: str, command: List[str]) -> Tuple[str, float]:
    cmd = [part.replace("{interface}", interface) for part in command]
    if "-I" not in cmd and "--interface" not in cmd:
        cmd.extend(["-I", interface])
    start = dt.datetime.now(dt.timezone.utc)
    proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
    elapsed_ms = (dt.datetime.now(dt.timezone.utc) - start).total_seconds() * 1000.0
    return proc.stdout, elapsed_ms


def build_payloads(
    alias_map: Dict[str, str],
    seen: Dict[str, Dict[str, Optional[str]]],
    iface: str,
    scanner: str,
    emit_summary: bool,
) -> Iterable[Dict[str, Any]]:
    ts = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    for mac, alias in sorted(alias_map.items(), key=lambda item: item[1]):
        observed = seen.get(mac)
        yield {
            "ts": ts,
            "site": "bedehus",
            "scanner": scanner,
            "type": "arp_presence",
            "iface": iface,
            "alias": alias,
            "mac": mac,
            "ip": observed.get("ip") if observed else None,
            "vendor": observed.get("vendor") if observed else None,
            "online": observed is not None,
        }
    if emit_summary:
        yield {
            "ts": ts,
            "site": "bedehus",
            "scanner": scanner,
            "type": "arp_scan_summary",
            "iface": iface,
            "expected": len(alias_map),
            "seen": len(seen),
            "success": True,
        }


def main() -> int:
    parser = argparse.ArgumentParser(description="Logg ARP presence for utvalgte alias til syslog/stdout som JSON-lines.")
    parser.add_argument("--config", default="config/config.json", help="JSON-konfig, default config/config.json")
    parser.add_argument("--iface", help="Overstyr interface")
    parser.add_argument("--alias-file", help="Overstyr alias-fil")
    parser.add_argument("--alias-prefix", help="Overstyr alias-prefiks")
    parser.add_argument("--stdout", action="store_true", help="Skriv JSON-lines til stdout i tillegg til logging")
    args = parser.parse_args()

    cfg = load_config(ROOT, args.config)
    arp_cfg = cfg.get("arp", {})
    iface = args.iface or arp_cfg.get("interface", "wlan0")
    alias_prefix = args.alias_prefix or arp_cfg.get("alias_prefix", "glamox_ovn_")
    alias_file = resolve_path(ROOT, args.alias_file or arp_cfg.get("alias_file", "scripts/arp_alias"))
    command = list(arp_cfg.get("command", ["sudo", "arp-scan", "-I", "{interface}", "--localnet"]))
    emit_summary = bool(arp_cfg.get("emit_summary", True))

    logger = setup_logging("bedehus-arp", ROOT, cfg, default_config_file="logging_arp.config")

    alias_map = load_aliases(alias_file, alias_prefix)
    if not alias_map:
        logger.warning(json.dumps({
            "type": "arp_scan_summary",
            "success": False,
            "reason": "no_aliases_loaded",
            "iface": iface,
            "alias_file": str(alias_file),
            "alias_prefix": alias_prefix,
        }, separators=(",", ":")))
        return 1

    try:
        output, elapsed_ms = run_arp_scan(iface, command)
    except subprocess.CalledProcessError as exc:
        logger.error(json.dumps({
            "ts": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            "site": "bedehus",
            "scanner": "pi1",
            "type": "arp_scan_summary",
            "iface": iface,
            "success": False,
            "returncode": exc.returncode,
            "stderr": (exc.stderr or "").strip(),
        }, separators=(",", ":")))
        return exc.returncode or 1

    seen = parse_arp_scan(output, alias_map)
    payloads = list(build_payloads(alias_map, seen, iface, scanner="pi1", emit_summary=emit_summary))
    if emit_summary and payloads:
        payloads[-1]["duration_ms"] = round(elapsed_ms, 1)

    for payload in payloads:
        line = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
        logger.info(line)
        if args.stdout:
            print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
