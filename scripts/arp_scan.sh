#!/usr/bin/env bash
set -euo pipefail

IFACE="${IFACE:-wlan0}"
ALIAS_FILE="${ALIAS_FILE:-./arp_alias}"

# Load aliases into an associative array: aliases["mac"]="alias"
declare -A aliases
if [[ -f "$ALIAS_FILE" ]]; then
  while read -r mac alias; do
    # Skip comments/blank lines
    [[ -z "${mac:-}" ]] && continue
    [[ "${mac:0:1}" == "#" ]] && continue

    # Normalize MAC to lowercase
    mac="$(echo "$mac" | tr '[:upper:]' '[:lower:]')"
    aliases["$mac"]="$alias"
  done <"$ALIAS_FILE"
fi

# Header (optional, comment out if you want pure data)
printf "%-17s %-15s %-30s %s\n" "MAC" "IP" "NAME" "ALIAS"

# arp-scan output lines start with an IPv4 address. Fields: IP MAC Vendor...
sudo arp-scan -I "$IFACE" --localnet 2>/dev/null |
  awk '/^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+[[:space:]]+/ {print $1, $2}' |
  while read -r ip mac; do
    mac_lc="$(echo "$mac" | tr '[:upper:]' '[:lower:]')"

    # NAME: use system resolver (mDNS/DNS/hosts). If not found, leave blank/NO_NAME.
    name="$(getent hosts "$ip" | awk '{print $2}' || true)"
    [[ -z "$name" ]] && name="NO_NAME"

    # ALIAS: from mapping file, else "-"
    alias="${aliases[$mac_lc]:-"-"}"

    printf "%-17s %-15s %-30s %s\n" "$mac_lc" "$ip" "$name" "$alias"
  done |
  sort -k4,4 -k1,1
