#!/usr/bin/env bash
# One-Line Turnkey Bootstrap & Auto-Deploy Installer for Stephan Van Vuuren's Network Tester
set -e

echo "========================================================================"
echo "  STEPHAN VAN VUUREN'S NETWORK TESTER - FINAL BOOTSTRAP & AUTO-DEPLOY"
echo "========================================================================"

mkdir -p /opt/stephan-network-tester/data
cd /opt/stephan-network-tester

if [ ! -d .git ]; then
    git init -b main
fi
git remote remove origin 2>/dev/null || true
git remote add origin https://github.com/stephanv48v/stephan-network-tester.git
git fetch origin main
git reset --hard origin/main

sed -i 's/\r$//' /opt/stephan-network-tester/scripts/*.sh /opt/stephan-network-tester/scripts/*.py /opt/stephan-network-tester/systemd/*.service
chmod +x /opt/stephan-network-tester/scripts/*.sh /opt/stephan-network-tester/scripts/*.py

echo "[1/4] Generating /etc/trex_cfg.yaml & Virtual Loopback Pair..."
/opt/stephan-network-tester/venv/bin/python /opt/stephan-network-tester/scripts/discover_hardware.py --write-config >/dev/null
/opt/stephan-network-tester/scripts/update_lcd_and_banner.sh || true

echo "[2/4] Installing systemd services (trex-server, trex-engine, stephan-tester-web, stephan-auto-deploy)..."
systemctl stop nginx apache2 2>/dev/null || true
systemctl disable nginx apache2 2>/dev/null || true
cp /opt/stephan-network-tester/systemd/trex-server.service /etc/systemd/system/trex-server.service
rm -f /etc/systemd/system/trex-engine.service
cp /opt/stephan-network-tester/systemd/stephan-tester-web.service /etc/systemd/system/stephan-tester-web.service
cp /opt/stephan-network-tester/systemd/stephan-auto-deploy.service /etc/systemd/system/stephan-auto-deploy.service
systemctl daemon-reload

echo "[3/4] Enabling & starting services on boot..."
systemctl enable --now trex-server.service
systemctl enable --now stephan-tester-web.service
systemctl enable --now stephan-auto-deploy.service

sleep 2
echo "[4/4] Verifying Port 80 Web GUI & Auto-Deploy Daemon..."
systemctl is-active trex-server.service stephan-tester-web.service stephan-auto-deploy.service

PRIMARY_IP=$(hostname -I | awk '{print $1}')
echo "========================================================================"
echo "  LIVE NOW! Open your browser to:  http://${PRIMARY_IP}"
echo "  Auto-Deploy Daemon is ACTIVE (auto-pulls origin/main every 15s)"
echo "========================================================================"
