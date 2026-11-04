"""
Traffic Profiles, Users & Devices Scale Synthesizer, and Custom Packet Builder
for Stephan Van Vuuren's Network Tester.
"""
from typing import Any, Dict, List


PREBUILT_PROFILES: Dict[str, Dict[str, Any]] = {
    "imix": {
        "id": "imix",
        "name": "IMIX Realistic Enterprise Traffic",
        "short_name": "IMIX Realistic",
        "category": "Enterprise Mix",
        "icon": "layers",
        "color": "#00E5FF",
        "description": "Standard Internet Mix (7x 64B, 4x 570B, 1x 1518B) + Web, VoIP, Video, and DNS flows simulating a busy enterprise network.",
        "avg_frame_size": 354,
        "default_rate_pct": 35.0,
        "default_users": 500,
        "default_devices": 1250,
        "dscp": 0,
        "vlan_id": 0,
        "protocol_mix": {
            "web_https": 40,
            "video_streaming": 25,
            "voip_rtp": 15,
            "file_smb": 10,
            "dns_control": 5,
            "gaming_udp": 5,
        },
        "streams": [
            {"size": 64, "weight": 58, "proto": "UDP", "sport": 5060, "dport": 5060, "dscp": 46},
            {"size": 570, "weight": 33, "proto": "TCP", "sport": 443, "dport": 52400, "dscp": 0},
            {"size": 1518, "weight": 9, "proto": "UDP", "sport": 8554, "dport": 5004, "dscp": 34},
        ],
    },
    "stress_64b": {
        "id": "stress_64b",
        "name": "64B Max PPS Torture Stress",
        "short_name": "64B Max PPS",
        "category": "ASIC / PPS Torture",
        "icon": "zap",
        "color": "#F43F5E",
        "description": "Minimum 64-byte Ethernet frames at maximum packet-per-second rate to stress switch ASICs, firewall state tables, and routing engines.",
        "avg_frame_size": 64,
        "default_rate_pct": 50.0,
        "default_users": 2500,
        "default_devices": 5000,
        "dscp": 0,
        "vlan_id": 0,
        "protocol_mix": {
            "web_https": 5,
            "video_streaming": 0,
            "voip_rtp": 35,
            "file_smb": 0,
            "dns_control": 30,
            "gaming_udp": 30,
        },
        "streams": [
            {"size": 64, "weight": 100, "proto": "UDP", "sport": 10000, "dport": 20000, "dscp": 0},
        ],
    },
    "bw_1518b": {
        "id": "bw_1518b",
        "name": "1518B Max Line-Rate Bandwidth",
        "short_name": "1518B Max BW",
        "category": "Throughput Saturation",
        "icon": "gauge",
        "color": "#10B981",
        "description": "Full 1518-byte standard MTU frames designed to saturate 1Gbps and 10Gbps physical links and verify wire-speed backplane capacity.",
        "avg_frame_size": 1518,
        "default_rate_pct": 80.0,
        "default_users": 200,
        "default_devices": 400,
        "dscp": 0,
        "vlan_id": 0,
        "protocol_mix": {
            "web_https": 30,
            "video_streaming": 35,
            "voip_rtp": 0,
            "file_smb": 35,
            "dns_control": 0,
            "gaming_udp": 0,
        },
        "streams": [
            {"size": 1518, "weight": 100, "proto": "UDP", "sport": 445, "dport": 445, "dscp": 0},
        ],
    },
    "jumbo_9000b": {
        "id": "jumbo_9000b",
        "name": "9000B Jumbo Frame Datacenter Storage",
        "short_name": "9000B Jumbo",
        "category": "SAN / Datacenter",
        "icon": "database",
        "color": "#8B5CF6",
        "description": "9000-byte Jumbo Frames simulating iSCSI, NFS, vMotion, and AI cluster East-West storage replication across 10GbE trunks.",
        "avg_frame_size": 9000,
        "default_rate_pct": 90.0,
        "default_users": 50,
        "default_devices": 128,
        "dscp": 26,
        "vlan_id": 0,
        "protocol_mix": {
            "web_https": 5,
            "video_streaming": 10,
            "voip_rtp": 0,
            "file_smb": 85,
            "dns_control": 0,
            "gaming_udp": 0,
        },
        "streams": [
            {"size": 9000, "weight": 100, "proto": "UDP", "sport": 3260, "dport": 3260, "dscp": 26},
        ],
    },
    "voip_qos": {
        "id": "voip_qos",
        "name": "VoIP & Unified Comms (SIP + RTP G.711)",
        "short_name": "VoIP / QoS SLA",
        "category": "Voice & Video SLA",
        "icon": "phone",
        "color": "#F59E0B",
        "description": "High-priority DSCP EF (46) 160B RTP voice packets + AF41 video streams to measure jitter, micro-drops, and live ITU-T G.107 MOS voice quality.",
        "avg_frame_size": 180,
        "default_rate_pct": 25.0,
        "default_users": 1000,
        "default_devices": 2000,
        "dscp": 46,
        "vlan_id": 20,
        "protocol_mix": {
            "web_https": 10,
            "video_streaming": 30,
            "voip_rtp": 55,
            "file_smb": 0,
            "dns_control": 5,
            "gaming_udp": 0,
        },
        "streams": [
            {"size": 160, "weight": 75, "proto": "UDP", "sport": 16384, "dport": 16384, "dscp": 46},
            {"size": 1280, "weight": 25, "proto": "UDP", "sport": 5004, "dport": 5004, "dscp": 34},
        ],
    },
    "udp_burst": {
        "id": "udp_burst",
        "name": "UDP Microburst & Bufferbloat Hammer",
        "short_name": "UDP Microburst",
        "category": "Buffer & Queue Stress",
        "icon": "flame",
        "color": "#EC4899",
        "description": "High-intensity back-to-back UDP packet bursts designed to overflow shallow switch ingress buffers and expose tail-drop / RED queue behavior.",
        "avg_frame_size": 512,
        "default_rate_pct": 65.0,
        "default_users": 1500,
        "default_devices": 3000,
        "dscp": 0,
        "vlan_id": 0,
        "protocol_mix": {
            "web_https": 10,
            "video_streaming": 40,
            "voip_rtp": 10,
            "file_smb": 10,
            "dns_control": 10,
            "gaming_udp": 20,
        },
        "streams": [
            {"size": 512, "weight": 60, "proto": "UDP", "sport": 9000, "dport": 9001, "dscp": 0},
            {"size": 128, "weight": 40, "proto": "UDP", "sport": 9002, "dport": 9003, "dscp": 0},
        ],
    },
    "campus_sim": {
        "id": "campus_sim",
        "name": "Multi-User Campus & CCTV Surveillance Mix",
        "short_name": "Campus + CCTV",
        "category": "Multi-User Simulation",
        "icon": "users",
        "color": "#38BDF8",
        "description": "Simulates hundreds of office staff on Wi-Fi/LAN alongside 4K RTSP IP security cameras, cloud SaaS apps, Teams calls, and background backups.",
        "avg_frame_size": 740,
        "default_rate_pct": 45.0,
        "default_users": 1000,
        "default_devices": 3500,
        "dscp": 34,
        "vlan_id": 0,
        "protocol_mix": {
            "web_https": 30,
            "video_streaming": 35,
            "voip_rtp": 15,
            "file_smb": 10,
            "dns_control": 5,
            "gaming_udp": 5,
        },
        "streams": [
            {"size": 1380, "weight": 45, "proto": "UDP", "sport": 554, "dport": 50000, "dscp": 34},
            {"size": 570, "weight": 35, "proto": "TCP", "sport": 443, "dport": 51000, "dscp": 0},
            {"size": 160, "weight": 20, "proto": "UDP", "sport": 5060, "dport": 5060, "dscp": 46},
        ],
    },
    "custom": {
        "id": "custom",
        "name": "Custom Packet & Traffic Mix Builder",
        "short_name": "Custom Builder",
        "category": "Custom L2/L3/QoS",
        "icon": "sliders",
        "color": "#A855F7",
        "description": "Full control over frame size (64B-9000B), 802.1Q VLAN tagging, DSCP QoS class, Src/Dst IP & MAC pools, and custom application mix.",
        "avg_frame_size": 512,
        "default_rate_pct": 30.0,
        "default_users": 250,
        "default_devices": 600,
        "dscp": 0,
        "vlan_id": 0,
        "protocol_mix": {
            "web_https": 35,
            "video_streaming": 25,
            "voip_rtp": 15,
            "file_smb": 15,
            "dns_control": 5,
            "gaming_udp": 5,
        },
        "streams": [
            {"size": 512, "weight": 100, "proto": "UDP", "sport": 12345, "dport": 80, "dscp": 0},
        ],
    },
}


