"""
Enterprise Traffic Profiles, 12-Category Synthetic Application Workload Catalogue,
and Mix Normalization for Cisco TRex Network Test Studio.

NOTE ON METHODOLOGY:
Application category names describe synthetic workload characteristics (frame-size distribution,
inter-burst timing, L4 protocol mix, DSCP marking, and flow concurrency). They do NOT establish
authenticated commercial sessions (e.g., encrypted proprietary WhatsApp, Facebook, or Microsoft 365
logins) unless run in Live Internet HTTP/HTTPS mode against public endpoints.
"""
from typing import Any, Dict, List


APPLICATION_WORKLOADS: List[Dict[str, Any]] = [
    {
        "key": "video_streaming",
        "name": "YouTube / Netflix-style Video Streaming",
        "short_name": "Video Streaming",
        "classification": "Synthetic STL / Live CDN HTTPS",
        "protocol": "TCP/UDP (HTTPS + QUIC-like)",
        "ports": [443, 8080],
        "avg_frame_bytes": 1380,
        "burst_pattern": "Chunked adaptive bitrate bursts (1280-1460B)",
        "dscp": 34,
        "color": "#1769D2",
        "default_weight": 25,
        "disclaimer": "Approximates ABR chunked video delivery packet sizes and burst intervals; not DRM-authenticated playback.",
    },
    {
        "key": "m365_productivity",
        "name": "Microsoft 365-style Productivity",
        "short_name": "M365 Productivity",
        "classification": "Synthetic STL / HTTPS TLS",
        "protocol": "TCP",
        "ports": [443],
        "avg_frame_bytes": 640,
        "burst_pattern": "Interactive REST/API request-response bursts",
        "dscp": 18,
        "color": "#2585E6",
        "default_weight": 15,
        "disclaimer": "Models SaaS API/document sync packet distributions; not authenticated Entra ID / M365 tenant sessions.",
    },
    {
        "key": "teams_collab",
        "name": "Microsoft Teams-style Voice / Video",
        "short_name": "Teams Voice/Video",
        "classification": "Synthetic STL Realtime RTP-like",
        "protocol": "UDP",
        "ports": [3478, 3479, 3480],
        "avg_frame_bytes": 420,
        "burst_pattern": "Isochronous 20ms audio (160B) + 30fps video (980B)",
        "dscp": 46,
        "color": "#0EA5E9",
        "default_weight": 10,
        "disclaimer": "Models STUN/RTP media pacing and DSCP EF/AF41 markings; not encrypted Teams conferencing signaling.",
    },
    {
        "key": "social_browsing",
        "name": "Facebook / Instagram-style Browsing",
        "short_name": "Social Media-like",
        "classification": "Synthetic STL Media Feed",
        "protocol": "TCP/UDP",
        "ports": [443],
        "avg_frame_bytes": 890,
        "burst_pattern": "Scroll-triggered image/reel microbursts",
        "dscp": 0,
        "color": "#6366F1",
        "default_weight": 15,
        "disclaimer": "Approximates feed-scroll media fetch bursts; does not generate Meta Graph API or authenticated social traffic.",
    },
    {
        "key": "messaging_chat",
        "name": "WhatsApp-style Messaging",
        "short_name": "Messaging-like",
        "classification": "Synthetic STL Small-Packet Burst",
        "protocol": "TCP/UDP",
        "ports": [443, 5222],
        "avg_frame_bytes": 190,
        "burst_pattern": "High-concurrency keepalives + short media/text payloads",
        "dscp": 0,
        "color": "#14B8A6",
        "default_weight": 10,
        "disclaimer": "Approximates small-frame messaging keepalive and attachment bursts; not Signal/WhatsApp E2EE protocol.",
    },
    {
        "key": "cloud_files",
        "name": "OneDrive / SharePoint-style File Transfers",
        "short_name": "Cloud File Sync",
        "classification": "Synthetic STL Sustained TCP",
        "protocol": "TCP",
        "ports": [443],
        "avg_frame_bytes": 1420,
        "burst_pattern": "Parallel chunked TLS upload/download streams",
        "dscp": 10,
        "color": "#3B82F6",
        "default_weight": 5,
        "disclaimer": "Models large-object HTTPS sync flows; not authenticated SharePoint/OneDrive API calls.",
    },
    {
        "key": "web_browsing",
        "name": "Web Browsing (HTTP/HTTPS)",
        "short_name": "Web Browsing",
        "classification": "Synthetic STL / Live HTTP(S)",
        "protocol": "TCP",
        "ports": [80, 443],
        "avg_frame_bytes": 576,
        "burst_pattern": "Page-load multi-connection short flows",
        "dscp": 0,
        "color": "#10B981",
        "default_weight": 10,
        "disclaimer": "Standard web page-load packet size mix (SYN/ACK + 576B-1460B responses).",
    },
    {
        "key": "dns_queries",
        "name": "DNS Lookups",
        "short_name": "DNS",
        "classification": "Synthetic STL / Live UDP 53",
        "protocol": "UDP",
        "ports": [53],
        "avg_frame_bytes": 96,
        "burst_pattern": "High-rate small UDP query/response transactions",
        "dscp": 0,
        "color": "#F59E0B",
        "default_weight": 2,
        "disclaimer": "Standard RFC 1035 UDP DNS query framing.",
    },
    {
        "key": "voip_sip",
        "name": "VoIP (SIP + RTP G.711)",
        "short_name": "VoIP",
        "classification": "Synthetic STL Voice Bearer",
        "protocol": "UDP",
        "ports": [5060, 16384],
        "avg_frame_bytes": 160,
        "burst_pattern": "Constant bit-rate 50 pps per voice channel (DSCP EF)",
        "dscp": 46,
        "color": "#0D9488",
        "default_weight": 3,
        "disclaimer": "20ms G.711-sized UDP RTP bearer packets marked DSCP EF (46).",
    },
    {
        "key": "gaming_realtime",
        "name": "Online Gaming (Low-Latency UDP)",
        "short_name": "Gaming",
        "classification": "Synthetic STL Tick-Rate UDP",
        "protocol": "UDP",
        "ports": [27015, 3074],
        "avg_frame_bytes": 128,
        "burst_pattern": "64Hz-128Hz fixed-tick small UDP state updates",
        "dscp": 32,
        "color": "#8B5CF6",
        "default_weight": 2,
        "disclaimer": "Models 64-128 tick/sec small UDP datagrams sensitive to jitter.",
    },
    {
        "key": "backups_storage",
        "name": "Enterprise Backups & Replication",
        "short_name": "Backups",
        "classification": "Synthetic STL / Elephant Flows",
        "protocol": "TCP",
        "ports": [445, 2049, 3260],
        "avg_frame_bytes": 1518,
        "burst_pattern": "Sustained MTU-sized throughput streams",
        "dscp": 8,
        "color": "#64748B",
        "default_weight": 2,
        "disclaimer": "Sustained 1518B/Jumbo storage transfer pattern (CS1 Scavenger/Backup).",
    },
    {
        "key": "bulk_downloads",
        "name": "Bulk Downloads (CDN / OS Updates)",
        "short_name": "Bulk Downloads",
        "classification": "Synthetic STL / Live CDN HTTPS",
        "protocol": "TCP",
        "ports": [80, 443],
        "avg_frame_bytes": 1490,
        "burst_pattern": "Continuous full-window TCP/HTTPS payload transfer",
        "dscp": 0,
        "color": "#0284C7",
        "default_weight": 1,
        "disclaimer": "Full-MTU bulk payload transfer pattern; uses real CDN HTTPS objects in Internet/WAN mode.",
    },
]

