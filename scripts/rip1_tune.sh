#!/bin/bash

set -e

LOGFILE="$HOME/rpi1_tune.log"
exec > >(tee -a "$LOGFILE") 2>&1

echo "==== Raspberry Pi 1 Tuning Script ===="
echo "Logfile: $LOGFILE"
echo

# 1️⃣ Deaktiver unødvendige tjenester hvis de finnes
disable_service() {
    local svc="$1"
    if systemctl list-unit-files | grep -q "^$svc"; then
        echo "Disabling $svc..."
        sudo systemctl disable "$svc"
    else
        echo "Service $svc not installed — skipping."
    fi
}

echo "== Deaktiverer unødvendige tjenester =="
disable_service bluetooth.service
disable_service avahi-daemon.service
disable_service triggerhappy.service
disable_service ModemManager.service
disable_service hciuart.service

# 2️⃣ coherent_pool=1M i /boot/firmware/config.txt
echo
echo "== Setter coherent_pool=1M i /boot/firmware/config.txt hvis ikke satt =="
if grep -q "coherent_pool=1M" /boot/firmware/config.txt; then
    echo "coherent_pool=1M already present."
else
    echo "Adding coherent_pool=1M..."
    echo "coherent_pool=1M" | sudo tee -a /boot/firmware/config.txt
fi

# 3️⃣ Journal config
echo
echo "== Setter journal til 3 dager retention =="
sudo journalctl --vacuum-time=3d
sudo sed -i 's/^#*SystemMaxUse=.*/SystemMaxUse=50M/' /etc/systemd/journald.conf
sudo sed -i 's/^#*SystemMaxRetention=.*/SystemMaxRetention=3d/' /etc/systemd/journald.conf
sudo systemctl restart systemd-journald
echo "Journal config satt."

# 4️⃣ ZRAM installasjon og tuning
echo
echo "== Installerer zram-tools og tuner ZRAM =="
if ! dpkg -l | grep -q zram-tools; then
    echo "Installerer zram-tools..."
    sudo apt update
    sudo apt install -y zram-tools
else
    echo "zram-tools er allerede installert."
fi

if [ -f /etc/default/zramswap ]; then
    echo "Configuring ZRAM to 256 MB..."
    sudo sed -i 's/^#*ZRAM_SIZE=.*/ZRAM_SIZE=256/' /etc/default/zramswap
    sudo systemctl restart zramswap
    echo "ZRAM aktivert og satt til 256 MB."
else
    echo "Fant ikke /etc/default/zramswap etter installasjon — noe er galt."
fi

# 5️⃣ Ferdig!
echo
echo "==== Ferdig! ===="
echo "Anbefalt: reboot Pi for å bruke ny config."
echo "Log lagret i $LOGFILE"

