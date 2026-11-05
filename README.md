# Cisco TRex Network Test Studio (`stephan-network-tester` v4.0)

![Appliance Badge](https://img.shields.io/badge/Appliance-Dell_PowerEdge_R640-1769D2?style=for-the-badge)
![Engine](https://img.shields.io/badge/Engine-Cisco_TRex_v3.04_ASTF_%2B_STL-15803D?style=for-the-badge)
![Stack](https://img.shields.io/badge/Stack-FastAPI_%2B_UniFi_API_%2B_SNMP_%2B_SQLite-142338?style=for-the-badge)

Enterprise-grade network performance testing, **10,000-user stateful workload simulation**, **UniFi Enterprise Fortress Gateway (EFG) stack monitoring**, and **multi-page client-ready reporting** deployed on **Dell PowerEdge R640** (`Ubuntu Server LTS`).

---

## Core Capabilities

### 1. Realistic 10,000-User Enterprise Traffic Engine (`ASTF` + `STL` + `Internet/WAN`)
- **Cisco TRex Advanced Stateful (`--astf`)**: Simulates `500` to `10,000` concurrent enterprise users across unique sequential client IPs (`16.0.0.1`–`16.0.39.16`) establishing genuine multi-template TCP 3-way handshakes (`SYN`/`SYN-ACK`/`ACK`), HTTP/HTTPS request/response loops, sustained streaming transfers, keep-alives, teardowns, and interleaved UDP/RTP/DNS flows (`48.0.0.1`+ emulated WAN servers).
- **Independent User Scale & Target Throughput**: Configure simulated user count (`500`, `1,000`, `2,500`, `5,000`, `7,500`, `10,000`) independently from target bandwidth (`Mbps` / `Gbps`).
- **Strict Metric Separation**: Reports **Simulated Users**, **Emulated Client IPs**, **Active Stateful Flows**, **Established TCP Sessions**, and **Connections/sec (CPS)** separately — never conflated.
- **12 Synthetic Enterprise Workload Categories**:
  - Video Streaming (`YouTube` / `4K` / Adaptive Bitrate)
  - Microsoft 365 & SaaS Productivity (`HTTPS` bursty transactions)
  - Teams Voice & Video (`UDP/RTP` real-time media)
  - Social Media Browsing & Media Feeds (`Facebook` / `Instagram`-like object bursts)
  - Messaging (`WhatsApp`-like persistent keep-alives & media bursts)
  - Web Browsing (`HTTP/HTTPS` page loads)
  - File Downloads & Uploads (`SMB` / Cloud Storage bulk TCP)
  - DNS Lookups (`UDP/53` query/response pairs)
  - Gaming & Low-Latency Interactive `UDP`
  - VoIP (`SIP/RTP G.711`, `DSCP EF` with live **ITU-T G.107 MOS**)
  - Background Sync & Cloud Backups
  - Custom Packet / Flow Templates
  *(All synthetic application workloads are clearly labeled as traffic-pattern approximations rather than proprietary encrypted SaaS logins.)*
- **Cisco TRex Stateless (`--stl`)**: Wire-speed frame sweeps (`64B`, `128B`, `256B`, `512B`, `1024B`, `1518B`, `9000B`) and automated **RFC 2544** throughput/latency/loss benchmarking with dynamic `--astf` ↔ `--stl` daemon switching.
- **Live Internet / WAN Engine (`internet_wan`)**: Multi-worker real HTTP/HTTPS downloads/uploads, DNS resolution, and gateway RTT/jitter probes through the live management/WAN route against operator-authorized endpoints.

### 2. UniFi Stack & Read-Only SNMP Telemetry Correlation
- **Official Local UniFi Network Integration API (`X-API-KEY`)** & **UniFi OS Controller Session API** + optional **UniFi Site Manager API (`api.ui.com`)**:
  - Live monitoring of **UniFi Enterprise Fortress Gateway (EFG)**, switches, access points, WAN health/ISP latency, port utilization, CPU/memory, and active clients.
  - Synchronized second-by-second **TRex Load vs. UniFi EFG CPU / Memory / Throughput** correlation timelines.
- **Read-Only SNMPv2c / SNMPv3 (`IF-MIB`) Collector**:
  - Polls 64-bit `ifHCInOctets` / `ifHCOutOctets`, `ifHCInUcastPkts` / `ifHCOutUcastPkts`, `ifInErrors` / `ifOutErrors`, `ifInDiscards` / `ifOutDiscards`, and operational link state with 64-bit wraparound protection.
- **Server-Side Fernet Credential Vault**: API keys, controller passwords, and SNMP secrets are encrypted at rest (`/opt/stephan-network-tester/data/.secret.key`) and never returned to browsers or exports. Unavailable metrics explicitly report `"Unavailable"`.

### 3. Dell R640 Hardware & UniFi EFG LAN-to-WAN Topology Assessment
- **Management NIC Lockout Shield**: Protects `enp216s0` (`10.20.30.237/24`) from DPDK unbinding at all times.
- **Transparent Hardware Capability Reporting**:
  - `eno1`–`eno4` (`4× 1GbE Intel I350`): Cable `eno1` → EFG LAN and `eno2` → Controlled EFG WAN Lab VLAN to validate **10,000 stateful users through the EFG firewall/NAT engine up to `1.0 Gbps`**.
  - `veth_trex0` ↔ `veth_trex1`: Internal TRex self-test loopback when physical test ports are unpatched.
  - Full **`10 Gbps` LAN-to-WAN hairpin** across the EFG requires adding a dual-port `10GbE SFP+` NIC (`Intel X710` / `Mellanox ConnectX-5`) or an external `10GbE` WAN responder.

### 4. Simple 6-Section UI
The sidebar has six sections; each one shows its pages as tabs across the top.
- **Home**: status banner, 4 key numbers, live throughput chart, one-click tests (engine self-test, firewall load test with any user count up to 100,000, internet speed & quality, frame-size benchmark), recent results, UniFi and server health
- **Run a Test**: Custom Test (with pre-flight check), App Simulation, Traffic Mix, Stress & Soak (custom user-scale test up to 100,000 users), Benchmark (RFC 2544-style), Saved Profiles, Schedule
- **Live View**: throughput, latency, connections, errors and gateway load for the running test
- **Results & Reports**: History, Compare, Reports (PDF / CSV / JSON)
- **My Network**: UniFi, Topology, Ports
- **System & Settings**: Server Health, TRex Engine, Integrations, Settings, Users, Audit Log

User counts are free-entry from 1 to **100,000** (one emulated client IP per user, `16.0.0.1`–`16.1.134.160` at the maximum).

### 5. Client-Ready Multi-Page Light-Mode Reports (`PDF` / `CSV` / `JSON`)
- **9-Page Full Technical PDF Report**, **3-Page Executive Summary PDF**, and **Side-by-Side Comparison PDF** featuring light-mode charts, traffic mix breakdowns, latency percentile tables (`Avg` / `P95` / `P99` / `Max` / `Jitter`), UniFi EFG correlation, and explicit threshold evaluation (**Pass/Fail** is evaluated and displayed **only** when explicit SLA thresholds are enabled; otherwise runs conclude as **Completed**).

---

## Directory Layout

```
/opt/stephan-network-tester
├── backend/
│   ├── main.py               # FastAPI v4.0 REST API, 250ms WebSocket streamer, & scheduler
│   ├── trex_manager.py       # Dual-mode Cisco TRex ASTF + STL + Internet/WAN orchestrator
│   ├── astf_builder.py       # Multi-template 10,000-user Cisco TRex ASTF profile builder
│   ├── internet_generator.py # Multi-worker live WAN HTTP/HTTPS/DNS & RTT probe engine
│   ├── profiles.py           # 12 enterprise app workloads, EFG scenarios, & staged steps
│   ├── unifi_collector.py    # Local UniFi API, UniFi OS, & Site Manager read-only collector
│   ├── snmp_collector.py     # SNMPv2c/v3 64-bit IF-MIB interface counter collector
│   ├── diagnostics.py        # LLDP, iPerf3, MTU, DNS/DHCP benchmark, PCAP capture
│   ├── database.py           # SQLite persistence, Fernet secret vault, & run comparison
│   └── exporter.py           # 9-page Technical PDF, Executive PDF, Comparison PDF, CSV, JSON
├── frontend/
│   ├── index.html            # Enterprise Light-Mode App Shell & 20-route Sidebar
│   └── static/
│       ├── styles.css        # Cisco Enterprise Light-Mode Design System
│       ├── app.js            # Core state, WebSocket telemetry, Dashboard, Live Monitoring
│       ├── pages_studio.js   # Test Studio, Results, Comparison, & Reports views
│       └── pages_infra.js    # UniFi Stack, Topology, NICs, TRex Engine, Server Health, Admin
├── scripts/
│   ├── discover_hardware.py  # PCIe/NIC discovery, topology assessment & /etc/trex_cfg.yaml
│   ├── start_trex.sh         # TRex daemon launcher (--astf / --stl via /etc/default/trex-mode)
│   └── auto_deploy.sh        # GitHub origin/main auto-pull & service reloader
└── systemd/
    ├── trex-server.service        # Cisco TRex ZMQ RPC daemon
    ├── stephan-tester-web.service # FastAPI Web Studio on 0.0.0.0:80
    └── stephan-auto-deploy.timer  # Automated GitHub deployment timer
```

## Quick Operations

```bash
# Discover NICs, evaluate EFG topology & regenerate /etc/trex_cfg.yaml
sudo /opt/stephan-network-tester/venv/bin/python /opt/stephan-network-tester/scripts/discover_hardware.py --write-config

# Pull latest main & restart web service cleanly (preserving SQLite data)
sudo /opt/stephan-network-tester/scripts/auto_deploy.sh --once

# Check services
sudo systemctl status trex-server.service stephan-tester-web.service
```