WORKLOAD_MAP: Dict[str, Dict[str, Any]] = {w["key"]: w for w in APPLICATION_WORKLOADS}


def normalize_mix_to_100(raw_mix: Dict[str, Any]) -> Dict[str, float]:
    """Ensure workload weights are non-negative and sum strictly to 100.0%."""
    cleaned: Dict[str, float] = {}
    for k, v in (raw_mix or {}).items():
        try:
            val = max(0.0, float(v))
            if val > 0:
                cleaned[k] = val
        except Exception:
            pass
    total = sum(cleaned.values())
    if total <= 0:
        return {w["key"]: float(w["default_weight"]) for w in APPLICATION_WORKLOADS}
    scaled = {k: round((v / total) * 100.0, 2) for k, v in cleaned.items()}
    # Fix floating-point rounding drift on largest key so sum == 100.00
    diff = round(100.0 - sum(scaled.values()), 2)
    if diff != 0 and scaled:
        largest_key = max(scaled, key=lambda x: scaled[x])
        scaled[largest_key] = round(max(0.0, scaled[largest_key] + diff), 2)
    return scaled


PREBUILT_PROFILES: Dict[str, Dict[str, Any]] = {
    "imix": {
        "id": "imix",
        "name": "IMIX — Realistic Enterprise Mix (10K User Stateful ASTF)",
        "short_name": "IMIX — Realistic Enterprise",
        "category": "Enterprise Workload Mix",
        "traffic_engine": "trex_astf",
        "description": "Balanced enterprise stateful TCP/UDP workload across up to 10,000 emulated users combining video streaming (25%), M365/Teams-like collaboration (25%), social/messaging patterns (25%), web browsing (15%), and VoIP/DNS/gaming (10%).",
        "avg_frame_size": 594,
        "default_rate_pct": 100.0,
        "target_gbps": 10.0,
        "default_users": 10000,
        "default_devices": 15000,
        "tcp_pct": 80,
        "udp_pct": 20,
        "dscp": 0,
        "vlan_id": 0,
        "protocol_mix": {
            "video_streaming": 25.0,
            "m365_productivity": 15.0,
            "teams_collab": 10.0,
            "social_browsing": 15.0,
            "messaging_chat": 10.0,
            "web_browsing": 15.0,
            "voip_sip": 4.0,
            "dns_queries": 3.0,
            "gaming_realtime": 3.0,
        },
        "streams": [
            {"size": 64, "weight": 28, "proto": "UDP", "sport": 5060, "dport": 5060, "dscp": 46},
            {"size": 570, "weight": 42, "proto": "TCP", "sport": 443, "dport": 52400, "dscp": 0},
            {"size": 1420, "weight": 30, "proto": "UDP", "sport": 8554, "dport": 5004, "dscp": 34},
        ],
    },
    "internet_wan_mix": {
        "id": "internet_wan_mix",
        "name": "Live Internet & WAN Gateway Traffic (EFG -> WAN)",
        "short_name": "Internet / WAN Gateway",
        "category": "Live Internet / WAN",
        "traffic_engine": "internet_wan",
        "description": "Generates genuine outbound/inbound Internet traffic (HTTPS CDN downloads, TLS web sessions, DNS lookups, and WAN latency probes) routed through 10.20.30.1 (UniFi Gateway) to the Internet.",
        "avg_frame_size": 1380,
        "default_rate_pct": 50.0,
        "target_gbps": 0.1,
        "default_users": 250,
        "default_devices": 500,
        "tcp_pct": 90,
        "udp_pct": 10,
        "dscp": 0,
        "vlan_id": 0,
        "protocol_mix": {
            "bulk_downloads": 45.0,
            "video_streaming": 25.0,
            "web_browsing": 20.0,
            "dns_queries": 10.0,
        },
        "streams": [
            {"size": 1460, "weight": 90, "proto": "TCP", "sport": 443, "dport": 443, "dscp": 0},
            {"size": 96, "weight": 10, "proto": "UDP", "sport": 53000, "dport": 53, "dscp": 0},
        ],
    },
    "stress_64b": {
        "id": "stress_64b",
        "name": "64B Minimum-Frame Max PPS Benchmark",
        "short_name": "64B Max PPS Stress",
        "category": "PPS & ASIC Forwarding",
        "traffic_engine": "trex_stl",
        "description": "Minimum 64-byte Ethernet frames stressing packet-per-second forwarding engines, firewall state tables, and routing lookups.",
        "avg_frame_size": 64,
        "default_rate_pct": 50.0,
        "target_gbps": 5.0,
        "default_users": 5000,
        "default_devices": 10000,
        "tcp_pct": 0,
        "udp_pct": 100,
        "dscp": 0,
        "vlan_id": 0,
        "protocol_mix": {
            "dns_queries": 40.0,
            "voip_sip": 30.0,
            "gaming_realtime": 30.0,
        },
        "streams": [
            {"size": 64, "weight": 100, "proto": "UDP", "sport": 10000, "dport": 20000, "dscp": 0},
        ],
    },
    "bw_1518b": {
        "id": "bw_1518b",
        "name": "1518B Standard MTU Line-Rate Throughput",
        "short_name": "1518B Max Throughput",
        "category": "Throughput Benchmark",
        "traffic_engine": "trex_stl",
        "description": "Full 1518-byte standard Ethernet frames designed to validate maximum L2/L3 throughput across 1 Gbps and 10 Gbps links.",
        "avg_frame_size": 1518,
        "default_rate_pct": 100.0,
        "target_gbps": 10.0,
        "default_users": 1000,
        "default_devices": 2000,
        "tcp_pct": 70,
        "udp_pct": 30,
        "dscp": 0,
        "vlan_id": 0,
        "protocol_mix": {
            "bulk_downloads": 50.0,
            "backups_storage": 30.0,
            "cloud_files": 20.0,
        },
        "streams": [
            {"size": 1518, "weight": 100, "proto": "UDP", "sport": 445, "dport": 445, "dscp": 0},
        ],
    },
    "jumbo_9000b": {
        "id": "jumbo_9000b",
        "name": "9000B Jumbo Frame Datacenter / Storage",
        "short_name": "9000B Jumbo Frames",
        "category": "Storage & East-West",
        "traffic_engine": "trex_stl",
        "description": "9000-byte Jumbo Frames validating MTU>=9000 switching paths, storage replication, and high-efficiency 10GbE trunks.",
        "avg_frame_size": 9000,
        "default_rate_pct": 100.0,
        "target_gbps": 10.0,
        "default_users": 250,
        "default_devices": 500,
        "tcp_pct": 80,
        "udp_pct": 20,
        "dscp": 26,
        "vlan_id": 0,
        "protocol_mix": {
            "backups_storage": 75.0,
            "cloud_files": 25.0,
        },
        "streams": [
            {"size": 9000, "weight": 100, "proto": "UDP", "sport": 3260, "dport": 3260, "dscp": 26},
        ],
    },
    "voip_qos": {
        "id": "voip_qos",
        "name": "Realtime Voice & Collaboration QoS Validation",
        "short_name": "VoIP & Teams QoS",
        "category": "Latency & QoS",
        "traffic_engine": "trex_stl",
        "description": "DSCP EF (46) voice packets paired with AF41 collaboration video to measure queuing latency, P95/P99 tail latency, and jitter.",
        "avg_frame_size": 260,
        "default_rate_pct": 25.0,
        "target_gbps": 2.5,
        "default_users": 2500,
        "default_devices": 5000,
        "tcp_pct": 15,
        "udp_pct": 85,
        "dscp": 46,
        "vlan_id": 0,
        "protocol_mix": {
            "voip_sip": 45.0,
            "teams_collab": 40.0,
            "m365_productivity": 15.0,
        },
        "streams": [
            {"size": 160, "weight": 65, "proto": "UDP", "sport": 16384, "dport": 16384, "dscp": 46},
            {"size": 980, "weight": 35, "proto": "UDP", "sport": 3478, "dport": 3478, "dscp": 34},
        ],
    },
    "voice_under_load": {
        "id": "voice_under_load",
        "name": "Voice Quality Under Load (EF voice + saturating bulk traffic)",
        "short_name": "Voice Under Load",
        "category": "Latency & QoS",
        "traffic_engine": "trex_stl",
        "description": "Sends DSCP EF (46) G.711-sized voice packets while filling the rest of the link with "
                       "best-effort 1518B bulk traffic. If QoS works, voice latency, jitter and MOS stay good "
                       "even though the link is nearly full. MOS is an ITU-T G.107 estimate from measured "
                       "latency/jitter/loss, not a real phone call.",
        "avg_frame_size": 1450,
        "default_rate_pct": 95.0,
        "target_gbps": 0.95,
        "default_users": 500,
        "default_devices": 1000,
        "tcp_pct": 0,
        "udp_pct": 100,
        "dscp": 46,
        "vlan_id": 0,
        "protocol_mix": {
            "voip_sip": 5.0,
            "bulk_downloads": 95.0,
        },
        "streams": [
            {"size": 214, "weight": 5, "proto": "UDP", "sport": 16384, "dport": 16384, "dscp": 46},
            {"size": 1518, "weight": 95, "proto": "UDP", "sport": 50000, "dport": 50000, "dscp": 0},
        ],
    },
    "udp_burst": {
        "id": "udp_burst",
        "name": "Microburst & Queue Buffer Tolerance",
        "short_name": "UDP Burst Stress",
        "category": "Buffer & Burst",
        "traffic_engine": "trex_stl",
        "description": "Back-to-back UDP packet bursts evaluating switch and gateway ingress buffer absorption and tail-drop thresholds.",
        "avg_frame_size": 512,
        "default_rate_pct": 75.0,
        "target_gbps": 7.5,
        "default_users": 5000,
        "default_devices": 10000,
        "tcp_pct": 10,
        "udp_pct": 90,
        "dscp": 0,
        "vlan_id": 0,
        "protocol_mix": {
            "video_streaming": 40.0,
            "social_browsing": 30.0,
            "gaming_realtime": 20.0,
            "dns_queries": 10.0,
        },
        "streams": [
            {"size": 512, "weight": 60, "proto": "UDP", "sport": 9000, "dport": 9001, "dscp": 0},
            {"size": 128, "weight": 40, "proto": "UDP", "sport": 9002, "dport": 9003, "dscp": 0},
        ],
    },
    "custom": {
        "id": "custom",
        "name": "Custom Enterprise Traffic Mix",
        "short_name": "Custom Mix Builder",
        "category": "Custom Workload",
        "traffic_engine": "trex_astf",
        "description": "Operator-configured synthetic workload profile with custom application weights, frame size bounds, VLAN/DSCP tags, and IP pools.",
        "avg_frame_size": 512,
        "default_rate_pct": 50.0,
        "target_gbps": 5.0,
        "default_users": 10000,
        "default_devices": 15000,
        "tcp_pct": 80,
        "udp_pct": 20,
        "dscp": 0,
        "vlan_id": 0,
        "protocol_mix": {
            "video_streaming": 25.0,
            "m365_productivity": 15.0,
            "teams_collab": 10.0,
            "social_browsing": 15.0,
            "messaging_chat": 10.0,
            "web_browsing": 15.0,
            "voip_sip": 10.0,
        },
        "streams": [
            {"size": 512, "weight": 100, "proto": "UDP", "sport": 12345, "dport": 443, "dscp": 0},
        ],
    },
}


