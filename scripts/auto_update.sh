#!/usr/bin/env bash
# Poller GitHub Releases og installer nyeste versjon automatisk.
# Designet for å kjøre som en systemd-timer på Raspberry Pi bak privat VPN.
#
# Oppsett:
#   sudo mkdir -p /usr/local/lib/bedehus
#   sudo cp scripts/auto_update.sh /usr/local/lib/bedehus/auto_update.sh
#   sudo chmod +x /usr/local/lib/bedehus/auto_update.sh
#
# For private repo – lagre GitHub personal access token (read:contents scope):
#   sudo mkdir -p /etc/bedehus
#   echo "ghp_xxxx..." | sudo tee /etc/bedehus/github_token
#   sudo chmod 600 /etc/bedehus/github_token

set -euo pipefail

# --- Konfigurasjon (kan overrides med miljøvariabler) ---
REPO="${BEDEHUS_REPO:-FarrisSR/Bedehus}"
INSTALL_DIR="${BEDEHUS_INSTALL_DIR:-/home/runo/bedehus}"
VERSION_FILE="${BEDEHUS_VERSION_FILE:-/var/lib/bedehus/installed_version}"
TOKEN_FILE="${BEDEHUS_TOKEN_FILE:-/etc/bedehus/github_token}"
# Romskilt liste over systemd-tjenester som restartes etter oppdatering
SERVICES="${BEDEHUS_SERVICES:-bedehus}"

# Asset i GitHub Release → filnavn på Pi  (format: "asset-navn:installert-navn")
ASSETS=(
    "bedehus-linux-armv6:bedehus"
    "bedehus-on-linux-armv6:bedehus-on"
    "bedehus-off-linux-armv6:bedehus-off"
    "bedehus-rs-linux-armv6:bedehus-rs"
)

# --- Hjelpefunksjoner ---
log() {
    local level="$1"; shift
    printf '%s bedehus-updater %-5s %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$level" "$*"
}

GITHUB_TOKEN=""
[[ -f "$TOKEN_FILE" ]] && GITHUB_TOKEN=$(cat "$TOKEN_FILE")

api_curl() {
    local args=(-sf --retry 3 --retry-delay 5)
    [[ -n "$GITHUB_TOKEN" ]] && args+=(-H "Authorization: Bearer $GITHUB_TOKEN")
    curl "${args[@]}" "$@"
}

# Ekstraher felt fra JSON via python3 (alltid tilgjengelig på Raspberry Pi OS)
json_get() {
    local expr="$1"; shift
    printf '%s' "$1" | python3 -c "import sys, json; d=json.load(sys.stdin); print($expr)"
}

asset_id_for() {
    local name="$1"
    printf '%s' "$release_json" | python3 -c "
import sys, json
name = sys.argv[1]
for a in json.load(sys.stdin).get('assets', []):
    if a['name'] == name:
        print(a['id'])
        break
" "$name"
}

download_asset() {
    local asset_id="$1" dest="$2"
    if [[ -n "$GITHUB_TOKEN" ]]; then
        # Private repo: bruk GitHub API med Accept: application/octet-stream
        curl -sfL --retry 3 --retry-delay 5 \
            -H "Authorization: Bearer $GITHUB_TOKEN" \
            -H "Accept: application/octet-stream" \
            "https://api.github.com/repos/$REPO/releases/assets/$asset_id" \
            -o "$dest"
    else
        # Public repo: følg browser_download_url direkte
        local url
        url=$(printf '%s' "$release_json" | python3 -c "
import sys, json
for a in json.load(sys.stdin).get('assets', []):
    if str(a['id']) == '$asset_id':
        print(a['browser_download_url']); break
")
        curl -sfL --retry 3 --retry-delay 5 "$url" -o "$dest"
    fi
}

# Verifiser nedlastet binary mot sha256-asset (om den finnes i releasen).
# Returnerer 1 dersom checksum-asset finnes men ikke stemmer, eller nedlasting feiler.
verify_checksum() {
    local asset_name="$1" file="$2"
    local checksum_asset_id
    checksum_asset_id=$(asset_id_for "${asset_name}.sha256")
    if [[ -z "$checksum_asset_id" ]]; then
        log "WARN" "Ingen .sha256 for $asset_name i denne releasen – hopper over verifisering"
        return 0
    fi

    local checksum_file
    checksum_file=$(mktemp /tmp/bedehus-checksum.XXXXXX)
    if ! download_asset "$checksum_asset_id" "$checksum_file"; then
        log "ERROR" "Klarte ikke laste ned sha256 for $asset_name"
        rm -f "$checksum_file"
        return 1
    fi

    local expected actual
    expected=$(awk '{print $1}' "$checksum_file")
    actual=$(sha256sum "$file" | awk '{print $1}')
    rm -f "$checksum_file"

    if [[ "$expected" != "$actual" ]]; then
        log "ERROR" "Checksum-mismatch for $asset_name: forventet $expected, fikk $actual"
        return 1
    fi
    return 0
}

# --- Sjekk siste release ---
log "INFO" "Sjekker GitHub Releases for $REPO..."
release_json=$(api_curl "https://api.github.com/repos/$REPO/releases/latest") || {
    log "ERROR" "Klarte ikke nå GitHub API – avslutter"
    exit 1
}

latest=$(json_get "d['tag_name']" "$release_json")
[[ -z "$latest" ]] && { log "ERROR" "Tom tag_name i API-svar"; exit 1; }

current=$(cat "$VERSION_FILE" 2>/dev/null || echo "none")

if [[ "$latest" == "$current" ]]; then
    log "INFO" "Allerede på $latest – ingen oppdatering nødvendig"
    exit 0
fi

log "INFO" "Ny versjon tilgjengelig: $current → $latest"

# --- Last ned og installer ---
mkdir -p "$INSTALL_DIR"
installed=0
failed=0

for mapping in "${ASSETS[@]}"; do
    asset_name="${mapping%%:*}"
    install_name="${mapping##*:}"
    install_path="$INSTALL_DIR/$install_name"

    asset_id=$(asset_id_for "$asset_name")
    if [[ -z "$asset_id" ]]; then
        log "INFO" "$asset_name ikke i release $latest – hopper over"
        continue
    fi

    tmpfile=$(mktemp /tmp/bedehus-update.XXXXXX)

    log "INFO" "Laster ned $asset_name..."
    if download_asset "$asset_id" "$tmpfile" && verify_checksum "$asset_name" "$tmpfile"; then
        chmod +x "$tmpfile"
        # Sikkerhetskopi av eksisterende binary
        [[ -f "$install_path" ]] && cp "$install_path" "${install_path}.prev"
        mv "$tmpfile" "$install_path"
        log "INFO" "Installerte $install_name → $install_path"
        installed=$((installed + 1))
    else
        rm -f "$tmpfile"
        log "ERROR" "Nedlasting/verifisering av $asset_name feilet – behold eksisterende binary"
        failed=$((failed + 1))
    fi
done

if [[ "$installed" -eq 0 ]]; then
    log "ERROR" "Ingen binærer ble installert fra $latest"
    exit 1
fi

# --- Lagre versjon og restart tjenester ---
mkdir -p "$(dirname "$VERSION_FILE")"
echo "$latest" > "$VERSION_FILE"

for svc in $SERVICES; do
    if systemctl is-active --quiet "$svc" 2>/dev/null; then
        systemctl restart "$svc"
        log "INFO" "Restartet $svc"
    else
        log "INFO" "$svc kjører ikke – ingen restart"
    fi
done

log "INFO" "Oppdatering fullført: $latest ($installed installert${failed:+, $failed feilet})"
