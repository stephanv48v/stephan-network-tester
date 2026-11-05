"""
Cisco TRex ASTF (Advanced Stateful) Multi-User Enterprise Workload Builder
for Cisco TRex Network Test Studio (Dell PowerEdge R640 -> UniFi EFG).

Builds genuine stateful TCP 3-way-handshake + UDP client/server ASTFProfiles across
up to 10,000 distinct emulated LAN client IPs (Port 0) communicating through the
Device Under Test (UniFi Enterprise Fortress Gateway) with a controlled WAN/Internet
Server Emulator (Port 1).

Key Engineering Properties:
  - Separates Simulated User Count (IP pool & concurrency) from Target Bandwidth (CPS pacing).
  - Models variable session durations, think-time delays, bursty & sustained flows,
    bidirectional uploads & downloads, TCP connection establishment/teardown, and UDP media/DNS.
  - Synthetic Pattern Notice: Emulates realistic L4/L7 byte lengths, burst timing, and TCP/UDP
    state transitions; does not execute proprietary commercial encryption/authentication protocols.
"""
import ipaddress
from typing import Any, Dict, List, Tuple


def compute_client_ip_range(base_ip: str, user_count: int) -> Tuple[str, str, int]:
    """Compute sequential IPv4 range [start_ip, end_ip] for exact simulated user population."""
    count = max(1, min(65000, int(user_count)))
    try:
        start_int = int(ipaddress.IPv4Address(base_ip))
    except Exception:
        start_int = int(ipaddress.IPv4Address("16.0.0.1"))
    end_int = start_int + count - 1
    return str(ipaddress.IPv4Address(start_int)), str(ipaddress.IPv4Address(end_int)), count


# Approximate total L7+L4 wire bytes exchanged per single ASTF session for each template,
# used to calibrate initial CPS so Target Bandwidth and Simulated Users remain independent.
TEMPLATE_BYTES_PER_SESSION: Dict[str, int] = {
    "web_browsing": 72_000,         # ~72 KB multi-request keepalive web page load
    "social_browsing": 235_000,     # ~235 KB bursty feed + media clips
    "video_streaming": 1_060_000,   # ~1.06 MB chunked ABR video stream (4 x 256 KB chunks)
    "m365_productivity": 34_000,    # ~34 KB bidirectional SaaS API sync + upload
    "teams_collab": 12_800,         # ~12.8 KB bidirectional UDP voice/video burst
    "messaging_chat": 19_500,       # ~19.5 KB long-lived chat + attachment
    "cloud_files": 270_000,         # ~270 KB upstream/downstream cloud file sync
    "bulk_downloads": 535_000,      # ~535 KB sustained HTTPS-like object download
    "dns_queries": 310,             # ~310 B UDP query + response
    "voip_sip": 3_600,              # ~3.6 KB G.711 RTP voice burst
    "gaming_realtime": 2_800,       # ~2.8 KB high-tickrate UDP game state exchange
    "backups_storage": 398_000,     # ~398 KB sustained upstream client backup transfer
}