USER_SCALE_PRESETS: List[Dict[str, Any]] = [
    {
        "id": "small_branch",
        "name": "Small Office / Retail Branch",
        "users": 35,
        "devices": 95,
        "recommended_rate_pct": 10.0,
        "device_breakdown": {"laptops": 35, "phones_voip": 25, "iot_cctv": 20, "printers_ap": 15},
    },
    {
        "id": "medium_business",
        "name": "Medium Enterprise Floor",
        "users": 250,
        "devices": 680,
        "recommended_rate_pct": 25.0,
        "device_breakdown": {"laptops": 250, "phones_voip": 220, "iot_cctv": 130, "printers_ap": 80},
    },
    {
        "id": "campus_hq",
        "name": "Corporate HQ / Hospital / School Campus",
        "users": 1500,
        "devices": 4200,
        "recommended_rate_pct": 55.0,
        "device_breakdown": {"laptops": 1800, "phones_voip": 1200, "iot_cctv": 850, "printers_ap": 350},
    },
    {
        "id": "isp_stadium",
        "name": "ISP Core / Stadium / Data Center Torture",
        "users": 15000,
        "devices": 45000,
        "recommended_rate_pct": 95.0,
        "device_breakdown": {"laptops": 22000, "phones_voip": 12000, "iot_cctv": 8000, "printers_ap": 3000},
    },
]