STAGED_LOAD_STEPS: List[Dict[str, Any]] = [
    {"step": 1, "rate_pct": 10.0, "target_10g_gbps": 1.0, "label": "10% Warmup (1.0 Gbps @ 10G)"},
    {"step": 2, "rate_pct": 25.0, "target_10g_gbps": 2.5, "label": "25% Quarter Load (2.5 Gbps @ 10G)"},
    {"step": 3, "rate_pct": 50.0, "target_10g_gbps": 5.0, "label": "50% Half Line Rate (5.0 Gbps @ 10G)"},
    {"step": 4, "rate_pct": 75.0, "target_10g_gbps": 7.5, "label": "75% High Load (7.5 Gbps @ 10G)"},
    {"step": 5, "rate_pct": 90.0, "target_10g_gbps": 9.0, "label": "90% Near-Saturation (9.0 Gbps @ 10G)"},
    {"step": 6, "rate_pct": 100.0, "target_10g_gbps": 10.0, "label": "100% Full Line Rate (10.0 Gbps @ 10G)"},
]


USER_SCALE_PRESETS: List[Dict[str, Any]] = [
    {"id": "efg_500", "name": "500 Users — Baseline", "users": 500, "devices": 1000, "target_gbps": 0.25, "recommended_rate_pct": 2.5},
    {"id": "efg_1000", "name": "1,000 Users", "users": 1000, "devices": 2000, "target_gbps": 0.50, "recommended_rate_pct": 5.0},
    {"id": "efg_2500", "name": "2,500 Users", "users": 2500, "devices": 5000, "target_gbps": 1.25, "recommended_rate_pct": 12.5},
    {"id": "efg_5000", "name": "5,000 Users", "users": 5000, "devices": 10000, "target_gbps": 2.50, "recommended_rate_pct": 25.0},
    {"id": "efg_7500", "name": "7,500 Users", "users": 7500, "devices": 15000, "target_gbps": 3.75, "recommended_rate_pct": 37.5},
    {"id": "efg_10000", "name": "10,000 Users — EFG Target", "users": 10000, "devices": 20000, "target_gbps": 5.00, "recommended_rate_pct": 50.0},
    {"id": "efg_25000", "name": "25,000 Users", "users": 25000, "devices": 50000, "target_gbps": 1.00, "recommended_rate_pct": 10.0},
    {"id": "efg_50000", "name": "50,000 Users", "users": 50000, "devices": 100000, "target_gbps": 1.00, "recommended_rate_pct": 10.0},
    {"id": "efg_100000", "name": "100,000 Users — Maximum Scale", "users": 100000, "devices": 200000, "target_gbps": 1.00, "recommended_rate_pct": 10.0},
]

