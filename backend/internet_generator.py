"""
Live Internet & WAN Gateway Traffic Engine for Cisco TRex Network Test Studio.
Generates real outbound/inbound Internet workloads routed through the active WAN gateway
(e.g. enp216s0 -> 10.20.30.1 UniFi Enterprise Fortress Gateway -> Internet) using:
  - Multi-worker HTTPS CDN download streams (Cloudflare Speedtest CDN & configurable URLs)
  - Optional HTTPS upload streams (Cloudflare __up or custom endpoint)
  - Interactive HTTPS web/SaaS requests
  - Real UDP DNS queries
  - Continuous ICMP/TCP RTT probe measuring real Avg, P95, P99 latency, RFC 3550 jitter, and loss.

All reported throughput, packet rates, active sockets, and latency statistics are measured
from real OS interface counters (/sys/class/net/<iface>/statistics) and live socket probes.
"""
import math
import os
import random
import re
import socket
import struct
import subprocess
import threading
import time
from collections import deque
from pathlib import Path
from typing import Any, Deque, Dict, List, Optional

import httpx


DEFAULT_DOWNLOAD_URLS = [
    "https://speed.cloudflare.com/__down?bytes=25000000",
    "https://speed.cloudflare.com/__down?bytes=10000000",
]
DEFAULT_UPLOAD_URL = "https://speed.cloudflare.com/__up"
DEFAULT_WEB_URLS = [
    "https://1.1.1.1/cdn-cgi/trace",
    "https://speed.cloudflare.com/cdn-cgi/trace",
]
DEFAULT_DNS_SERVERS = ["1.1.1.1", "8.8.8.8"]
DEFAULT_DNS_DOMAINS = ["cloudflare.com", "microsoft.com", "apple.com", "github.com", "google.com"]


def _read_iface_counters(ifname: str) -> Dict[str, int]:
    base = Path(f"/sys/class/net/{ifname}/statistics")
    if not base.exists():
        return {"tx_bytes": 0, "rx_bytes": 0, "tx_packets": 0, "rx_packets": 0, "drops": 0}
    def _rd(name: str) -> int:
        p = base / name
        try:
            return int(p.read_text().strip())
        except Exception:
            return 0
    return {
        "tx_bytes": _rd("tx_bytes"),
        "rx_bytes": _rd("rx_bytes"),
        "tx_packets": _rd("tx_packets"),
        "rx_packets": _rd("rx_packets"),
        "drops": _rd("rx_dropped") + _rd("tx_dropped"),
    }


def _build_dns_query(domain: str) -> bytes:
    tid = random.randint(1, 65534)
    header = struct.pack(">HHHHHH", tid, 0x0100, 1, 0, 0, 0)
    qname = b"".join(bytes([len(lbl)]) + lbl.encode("ascii") for lbl in domain.split(".")) + b"\x00"
    qtail = struct.pack(">HH", 1, 1)
    return header + qname + qtail


