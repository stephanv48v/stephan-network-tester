#!/usr/bin/env bash
# Wrapper script for trex-server.service / trex-engine.service
set -e

# 1. Ensure HugePages are mounted and allocated
sysctl -w vm.nr_hugepages=4096 >/dev/null 2>&1 || true
mkdir -p /mnt/huge
mountpoint -q /mnt/huge || mount -t hugetlbfs nodev /mnt/huge 2>/dev/null || true

# 2. Ensure veth_trex0 <-> veth_trex1 loopback and /etc/trex_cfg.yaml exist
python3 /opt/stephan-network-tester/scripts/discover_hardware.py --write-config >/dev/null 2>&1 || true

# 3. Update Dell R640 Front LCD & login banner with current DHCP IP
/opt/stephan-network-tester/scripts/update_lcd_and_banner.sh >/dev/null 2>&1 || true

# 4. Launch Cisco TRex in Advanced Stateful (--astf) mode by default for 10,000-user EFG testing
#    (Can be switched dynamically to --stl via /etc/default/trex-mode for stateless RFC 2544 sweeps)
TREX_MODE="--astf"
if [ -f /etc/default/trex-mode ]; then
    source /etc/default/trex-mode
fi

cd /opt/trex
exec ./t-rex-64 -i ${TREX_MODE} --cfg /etc/trex_cfg.yaml --no-scapy-server