def compute_effective_frame_size(profile_id: str, custom_cfg: Dict[str, Any]) -> int:
    """Compute weighted average frame size from either custom builder or traffic mix."""
    if profile_id == "custom" and custom_cfg.get("frame_size"):
        return max(64, min(9000, int(custom_cfg["frame_size"])))

    mix = custom_cfg.get("protocol_mix")
    if isinstance(mix, dict) and sum(mix.values()) > 0:
        # Weighted average frame size based on traffic types:
        # web_https: ~580B, video_streaming: ~1360B, voip_rtp: ~160B, file_smb: ~1518B, dns_control: ~96B, gaming_udp: ~128B
        weights = {
            "web_https": 580,
            "video_streaming": 1360,
            "voip_rtp": 160,
            "file_smb": 1500,
            "dns_control": 96,
            "gaming_udp": 128,
        }
        total_w = sum(max(0, float(mix.get(k, 0))) for k in weights)
        if total_w > 0:
            weighted_sum = sum(max(0, float(mix.get(k, 0))) * sz for k, sz in weights.items())
            return max(64, min(9000, int(round(weighted_sum / total_w))))

    base = PREBUILT_PROFILES.get(profile_id, PREBUILT_PROFILES["imix"])
    return int(base.get("avg_frame_size", 354))


def calculate_mos_score(lat_avg_us: float, jitter_us: float, drop_pct: float) -> float:
    """
    ITU-T G.107 E-Model approximation converting Latency (us), Jitter (us), and Packet Loss (%)
    into a plain-English VoIP Mean Opinion Score (1.00 - 4.50).
    """
    delay_ms = (lat_avg_us / 1000.0) + (jitter_us * 2.0 / 1000.0)
    # Effective delay d
    if delay_ms < 160.0:
        id_factor = delay_ms / 40.0
    else:
        id_factor = (delay_ms - 120.0) / 10.0

    # Equipment impairment from packet loss
    ie_eff = 30.0 * (drop_pct / (drop_pct + 10.0)) if drop_pct > 0 else 0.0
    r_factor = max(0.0, min(93.2, 93.2 - id_factor - ie_eff))

    if r_factor <= 0:
        return 1.0
    if r_factor > 100:
        return 4.5
    mos = 1.0 + 0.035 * r_factor + r_factor * (r_factor - 60.0) * (100.0 - r_factor) * 7.0e-6
    return round(max(1.0, min(4.5, mos)), 2)