EFG_USER_SCENARIOS: List[Dict[str, Any]] = [
    {
        "id": "scenario_500_baseline",
        "name": "500 Users — Enterprise Baseline",
        "users": 500,
        "devices": 1000,
        "target_gbps": 0.25,
        "traffic_engine": "trex_astf",
        "profile_id": "imix",
        "test_mode": "phased",
        "ramp_up_sec": 15,
        "steady_sec": 60,
        "ramp_down_sec": 10,
        "description": "Stateful TCP/UDP baseline across 500 emulated enterprise user IPs (~500 Kbps/user average) to establish baseline EFG CPU, memory, and session latency.",
    },
    {
        "id": "scenario_1000_users",
        "name": "1,000 Users — Branch / Mid-Market Load",
        "users": 1000,
        "devices": 2000,
        "target_gbps": 0.50,
        "traffic_engine": "trex_astf",
        "profile_id": "imix",
        "test_mode": "phased",
        "ramp_up_sec": 20,
        "steady_sec": 90,
        "ramp_down_sec": 10,
        "description": "1,000 simultaneous stateful enterprise users executing mixed web, video, M365, Teams UDP, messaging, file sync, and DNS sessions.",
    },
    {
        "id": "scenario_2500_users",
        "name": "2,500 Users — Regional Campus Load",
        "users": 2500,
        "devices": 5000,
        "target_gbps": 1.25,
        "traffic_engine": "trex_astf",
        "profile_id": "imix",
        "test_mode": "phased",
        "ramp_up_sec": 30,
        "steady_sec": 120,
        "ramp_down_sec": 15,
        "description": "2,500 concurrent enterprise users testing stateful NAT translation, firewall rule evaluation, and multi-session concurrency.",
    },
    {
        "id": "scenario_5000_users",
        "name": "5,000 Users — Half-Scale EFG Validation",
        "users": 5000,
        "devices": 10000,
        "target_gbps": 2.50,
        "traffic_engine": "trex_astf",
        "profile_id": "imix",
        "test_mode": "phased",
        "ramp_up_sec": 45,
        "steady_sec": 180,
        "ramp_down_sec": 15,
        "description": "5,000 simultaneous enterprise users ramping smoothly to 2.5 Gbps of mixed TCP/UDP stateful application workloads.",
    },
    {
        "id": "scenario_7500_users",
        "name": "7,500 Users — High-Density Pre-Peak Load",
        "users": 7500,
        "devices": 15000,
        "target_gbps": 3.75,
        "traffic_engine": "trex_astf",
        "profile_id": "imix",
        "test_mode": "phased",
        "ramp_up_sec": 60,
        "steady_sec": 180,
        "ramp_down_sec": 20,
        "description": "7,500 concurrent users validating EFG connection tracking table scaling, IPS/DPI CPU headroom, and tail latency before full 10K peak.",
    },
    {
        "id": "scenario_10000_users",
        "name": "10,000 Users — Primary EFG Acceptance Test",
        "users": 10000,
        "devices": 20000,
        "target_gbps": 5.00,
        "traffic_engine": "trex_astf",
        "profile_id": "imix",
        "test_mode": "phased",
        "ramp_up_sec": 60,
        "steady_sec": 300,
        "ramp_down_sec": 30,
        "description": "Primary validation objective: 10,000 distinct emulated enterprise users concurrently generating web, video, M365, Teams, messaging, uploads/downloads, DNS, and backup flows.",
    },
    {
        "id": "scenario_10000_soak",
        "name": "Extended 10,000-User Soak & Stability Test",
        "users": 10000,
        "devices": 20000,
        "target_gbps": 5.00,
        "traffic_engine": "trex_astf",
        "profile_id": "imix",
        "test_mode": "soak",
        "ramp_up_sec": 120,
        "steady_sec": 1800,
        "ramp_down_sec": 60,
        "description": "Long-duration 33-minute (configurable up to 24h) 10,000-user soak test detecting EFG memory leaks, thermal throttling, state-table exhaustion, and TCP retransmission creep.",
    },
    {
        "id": "scenario_25000_users",
        "name": "25,000 Users — Large Campus",
        "users": 25000,
        "devices": 50000,
        "target_gbps": 1.00,
        "traffic_engine": "trex_astf",
        "profile_id": "imix",
        "test_mode": "phased",
        "ramp_up_sec": 60,
        "steady_sec": 300,
        "ramp_down_sec": 30,
        "description": "25,000 distinct client IPs. Stresses the gateway's NAT/connection table and ARP scale. Target is 1 Gbps to fit the 1GbE test ports — raise it if a 10GbE NIC is fitted.",
    },
    {
        "id": "scenario_50000_users",
        "name": "50,000 Users — Connection-Table Stress",
        "users": 50000,
        "devices": 100000,
        "target_gbps": 1.00,
        "traffic_engine": "trex_astf",
        "profile_id": "imix",
        "test_mode": "phased",
        "ramp_up_sec": 90,
        "steady_sec": 300,
        "ramp_down_sec": 30,
        "description": "50,000 distinct client IPs with a slow ramp. Shows where gateway CPU, memory and latency start to bend as the session table fills.",
    },
    {
        "id": "scenario_100000_users",
        "name": "100,000 Users — Maximum Scale",
        "users": 100000,
        "devices": 200000,
        "target_gbps": 1.00,
        "traffic_engine": "trex_astf",
        "profile_id": "imix",
        "test_mode": "phased",
        "ramp_up_sec": 120,
        "steady_sec": 300,
        "ramp_down_sec": 60,
        "description": "100,000 distinct client IPs (16.0.0.1 – 16.1.134.160) — the appliance maximum. Finds the gateway's breaking point for user/session scale. Watch gateway CPU and drops closely.",
    },
    {
        "id": "scenario_10gbps_linerate",
        "name": "10 Gbps Line-Rate Forwarding Benchmark",
        "users": 10000,
        "devices": 20000,
        "target_gbps": 10.00,
        "traffic_engine": "trex_stl",
        "profile_id": "bw_1518b",
        "test_mode": "phased",
        "ramp_up_sec": 20,
        "steady_sec": 120,
        "ramp_down_sec": 10,
        "description": "Maximum 10.00 Gbps wire-speed forwarding test (requires dual 10GbE physical test ports cabled across DUT).",
    },
]