def build_astf_enterprise_profile(
    astf_api: Dict[str, Any],
    simulated_users: int,
    target_bps: float,
    normalized_mix: Dict[str, float],
    src_ip_base: str = "16.0.0.1",
    dst_ip_base: str = "48.0.0.1",
) -> Tuple[Any, Dict[str, Any]]:
    """
    Construct a multi-template Cisco TRex ASTFProfile representing `simulated_users`
    concurrent enterprise users with weighted application behaviors.
    """
    ASTFProfile = astf_api["ASTFProfile"]
    ASTFProgram = astf_api["ASTFProgram"]
    ASTFIPGen = astf_api["ASTFIPGen"]
    ASTFIPGenDist = astf_api["ASTFIPGenDist"]
    ASTFIPGenGlobal = astf_api["ASTFIPGenGlobal"]
    ASTFTemplate = astf_api["ASTFTemplate"]
    ASTFTCPClientTemplate = astf_api["ASTFTCPClientTemplate"]
    ASTFTCPServerTemplate = astf_api["ASTFTCPServerTemplate"]
    ASTFUDPClientTemplate = astf_api.get("ASTFUDPClientTemplate")
    ASTFUDPServerTemplate = astf_api.get("ASTFUDPServerTemplate")
    ASTFAssociationRule = astf_api["ASTFAssociationRule"]

    c_start, c_end, ip_count = compute_client_ip_range(src_ip_base, simulated_users)
    s_start, s_end, _ = compute_client_ip_range(dst_ip_base, min(250, max(16, simulated_users // 25)))

    ip_gen_c = ASTFIPGenDist(ip_range=[c_start, c_end], distribution="seq")
    ip_gen_s = ASTFIPGenDist(ip_range=[s_start, s_end], distribution="seq")
    ip_gen = ASTFIPGen(
        glob=ASTFIPGenGlobal(ip_offset="1.0.0.0"),
        dist_client=ip_gen_c,
        dist_server=ip_gen_s,
    )

    templates: List[Any] = []
    template_summary: List[Dict[str, Any]] = []

    def add_tcp_template(key: str, port: int, prog_c: Any, prog_s: Any, weight_pct: float) -> None:
        if weight_pct <= 0.05:
            return
        share_bps = max(50_000.0, target_bps * (weight_pct / 100.0))
        bytes_per_sess = TEMPLATE_BYTES_PER_SESSION.get(key, 64_000)
        cps = max(0.5, min(25000.0, share_bps / (bytes_per_sess * 8.0)))
        tc = ASTFTCPClientTemplate(program=prog_c, ip_gen=ip_gen, cps=round(cps, 2), port=port)
        ts = ASTFTCPServerTemplate(program=prog_s, assoc=ASTFAssociationRule(port=port))
        templates.append(ASTFTemplate(client_template=tc, server_template=ts))
        template_summary.append({"key": key, "proto": "TCP", "port": port, "weight_pct": weight_pct, "target_cps": round(cps, 2)})

    def add_udp_template(key: str, port: int, prog_c: Any, prog_s: Any, weight_pct: float) -> None:
        if weight_pct <= 0.05 or ASTFUDPClientTemplate is None or ASTFUDPServerTemplate is None:
            return
        share_bps = max(20_000.0, target_bps * (weight_pct / 100.0))
        bytes_per_sess = TEMPLATE_BYTES_PER_SESSION.get(key, 2_000)
        # Cap UDP session CPS to avoid exhausting ephemeral UDP sockets on virtual veth
        cps = max(0.5, min(8000.0, share_bps / (bytes_per_sess * 8.0)))
        uc = ASTFUDPClientTemplate(program=prog_c, ip_gen=ip_gen, cps=round(cps, 2), port=port)
        us = ASTFUDPServerTemplate(program=prog_s, assoc=ASTFAssociationRule(port=port))
        templates.append(ASTFTemplate(client_template=uc, server_template=us))
        template_summary.append({"key": key, "proto": "UDP", "port": port, "weight_pct": weight_pct, "target_cps": round(cps, 2)})

    # 1. Web Browsing & HTTPS-like Keepalive Sessions (Port 443)
    w_web = float(normalized_mix.get("web_browsing", 0.0))
    if w_web > 0:
        pc, ps = ASTFProgram(), ASTFProgram()
        req1 = b"GET /portal/home HTTP/1.1\r\nHost: www.enterprise.test\r\nUser-Agent: Mozilla/5.0\r\n\r\n"
        resp1 = b"HTTP/1.1 200 OK\r\nContent-Type: text/html\r\n\r\n" + (b"W" * 24000)
        req2 = b"GET /static/app.bundle.js HTTP/1.1\r\nHost: www.enterprise.test\r\n\r\n"
        resp2 = b"HTTP/1.1 200 OK\r\nContent-Type: application/javascript\r\n\r\n" + (b"J" * 44000)
        pc.send(req1); pc.recv(len(resp1)); pc.delay(120000); pc.send(req2); pc.recv(len(resp2))
        ps.recv(len(req1)); ps.send(resp1); ps.recv(len(req2)); ps.send(resp2)
        add_tcp_template("web_browsing", 443, pc, ps, w_web)

    # 2. Social Media Browsing & Media Bursts (Port 8443)
    w_soc = float(normalized_mix.get("social_browsing", 0.0))
    if w_soc > 0:
        pc, ps = ASTFProgram(), ASTFProgram()
        req1 = b"GET /feed/timeline?count=20 HTTP/1.1\r\nHost: social.cdn.test\r\n\r\n"
        resp1 = b"HTTP/1.1 200 OK\r\n\r\n" + (b"M" * 96000)
        req2 = b"POST /feed/engagement HTTP/1.1\r\nContent-Length: 900\r\n\r\n" + (b"E" * 900)
        resp2 = b"HTTP/1.1 200 OK\r\n\r\n" + (b"V" * 128000)
        pc.send(req1); pc.recv(len(resp1)); pc.delay(220000); pc.send(req2); pc.recv(len(resp2))
        ps.recv(len(req1)); ps.send(resp1); ps.recv(len(req2)); ps.send(resp2)
        add_tcp_template("social_browsing", 8443, pc, ps, w_soc)

    # 3. Video Streaming & Sustained ABR Chunk Downloads (Port 8080)
    w_vid = float(normalized_mix.get("video_streaming", 0.0))
    if w_vid > 0:
        pc, ps = ASTFProgram(), ASTFProgram()
        seg_req = b"GET /video/1080p/segment_init.m4s HTTP/1.1\r\nHost: stream.cdn.test\r\n\r\n"
        seg_rsp = b"HTTP/1.1 200 OK\r\nContent-Type: video/mp4\r\n\r\n" + (b"S" * 262144)
        for idx in range(4):
            pc.send(seg_req); pc.recv(len(seg_rsp))
            if idx < 3:
                pc.delay(250000)
            ps.recv(len(seg_req)); ps.send(seg_rsp)
        add_tcp_template("video_streaming", 8080, pc, ps, w_vid)

    # 4. Microsoft 365-style Application Activity (Port 9443)
    w_m365 = float(normalized_mix.get("m365_productivity", 0.0))
    if w_m365 > 0:
        pc, ps = ASTFProgram(), ASTFProgram()
        up1 = b"POST /collab/doc/delta HTTP/1.1\r\nContent-Length: 4096\r\n\r\n" + (b"D" * 4096)
        dn1 = b"HTTP/1.1 200 OK\r\n\r\n" + (b"A" * 14000)
        up2 = b"POST /mail/sync HTTP/1.1\r\nContent-Length: 6144\r\n\r\n" + (b"O" * 6144)
        dn2 = b"HTTP/1.1 200 OK\r\n\r\n" + (b"I" * 8192)
        pc.send(up1); pc.recv(len(dn1)); pc.delay(180000); pc.send(up2); pc.recv(len(dn2))
        ps.recv(len(up1)); ps.send(dn1); ps.recv(len(up2)); ps.send(dn2)
        add_tcp_template("m365_productivity", 9443, pc, ps, w_m365)

    # 5. Teams-style Voice/Video Bidirectional UDP (Port 3478)
    w_teams = float(normalized_mix.get("teams_collab", 0.0))
    if w_teams > 0:
        pc, ps = ASTFProgram(stream=False), ASTFProgram(stream=False)
        for _ in range(8):
            pc.send_msg(b"A" * 180); pc.recv_msg(1); pc.delay(20000)
            ps.recv_msg(1); ps.send_msg(b"V" * 960)
        add_udp_template("teams_collab", 3478, pc, ps, w_teams)

    # 6. WhatsApp-style Messaging & Small Media (Port 5222)
    w_msg = float(normalized_mix.get("messaging_chat", 0.0))
    if w_msg > 0:
        pc, ps = ASTFProgram(), ASTFProgram()
        m1 = b"CHAT_FRAME_OUT:" + (b"m" * 220)
        r1 = b"CHAT_ACK_IN:" + (b"a" * 240)
        m2 = b"MEDIA_NOTE_UP:" + (b"u" * 8192)
        r2 = b"MEDIA_DELIVERED:" + (b"d" * 9600)
        pc.send(m1); pc.recv(len(r1)); pc.delay(300000); pc.send(m2); pc.recv(len(r2))
        ps.recv(len(m1)); ps.send(r1); ps.recv(len(m2)); ps.send(r2)
        add_tcp_template("messaging_chat", 5222, pc, ps, w_msg)

    # 7. Cloud File Uploads & Downloads (Port 8082 Upload + Port 8081 Download)
    w_files = float(normalized_mix.get("cloud_files", 0.0))
    if w_files > 0:
        pc, ps = ASTFProgram(), ASTFProgram()
        up_payload = b"PUT /drive/upload.bin HTTP/1.1\r\nContent-Length: 131072\r\n\r\n" + (b"U" * 131072)
        dn_payload = b"HTTP/1.1 200 OK\r\n\r\n" + (b"F" * 131072)
        pc.send(up_payload); pc.recv(len(dn_payload))
        ps.recv(len(up_payload)); ps.send(dn_payload)
        add_tcp_template("cloud_files", 8082, pc, ps, w_files)

    # 8. Sustained Bulk Downloads (Port 8081)
    w_bulk = float(normalized_mix.get("bulk_downloads", 0.0))
    if w_bulk > 0:
        pc, ps = ASTFProgram(), ASTFProgram()
        req = b"GET /release/update-image.bin HTTP/1.1\r\nHost: dl.cdn.test\r\n\r\n"
        rsp = b"HTTP/1.1 200 OK\r\nContent-Length: 524288\r\n\r\n" + (b"B" * 524288)
        pc.send(req); pc.recv(len(rsp))
        ps.recv(len(req)); ps.send(rsp)
        add_tcp_template("bulk_downloads", 8081, pc, ps, w_bulk)

    # 9. DNS Query/Response Transactions (UDP Port 53)
    w_dns = float(normalized_mix.get("dns_queries", 0.0))
    if w_dns > 0:
        pc, ps = ASTFProgram(stream=False), ASTFProgram(stream=False)
        pc.send_msg(b"Q" * 64); pc.recv_msg(1)
        ps.recv_msg(1); ps.send_msg(b"R" * 164)
        add_udp_template("dns_queries", 53, pc, ps, w_dns)

    # 10. VoIP SIP/RTP Bearer Burst (UDP Port 5060)
    w_voip = float(normalized_mix.get("voip_sip", 0.0))
    if w_voip > 0:
        pc, ps = ASTFProgram(stream=False), ASTFProgram(stream=False)
        for _ in range(10):
            pc.send_msg(b"G" * 160); pc.recv_msg(1); pc.delay(20000)
            ps.recv_msg(1); ps.send_msg(b"G" * 160)
        add_udp_template("voip_sip", 5060, pc, ps, w_voip)

    # 11. Low-Latency Gaming UDP (UDP Port 27015)
    w_game = float(normalized_mix.get("gaming_realtime", 0.0))
    if w_game > 0:
        pc, ps = ASTFProgram(stream=False), ASTFProgram(stream=False)
        for _ in range(10):
            pc.send_msg(b"K" * 96); pc.recv_msg(1); pc.delay(16000)
            ps.recv_msg(1); ps.send_msg(b"W" * 128)
        add_udp_template("gaming_realtime", 27015, pc, ps, w_game)

    # 12. Background Synchronisation & Upstream Backups (TCP Port 873)
    w_bak = float(normalized_mix.get("backups_storage", 0.0))
    if w_bak > 0:
        pc, ps = ASTFProgram(), ASTFProgram()
        blk = b"SYNC_BACKUP_BLOCK_HEADER:" + (b"Z" * 196608)
        ack = b"SYNC_BLOCK_COMMITTED_OK\r\n"
        pc.send(blk); pc.recv(len(ack)); pc.delay(50000); pc.send(blk); pc.recv(len(ack))
        ps.recv(len(blk)); ps.send(ack); ps.recv(len(blk)); ps.send(ack)
        add_tcp_template("backups_storage", 873, pc, ps, w_bak)

    # Fallback if somehow empty
    if not templates:
        pc, ps = ASTFProgram(), ASTFProgram()
        pc.send(b"GET / HTTP/1.1\r\n\r\n"); pc.recv(16384)
        ps.recv(18); ps.send(b"HTTP/1.1 200 OK\r\n\r\n" + (b"X" * 16365))
        add_tcp_template("web_browsing", 443, pc, ps, 100.0)

    profile = ASTFProfile(default_ip_gen=ip_gen, templates=templates)
    meta = {
        "emulated_client_ip_start": c_start,
        "emulated_client_ip_end": c_end,
        "emulated_client_ip_count": ip_count,
        "emulated_server_ip_range": f"{s_start} - {s_end}",
        "active_template_count": len(templates),
        "templates": template_summary,
    }
    return profile, meta