class InternetTrafficEngine:
    def __init__(self) -> None:
        self.running: bool = False
        self._stop_event = threading.Event()
        self._threads: List[threading.Thread] = []
        self._lock = threading.Lock()

        self.interface: str = "enp216s0"
        self.target_bps: float = 50_000_000.0  # Default 50 Mbps target unless raised
        self.enable_upload: bool = True
        self.enable_download: bool = True
        self.enable_web: bool = True
        self.enable_dns: bool = True
        self.download_urls: List[str] = list(DEFAULT_DOWNLOAD_URLS)
        self.upload_url: str = DEFAULT_UPLOAD_URL
        self.probe_host: str = "1.1.1.1"
        self.worker_count: int = 6

        # Live measured state
        self._start_counters: Dict[str, int] = {}
        self._prev_counters: Dict[str, int] = {}
        self._prev_ts: float = 0.0
        self.app_rx_bytes: int = 0
        self.app_tx_bytes: int = 0
        self.completed_requests: int = 0
        self._prev_requests: int = 0
        self.active_connections: int = 0

        # Real RTT / Jitter / Loss measurements (in microseconds)
        self._rtt_samples_us: Deque[float] = deque(maxlen=240)
        self._jitter_us: float = 0.0
        self._last_rtt_us: Optional[float] = None
        self._probes_sent: int = 0
        self._probes_lost: int = 0

    def configure_and_start(
        self,
        interface: str = "enp216s0",
        target_bps: float = 50_000_000.0,
        worker_count: int = 6,
        enable_download: bool = True,
        enable_upload: bool = True,
        enable_web: bool = True,
        enable_dns: bool = True,
        download_urls: Optional[List[str]] = None,
        probe_host: str = "1.1.1.1",
    ) -> None:
        self.stop()
        self.interface = interface or "enp216s0"
        self.target_bps = max(100_000.0, float(target_bps))
        self.worker_count = max(1, min(24, int(worker_count)))
        self.enable_download = enable_download
        self.enable_upload = enable_upload
        self.enable_web = enable_web
        self.enable_dns = enable_dns
        if download_urls:
            self.download_urls = [u for u in download_urls if u.startswith("http")]
        if not self.download_urls:
            self.download_urls = list(DEFAULT_DOWNLOAD_URLS)
        self.probe_host = probe_host or "1.1.1.1"

        now = time.time()
        init_c = _read_iface_counters(self.interface)
        self._start_counters = dict(init_c)
        self._prev_counters = dict(init_c)
        self._prev_ts = now
        self.app_rx_bytes = 0
        self.app_tx_bytes = 0
        self.completed_requests = 0
        self._prev_requests = 0
        self.active_connections = 0
        self._rtt_samples_us.clear()
        self._jitter_us = 0.0
        self._last_rtt_us = None
        self._probes_sent = 0
        self._probes_lost = 0

        self._stop_event.clear()
        self.running = True
        self._threads = []

        # 1. Start Latency / Jitter / Loss Probe Worker
        t_probe = threading.Thread(target=self._probe_worker, daemon=True)
        t_probe.start()
        self._threads.append(t_probe)

        # 2. Start Multi-Connection HTTPS Download Workers
        if self.enable_download:
            dl_workers = max(1, int(math.ceil(self.worker_count * 0.65)))
            for idx in range(dl_workers):
                t = threading.Thread(target=self._download_worker, args=(idx, dl_workers), daemon=True)
                t.start()
                self._threads.append(t)

        # 3. Start HTTPS Upload Workers (so TX throughput to Internet is also exercised)
        if self.enable_upload:
            ul_workers = max(1, int(math.ceil(self.worker_count * 0.35)))
            for idx in range(ul_workers):
                t = threading.Thread(target=self._upload_worker, args=(idx, ul_workers), daemon=True)
                t.start()
                self._threads.append(t)

        # 4. Start Web & DNS Transaction Worker
        if self.enable_web or self.enable_dns:
            t_tx = threading.Thread(target=self._web_and_dns_worker, daemon=True)
            t_tx.start()
            self._threads.append(t_tx)

    def update_target_bps(self, target_bps: float) -> None:
        self.target_bps = max(0.0, float(target_bps))

    def stop(self) -> None:
        self.running = False
        self._stop_event.set()
        for t in self._threads:
            if t.is_alive():
                t.join(timeout=0.4)
        self._threads = []
        self.active_connections = 0

    def _download_worker(self, worker_idx: int, total_dl_workers: int) -> None:
        limits = httpx.Limits(max_keepalive_connections=4, max_connections=8)
        with httpx.Client(verify=False, timeout=10.0, limits=limits, follow_redirects=True) as client:
            while not self._stop_event.is_set() and self.running:
                if self.target_bps <= 1000:
                    time.sleep(0.25)
                    continue
                url = self.download_urls[worker_idx % len(self.download_urls)]
                try:
                    with self._lock:
                        self.active_connections += 1
                    try:
                        with client.stream("GET", url) as resp:
                            with self._lock:
                                self.completed_requests += 1
                            for chunk in resp.iter_bytes(chunk_size=32768):
                                if self._stop_event.is_set() or not self.running:
                                    break
                                n = len(chunk)
                                with self._lock:
                                    self.app_rx_bytes += n
                                # Pace per-worker download rate to match target_bps
                                per_worker_bps = max(50_000.0, (self.target_bps * 0.75) / max(1, total_dl_workers))
                                expected_dt = (n * 8.0) / per_worker_bps
                                if expected_dt > 0.002:
                                    time.sleep(min(0.25, expected_dt * 0.85))
                    finally:
                        with self._lock:
                            self.active_connections = max(0, self.active_connections - 1)
                except Exception:
                    time.sleep(0.3)

    def _upload_worker(self, worker_idx: int, total_ul_workers: int) -> None:
        payload_size = 131072  # 128 KB chunks
        payload = b"SVV-NET-STUDIO-WAN-TEST-" * (payload_size // 24)
        with httpx.Client(verify=False, timeout=10.0) as client:
            while not self._stop_event.is_set() and self.running:
                if self.target_bps <= 1000:
                    time.sleep(0.25)
                    continue
                try:
                    with self._lock:
                        self.active_connections += 1
                    try:
                        t0 = time.perf_counter()
                        resp = client.post(
                            self.upload_url,
                            content=payload,
                            headers={"Content-Type": "application/octet-stream"},
                        )
                        _ = resp.status_code
                        with self._lock:
                            self.app_tx_bytes += len(payload)
                            self.completed_requests += 1
                        per_worker_bps = max(50_000.0, (self.target_bps * 0.25) / max(1, total_ul_workers))
                        expected_dt = (len(payload) * 8.0) / per_worker_bps
                        elapsed = time.perf_counter() - t0
                        if expected_dt > elapsed:
                            time.sleep(min(0.4, expected_dt - elapsed))
                    finally:
                        with self._lock:
                            self.active_connections = max(0, self.active_connections - 1)
                except Exception:
                    time.sleep(0.4)

    def _web_and_dns_worker(self) -> None:
        udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        udp_sock.settimeout(1.0)
        with httpx.Client(verify=False, timeout=5.0) as client:
            while not self._stop_event.is_set() and self.running:
                if self.enable_dns:
                    try:
                        dom = random.choice(DEFAULT_DNS_DOMAINS)
                        srv = random.choice(DEFAULT_DNS_SERVERS)
                        q = _build_dns_query(dom)
                        udp_sock.sendto(q, (srv, 53))
                        data, _ = udp_sock.recvfrom(512)
                        with self._lock:
                            self.app_tx_bytes += len(q)
                            self.app_rx_bytes += len(data)
                            self.completed_requests += 1
                    except Exception:
                        pass
                if self.enable_web:
                    try:
                        u = random.choice(DEFAULT_WEB_URLS)
                        r = client.get(u)
                        with self._lock:
                            self.app_rx_bytes += len(r.content)
                            self.completed_requests += 1
                    except Exception:
                        pass
                time.sleep(0.2)
        udp_sock.close()

    def _probe_worker(self) -> None:
        """Continuously measure real WAN/Gateway RTT, RFC 3550 jitter, and packet loss."""
        while not self._stop_event.is_set() and self.running:
            self._probes_sent += 1
            measured_us: Optional[float] = None
            try:
                res = subprocess.run(
                    ["ping", "-c", "1", "-W", "1", self.probe_host],
                    capture_output=True,
                    text=True,
                    timeout=2,
                )
                if res.returncode == 0:
                    m = re.search(r"time=([\d.]+)\s*ms", res.stdout)
                    if m:
                        measured_us = float(m.group(1)) * 1000.0
            except Exception:
                measured_us = None

            # Fallback to TCP connect RTT on 1.1.1.1:443 if ICMP is filtered
            if measured_us is None:
                try:
                    t0 = time.perf_counter()
                    s = socket.create_connection((self.probe_host, 443), timeout=1.0)
                    measured_us = (time.perf_counter() - t0) * 1_000_000.0
                    s.close()
                except Exception:
                    measured_us = None

            with self._lock:
                if measured_us is not None:
                    self._rtt_samples_us.append(measured_us)
                    if self._last_rtt_us is not None:
                        diff = abs(measured_us - self._last_rtt_us)
                        # RFC 3550 smoothed inter-arrival jitter estimator
                        self._jitter_us += (diff - self._jitter_us) / 16.0
                    self._last_rtt_us = measured_us
                else:
                    self._probes_lost += 1

            time.sleep(0.5)

    def sample_metrics(self) -> Dict[str, Any]:
        """Compute instantaneous and cumulative metrics from real OS NIC counters & live RTT probes."""
        now = time.time()
        dt = max(0.05, now - self._prev_ts)
        curr = _read_iface_counters(self.interface)

        d_tx_bytes = max(0, curr["tx_bytes"] - self._prev_counters.get("tx_bytes", curr["tx_bytes"]))
        d_rx_bytes = max(0, curr["rx_bytes"] - self._prev_counters.get("rx_bytes", curr["rx_bytes"]))
        d_tx_pkts = max(0, curr["tx_packets"] - self._prev_counters.get("tx_packets", curr["tx_packets"]))
        d_rx_pkts = max(0, curr["rx_packets"] - self._prev_counters.get("rx_packets", curr["rx_packets"]))

        tot_tx_pkts = max(0, curr["tx_packets"] - self._start_counters.get("tx_packets", curr["tx_packets"]))
        tot_rx_pkts = max(0, curr["rx_packets"] - self._start_counters.get("rx_packets", curr["rx_packets"]))
        nic_drops = max(0, curr["drops"] - self._start_counters.get("drops", curr["drops"]))

        self._prev_counters = curr
        self._prev_ts = now

        with self._lock:
            rtts = sorted(self._rtt_samples_us)
            jitter = self._jitter_us
            sent_p = self._probes_sent
            lost_p = self._probes_lost
            reqs = self.completed_requests
            d_reqs = max(0, reqs - self._prev_requests)
            self._prev_requests = reqs
            act_conn = self.active_connections

        if rtts:
            lat_min = rtts[0]
            lat_avg = sum(rtts) / len(rtts)
            lat_max = rtts[-1]
            p95_idx = min(len(rtts) - 1, int(math.floor(len(rtts) * 0.95)))
            p99_idx = min(len(rtts) - 1, int(math.floor(len(rtts) * 0.99)))
            p95 = rtts[p95_idx]
            p99 = rtts[p99_idx]
        else:
            lat_min = lat_avg = lat_max = p95 = p99 = 0.0

        probe_loss_pct = ((lost_p / sent_p) * 100.0) if sent_p > 0 else 0.0

        return {
            "tx_bps": (d_tx_bytes * 8.0) / dt,
            "rx_bps": (d_rx_bytes * 8.0) / dt,
            "tx_pps": d_tx_pkts / dt,
            "rx_pps": d_rx_pkts / dt,
            "tx_packets": tot_tx_pkts,
            "rx_packets": tot_rx_pkts,
            "dropped_packets": nic_drops + lost_p,
            "drop_pct": probe_loss_pct,
            "lat_min_us": lat_min,
            "lat_avg_us": lat_avg,
            "lat_max_us": lat_max,
            "p95_lat_us": p95,
            "p99_lat_us": p99,
            "jitter_us": jitter,
            "active_flows": act_conn,
            "cps": d_reqs / dt,
            "telemetry_source": f"Live Internet/WAN ({self.interface} -> {self.probe_host})",
        }


internet_engine = InternetTrafficEngine()