def compute_effective_frame_size(profile_id: str, custom_cfg: Dict[str, Any]) -> int:
    if profile_id == "custom" and custom_cfg.get("frame_size"):
        return max(64, min(9000, int(custom_cfg["frame_size"])))
    mix = custom_cfg.get("protocol_mix")
    if isinstance(mix, dict) and len(mix) > 0:
        norm = normalize_mix_to_100(mix)
        weighted = 0.0
        for k, pct in norm.items():
            w_meta = WORKLOAD_MAP.get(k)
            sz = w_meta["avg_frame_bytes"] if w_meta else 576
            weighted += (pct / 100.0) * sz
        if weighted >= 64:
            return max(64, min(9000, int(round(weighted))))
    base = PREBUILT_PROFILES.get(profile_id, PREBUILT_PROFILES["imix"])
    return int(base.get("avg_frame_size", 594))


def build_streams_from_workload_mix(mix: Dict[str, Any], vlan_id: int = 0, default_dscp: int = 0) -> List[Dict[str, Any]]:
    """Convert normalized 12-category application mix into concrete TRex STL stream definitions."""
    norm = normalize_mix_to_100(mix)
    streams: List[Dict[str, Any]] = []
    for key, pct in norm.items():
        if pct <= 0.05:
            continue
        meta = WORKLOAD_MAP.get(key)
        if not meta:
            continue
        proto = "UDP" if "UDP" in meta["protocol"] and "TCP" not in meta["protocol"] else ("TCP" if "TCP" in meta["protocol"] else "UDP")
        port = meta["ports"][0] if meta.get("ports") else 443
        streams.append({
            "name": key,
            "size": int(meta["avg_frame_bytes"]),
            "weight": float(pct),
            "proto": proto,
            "sport": 32768 + (len(streams) * 100),
            "dport": int(port),
            "dscp": int(meta["dscp"]) if default_dscp == 0 else int(default_dscp),
            "vlan_id": vlan_id,
        })
    if not streams:
        streams.append({"name": "default", "size": 576, "weight": 100.0, "proto": "TCP", "sport": 40000, "dport": 443, "dscp": default_dscp, "vlan_id": vlan_id})
    return streams


def calculate_mos_score(lat_avg_us: float, jitter_us: float, drop_pct: float) -> float:
    """ITU-T G.107 E-model approximation ONLY when real latency & loss measurements exist."""
    if lat_avg_us <= 0 and jitter_us <= 0 and drop_pct <= 0:
        return 0.0
    delay_ms = (lat_avg_us / 1000.0) + (jitter_us * 2.0 / 1000.0)
    id_factor = (delay_ms / 40.0) if delay_ms < 160.0 else ((delay_ms - 120.0) / 10.0)
    # G.107 Ie,eff = Ie + (95 - Ie) * Ppl / (Ppl + Bpl); G.711 with PLC: Ie=0, Bpl=25.1 (was 30*P/(P+10), far too lenient)
    ie_eff = 95.0 * (drop_pct / (drop_pct + 25.1)) if drop_pct > 0 else 0.0
    r_factor = max(0.0, min(93.2, 93.2 - id_factor - ie_eff))
    if r_factor <= 0:
        return 1.0
    mos = 1.0 + 0.035 * r_factor + r_factor * (r_factor - 60.0) * (100.0 - r_factor) * 7.0e-6
    return round(max(1.0, min(4.5, mos)), 2)
