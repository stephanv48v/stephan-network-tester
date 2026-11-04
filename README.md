# Stephan Van Vuuren's Network Tester

![Appliance Badge](https://img.shields.io/badge/Appliance-Dell_PowerEdge_R640-00E5FF?style=for-the-badge)
![Engine](https://img.shields.io/badge/Engine-Cisco_TRex_v3.05+%20%7C%20DPDK-10B981?style=for-the-badge)
![Stack](https://img.shields.io/badge/Backend-FastAPI_%2B_WebSockets_%2B_SQLite-6366F1?style=for-the-badge)

A turnkey, bare-metal network strain testing, traffic simulation, and site certification appliance built for **Dell PowerEdge R640** (`Ubuntu Server LTS`) with **1x 10GbE (`enp216s0` Aquantia AQC113)** and **4x 1GbE (`eno1`–`eno4` Intel I350)** interfaces.

---

## Key Capabilities

1. **Cisco TRex (`v3.04+`) & Hybrid Live-Network Traffic Engine**
   - Native integration with Cisco TRex (`trex_stl_lib.api`) over ZMQ RPC (`localhost:4501`) with automatic HugePages (`1GB`/`2MB`) and DPDK configuration.
   - Automatic `/etc/trex_cfg.yaml` hardware discovery supporting **Stateless (`--stl`)**, **Advanced Stateful (`--astf`)**, **Virtual Loopback Simulation (`veth_trex0` ↔ `veth_trex1`)**, and **Live Physical NIC Strain Testing**.
   - **Management NIC Lockout Shield**: Automatically detects the active DHCP/Web UI interface and prevents DPDK from unbinding the management link when moving between sites.

2. **Interactive Users, Devices & Traffic Mix Simulator**
   - Simulate **1 to 50,000+ Virtual Users** and **1 to 65,000+ Virtual Devices** (unique MAC pools, subnet IP ranges, VLANs, and multi-flow sessions).
   - Mix realistic traffic profiles with visual percentage sliders:
     - **Web & Cloud SaaS** (`HTTP/HTTPS`, bursty TCP flows)
     - **4K Video & CCTV Surveillance** (`UDP/RTP` high-bandwidth streams, `DSCP AF41`)
     - **VoIP & Unified Communications** (`SIP/RTP G.711`, `64B–200B`, `DSCP EF 46` with live **ITU-T G.107 MOS Score `1.0–4.5`**)
     - **Enterprise File Backup / SMB** (`1518B` & `9000B Jumbo` elephant flows)
     - **Gaming & Low-Latency UDP** (high tick-rate jitter spike detection)
     - **Control-Plane Stress** (`DNS` query floods / `ARP` & `DHCP` broadcast discovery)
     - **RFC 2544 / Torture Benchmarks** (`64B Max PPS`, `IMIX`, `1518B Line Rate`, `9000B Jumbo`, `UDP Microburst`)

3. **Test Execution Modes & Scheduler**
   - **Continuous Mode** with live `1%–100%` line-rate throttle slider.
   - **Timed Duration Mode** (`10s` to `24h`).
   - **Step-Ramp Saturation Finder** (automatically increments load every $N$ seconds to pinpoint the exact link saturation & drop threshold).
   - **RFC 2544 / Y.1564 1-Click Site Certification Wizard** (automated multi-frame-size sweep `64B` → `1518B` with Pass/Fail SLA grading).
   - **Scheduled Cron Tests** (schedule overnight or recurring site stress tests stored in SQLite).

4. **250ms Real-Time WebSocket Telemetry (`/ws/telemetry`)**
   - Live streaming of `TX bps`, `RX bps`, `TX pps`, `RX pps`, packet drops, drop percentage, latency (`min`/`avg`/`max`/`jitter` in $\mu\text{s}$), estimated **VoIP MOS**, and **Dell R640 32-Core Xeon CPU / 500GB RAM / HugePages / per-NIC counters**.

5. **Portable Field Site Diagnostics Suite**
   - **Multi-Port Portable DHCP (`Netplan`) & mDNS (`http://stephan-tester.local`)**: Plug any of the 5 NICs into a customer switch on DHCP and access the cockpit immediately on Port `80` with zero authentication.
   - **Dell R640 Front LCD Bezel IP Display (`ipmitool`)**: Automatically displays the live DHCP IP on the physical server front LCD screen.
   - **LLDP / CDP Switch Neighbor Discovery**: Shows the connected switch name, port description, and VLAN ID.
   - **Built-in iPerf3 Server & Client**, **Path-MTU Finder**, **Subnet Ping/ARP Sweeper**, **DNS/DHCP Responder Benchmark**, and **1-Click `.pcap` Packet Capture**.

6. **Executive PDF Reports & CSV Time-Series Export**
   - 1-click download of `.csv` second-by-second telemetry or a styled **Stephan Van Vuuren's Network Tester PDF Report** with Pass/Fail SLA badges, summary tables, and embedded throughput/latency charts.

---

## Architecture & Directory Layout

```
/opt/stephan-network-tester
├── backend/
│   ├── main.py             # FastAPI application, WebSocket streamer (250ms), & scheduler
│   ├── trex_manager.py     # Cisco TRex STL client + Live Multi-Core Traffic & Strain Engine
│   ├── profiles.py         # Traffic profiles, Users/Devices synthesizer, & packet builder
│   ├── diagnostics.py      # LLDP, iPerf3, MTU, DNS/DHCP benchmark, PCAP capture
│   ├── database.py         # SQLite persistence for runs, 1s samples, & cron schedules
│   └── exporter.py         # CSV & Branded PDF Report generator
├── frontend/
│   └── index.html          # Responsive Dark-Mode Cockpit (React + Tailwind + ECharts + SVG)
├── scripts/
│   ├── discover_hardware.py       # NIC/PCIe discovery & /etc/trex_cfg.yaml generator
│   ├── start_trex.sh              # TRex daemon launcher with veth loopback safety
│   └── update_lcd_and_banner.sh   # Dell R640 Front LCD & console IP updater
└── systemd/
    ├── trex-server.service        # Cisco TRex ZMQ RPC server daemon
    ├── trex-engine.service        # Alias/companion unit for TRex engine
    └── stephan-tester-web.service # FastAPI Web UI & Telemetry Engine on 0.0.0.0:80
```

## Quick Commands

```bash
# Hardware Discovery & regenerate /etc/trex_cfg.yaml
sudo /opt/stephan-network-tester/venv/bin/python /opt/stephan-network-tester/scripts/discover_hardware.py --write-config

# Check Services
sudo systemctl status trex-server.service
sudo systemctl status stephan-tester-web.service
```
