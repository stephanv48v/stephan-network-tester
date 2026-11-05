"""
Enterprise Multi-Page Light-Mode PDF, CSV, and JSON Report Generator
for Cisco TRex Network Test Studio (Dell PowerEdge R640 + UniFi EFG).

Visual Design System:
  - Matches Cisco TRex + UniFi Enterprise Performance Report specification:
    * Deep Navy (#0F1D31) cover hero & content page header banners
    * Clean white (#FFFFFF) KPI cards with vertical colored accent bars (#1769D2, #15803D, #D97706, #DC2626)
    * Dark Navy (#0F1D31) table headers with alternating #FFFFFF / #F8FAFC rows
    * Crisp light-mode Matplotlib charts (Throughput TX/RX/Target, Latency/P99, Traffic Mix Donut, TRex-UniFi Correlation)
    * Exact page X / Y footer numbering via two-pass NumberedCanvas
  - Strict Engineering Integrity:
    * Pass/Fail verdicts appear ONLY when explicit acceptance thresholds were configured for the run.
    * Synthetic application names are explicitly documented as workload approximations, not authenticated commercial logins.
    * Hardware/topology limitations and unavailable UniFi/SNMP metrics are reported transparently.
"""
import csv
import datetime
import io
import json
from typing import Any, Dict, List, Optional

from xml.sax.saxutils import escape as _esc

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
# NOTE: charts use fig.tight_layout()/fig.savefig() (not plt.*), because plt.* act on pyplot's global
# "current figure", which is shared across the asyncio.to_thread workers rendering concurrent exports.

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.platypus import (
    Image,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from profiles import WORKLOAD_MAP, normalize_mix_to_100


NAVY = colors.HexColor("#0F1D31")
NAVY_MID = colors.HexColor("#142338")
BLUE = colors.HexColor("#1769D2")
BLUE_SEC = colors.HexColor("#2585E6")
TEXT_MAIN = colors.HexColor("#17243A")
TEXT_MUTED = colors.HexColor("#64748B")
BORDER = colors.HexColor("#E2E8F0")
ROW_ALT = colors.HexColor("#F8FAFC")
GREEN = colors.HexColor("#15803D")
AMBER = colors.HexColor("#D97706")
RED = colors.HexColor("#DC2626")


def _fmt_bps(bps: Optional[float]) -> str:
    if bps is None:
        return "Unavailable"
    val = float(bps)
    if val >= 1e9:
        return f"{val / 1e9:.2f} Gbps"
    if val >= 1e6:
        return f"{val / 1e6:.2f} Mbps"
    if val >= 1e3:
        return f"{val / 1e3:.1f} Kbps"
    return f"{val:.0f} bps"


def _fmt_pps(pps: Optional[float]) -> str:
    if pps is None:
        return "Unavailable"
    val = float(pps)
    if val >= 1e6:
        return f"{val / 1e6:.2f} Mpps"
    if val >= 1e3:
        return f"{val / 1e3:.1f} Kpps"
    return f"{val:.0f} pps"


def _fmt_duration(seconds: int) -> str:
    sec = max(0, int(seconds or 0))
    if sec < 60:
        return f"{sec} seconds"
    mins, rem = divmod(sec, 60)
    if mins < 60:
        return f"{mins} min {rem} sec" if rem else f"{mins} minutes"
    hrs, mins = divmod(mins, 60)
    return f"{hrs}h {mins}m"


def _ensure_run_summary(run: Dict[str, Any]) -> Dict[str, Any]:
    summary = dict(run.get("summary") or {})
    samples = run.get("samples") or []
    if not summary and samples:
        lat_vals = [float(s.get("lat_avg_us") or 0) for s in samples if float(s.get("lat_avg_us") or 0) > 0]
        p99_vals = [float(s.get("p99_lat_us") or 0) for s in samples if float(s.get("p99_lat_us") or 0) > 0]
        jit_vals = [float(s.get("jitter_us") or 0) for s in samples if float(s.get("jitter_us") or 0) > 0]
        summary = {
            "sample_count": len(samples),
            "actual_duration_sec": int(samples[-1].get("elapsed_sec", len(samples))),
            "max_tx_bps": max(float(s.get("tx_bps") or 0) for s in samples),
            "avg_tx_bps": sum(float(s.get("tx_bps") or 0) for s in samples) / len(samples),
            "max_rx_bps": max(float(s.get("rx_bps") or 0) for s in samples),
            "avg_rx_bps": sum(float(s.get("rx_bps") or 0) for s in samples) / len(samples),
            "max_tx_pps": max(float(s.get("tx_pps") or 0) for s in samples),
            "avg_tx_pps": sum(float(s.get("tx_pps") or 0) for s in samples) / len(samples),
            "total_tx_packets": int(samples[-1].get("tx_packets") or 0),
            "total_rx_packets": int(samples[-1].get("rx_packets") or 0),
            "total_dropped_packets": int(samples[-1].get("dropped_packets") or 0),
            "drop_pct": float(samples[-1].get("drop_pct") or 0.0),
            "lat_avg_us": (sum(lat_vals) / len(lat_vals)) if lat_vals else 0.0,
            "p99_lat_us": max(p99_vals) if p99_vals else 0.0,
            "jitter_avg_us": (sum(jit_vals) / len(jit_vals)) if jit_vals else 0.0,
            "peak_active_flows": max(int(s.get("active_flows") or 0) for s in samples),
            "peak_established_sessions": max(int(s.get("established_sessions") or 0) for s in samples),
            "peak_cps": max(float(s.get("cps") or 0) for s in samples),
            "thresholds_configured": False,
            "verdict": "RECORDED",
        }
    return summary


# ---------------------------------------------------------------------------
# CSV & JSON Exports
# ---------------------------------------------------------------------------
def generate_csv_bytes(run: Dict[str, Any]) -> bytes:
    """Export all 1-second time-series telemetry samples for a test run as a clean CSV."""
    buf = io.StringIO()
    writer = csv.writer(buf)
    summary = _ensure_run_summary(run)
    writer.writerow([
        "# Cisco TRex Network Test Studio - Time-Series Telemetry Export",
        f"Run ID: {run.get('id')}",
        f"Test Name: {run.get('name')}",
        f"Engine: {run.get('traffic_engine', 'trex_astf')}",
        f"Simulated Users: {run.get('simulated_users')}",
        f"Outcome: {summary.get('verdict', run.get('verdict', 'COMPLETED'))}",
    ])
    writer.writerow([
        "elapsed_sec",
        "timestamp_iso",
        "phase",
        "rate_pct",
        "target_bps",
        "tx_bps",
        "rx_bps",
        "tx_mbps",
        "rx_mbps",
        "tx_pps",
        "rx_pps",
        "tx_packets",
        "rx_packets",
        "dropped_packets",
        "drop_pct",
        "active_flows",
        "established_sessions",
        "emulated_clients",
        "cps",
        "tcp_connects",
        "tcp_drops",
        "tcp_retransmits",
        "lat_min_us",
        "lat_avg_us",
        "p95_lat_us",
        "p99_lat_us",
        "lat_max_us",
        "jitter_us",
        "mos_score",
        "r640_cpu_pct",
        "r640_ram_pct",
        "unifi_gw_cpu_pct",
        "unifi_gw_mem_pct",
        "unifi_wan_rx_bps",
        "unifi_wan_tx_bps",
        "snmp_in_bps",
        "snmp_out_bps",
        "telemetry_source",
    ])
    for s in run.get("samples") or []:
        ts_iso = datetime.datetime.fromtimestamp(float(s.get("ts", 0))).isoformat()
        writer.writerow([
            s.get("elapsed_sec", 0),
            ts_iso,
            s.get("phase_name", "steady"),
            round(float(s.get("rate_pct") or 0), 2),
            round(float(s.get("target_bps") or 0), 2),
            round(float(s.get("tx_bps") or 0), 2),
            round(float(s.get("rx_bps") or 0), 2),
            round(float(s.get("tx_bps") or 0) / 1e6, 3),
            round(float(s.get("rx_bps") or 0) / 1e6, 3),
            round(float(s.get("tx_pps") or 0), 2),
            round(float(s.get("rx_pps") or 0), 2),
            int(s.get("tx_packets") or 0),
            int(s.get("rx_packets") or 0),
            int(s.get("dropped_packets") or 0),
            round(float(s.get("drop_pct") or 0), 4),
            int(s.get("active_flows") or 0),
            int(s.get("established_sessions") or 0),
            int(s.get("emulated_clients") or 0),
            round(float(s.get("cps") or 0), 2),
            int(s.get("tcp_connects") or 0),
            int(s.get("tcp_drops") or 0),
            int(s.get("tcp_retransmits") or 0),
            round(float(s.get("lat_min_us") or 0), 2),
            round(float(s.get("lat_avg_us") or 0), 2),
            round(float(s.get("p95_lat_us") or 0), 2),
            round(float(s.get("p99_lat_us") or 0), 2),
            round(float(s.get("lat_max_us") or 0), 2),
            round(float(s.get("jitter_us") or 0), 2),
            round(float(s.get("mos_score") or 0), 2),
            round(float(s.get("cpu_pct") or 0), 1),
            round(float(s.get("ram_pct") or 0), 1),
            s.get("unifi_gw_cpu", ""),
            s.get("unifi_gw_mem", ""),
            s.get("unifi_wan_rx_bps", ""),
            s.get("unifi_wan_tx_bps", ""),
            s.get("snmp_in_bps", ""),
            s.get("snmp_out_bps", ""),
            s.get("telemetry_source", ""),
        ])
    return buf.getvalue().encode("utf-8")


def generate_json_bytes(run: Dict[str, Any]) -> bytes:
    """Export immutable structured JSON run archive."""
    payload = {
        "schema_version": "2.0",
        "exported_at_iso": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "appliance": "Cisco TRex Network Test Studio — Dell PowerEdge R640",
        "run_metadata": {
            "id": run.get("id"),
            "name": run.get("name"),
            "profile_id": run.get("profile_id"),
            "profile_name": run.get("profile_name"),
            "traffic_engine": run.get("traffic_engine"),
            "test_mode": run.get("test_mode"),
            "status": run.get("status"),
            "verdict": run.get("verdict"),
            "started_at": run.get("started_at"),
            "ended_at": run.get("ended_at"),
            "duration_sec": run.get("duration_sec"),
            "simulated_users": run.get("simulated_users"),
            "simulated_devices": run.get("simulated_devices"),
            "operator_name": run.get("operator_name"),
            "client_name": run.get("client_name"),
            "dut_name": run.get("dut_name"),
        },
        "configuration": run.get("config") or {},
        "thresholds": run.get("thresholds"),
        "summary": _ensure_run_summary(run),
        "telemetry_samples": run.get("samples") or [],
        "unifi_samples": run.get("unifi_samples") or [],
        "snmp_samples": run.get("snmp_samples") or [],
    }
    return json.dumps(payload, indent=2).encode("utf-8")


# ---------------------------------------------------------------------------
# Light-Mode Enterprise Matplotlib Charts
# ---------------------------------------------------------------------------
def _style_light_axes(ax: Any) -> None:
    ax.set_facecolor("#FFFFFF")
    ax.tick_params(colors="#64748B", labelsize=8)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color("#CBD5E1")
    ax.spines["bottom"].set_color("#CBD5E1")
    ax.grid(True, color="#E2E8F0", linestyle="-", linewidth=0.6, alpha=0.85)


def _chart_throughput(samples: List[Dict[str, Any]], target_bps: float) -> io.BytesIO:
    fig, ax = plt.subplots(figsize=(7.1, 2.75), dpi=160)
    fig.patch.set_facecolor("#FFFFFF")
    _style_light_axes(ax)

    use_gbps = max([target_bps] + [float(s.get("tx_bps") or 0) for s in samples]) >= 800_000_000
    div = 1e9 if use_gbps else 1e6
    unit = "Gbps" if use_gbps else "Mbps"

    if samples:
        xs = [float(s.get("elapsed_sec", i)) for i, s in enumerate(samples)]
        tx = [float(s.get("tx_bps") or 0) / div for s in samples]
        rx = [float(s.get("rx_bps") or 0) / div for s in samples]
        tgt = [(float(s.get("target_bps") or target_bps)) / div for s in samples]
    else:
        xs, tx, rx, tgt = [0, 1], [0, 0], [0, 0], [target_bps / div, target_bps / div]

    ax.plot(xs, tx, color="#1769D2", linewidth=2.0, label=f"TRex TX ({unit})")
    ax.plot(xs, rx, color="#0EA5E9", linewidth=1.7, linestyle="-", label=f"TRex RX ({unit})")
    if target_bps > 0:
        ax.plot(xs, tgt, color="#94A3B8", linewidth=1.1, linestyle="--", label=f"Configured Target ({unit})")
    ax.fill_between(xs, tx, color="#1769D2", alpha=0.08)

    ax.set_ylabel(unit, color="#334155", fontsize=8.5, fontweight="bold")
    ax.set_xlabel("Elapsed test time (seconds)", color="#64748B", fontsize=8)
    ax.set_ylim(bottom=0)
    ax.legend(loc="lower right", frameon=True, facecolor="#FFFFFF", edgecolor="#E2E8F0", fontsize=7.5)
    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", facecolor="#FFFFFF")
    plt.close(fig)
    buf.seek(0)
    return buf


def _chart_latency(samples: List[Dict[str, Any]]) -> io.BytesIO:
    fig, ax = plt.subplots(figsize=(7.1, 2.65), dpi=160)
    fig.patch.set_facecolor("#FFFFFF")
    _style_light_axes(ax)

    if samples:
        xs = [float(s.get("elapsed_sec", i)) for i, s in enumerate(samples)]
        avg_l = [float(s.get("lat_avg_us") or 0) for s in samples]
        p99_l = [float(s.get("p99_lat_us") or s.get("lat_max_us") or 0) for s in samples]
        jit_l = [float(s.get("jitter_us") or 0) for s in samples]
    else:
        xs, avg_l, p99_l, jit_l = [0, 1], [0, 0], [0, 0], [0, 0]

    ax.plot(xs, avg_l, color="#1769D2", linewidth=1.9, label="Average latency (us)")
    if any(v > 0 for v in p99_l):
        ax.plot(xs, p99_l, color="#D97706", linewidth=1.3, linestyle="--", label="P99 tail latency (us)")
    if any(v > 0 for v in jit_l):
        ax.plot(xs, jit_l, color="#0D9488", linewidth=1.2, linestyle=":", label="Jitter (us)")
    ax.fill_between(xs, avg_l, color="#1769D2", alpha=0.08)

    ax.set_ylabel("Microseconds (us)", color="#334155", fontsize=8.5, fontweight="bold")
    ax.set_xlabel("Elapsed test time (seconds)", color="#64748B", fontsize=8)
    ax.set_ylim(bottom=0)
    ax.legend(loc="upper right", frameon=True, facecolor="#FFFFFF", edgecolor="#E2E8F0", fontsize=7.5)
    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", facecolor="#FFFFFF")
    plt.close(fig)
    buf.seek(0)
    return buf


def _chart_workload_donut(mix: Dict[str, Any]) -> io.BytesIO:
    norm = normalize_mix_to_100(mix)
    items = sorted(norm.items(), key=lambda x: x[1], reverse=True)
    top_items = items[:6]
    if len(items) > 6:
        other_sum = round(sum(v for _, v in items[6:]), 1)
        if other_sum > 0:
            top_items.append(("other_combined", other_sum))

    labels, sizes, clrs = [], [], []
    palette_fallback = ["#1769D2", "#2585E6", "#6366F1", "#14B8A6", "#10B981", "#F59E0B", "#94A3B8"]
    for idx, (k, val) in enumerate(top_items):
        meta = WORKLOAD_MAP.get(k)
        lbl = meta["short_name"] if meta else "Other Workloads"
        clr = meta["color"] if meta else palette_fallback[idx % len(palette_fallback)]
        labels.append(f"{lbl}  ({val:.0f}%)")
        sizes.append(max(0.1, float(val)))
        clrs.append(clr)

    fig, (ax_pie, ax_leg) = plt.subplots(1, 2, figsize=(7.0, 2.7), dpi=160, gridspec_kw={"width_ratios": [1.1, 1.3]})
    fig.patch.set_facecolor("#FFFFFF")

    wedges, _ = ax_pie.pie(
        sizes,
        colors=clrs,
        startangle=90,
        counterclock=False,
        wedgeprops={"width": 0.36, "edgecolor": "#FFFFFF", "linewidth": 2},
    )
    ax_pie.text(0, 0.06, "100%", ha="center", va="center", fontsize=12, fontweight="bold", color="#0F1D31")
    ax_pie.text(0, -0.14, "Traffic Mix", ha="center", va="center", fontsize=8.5, color="#64748B")
    ax_pie.axis("equal")

    ax_leg.axis("off")
    ax_leg.legend(wedges, labels, loc="center left", frameon=False, fontsize=8.5, labelcolor="#17243A")
    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", facecolor="#FFFFFF")
    plt.close(fig)
    buf.seek(0)
    return buf


def _chart_correlation(samples: List[Dict[str, Any]]) -> io.BytesIO:
    fig, ax1 = plt.subplots(figsize=(7.1, 2.75), dpi=160)
    fig.patch.set_facecolor("#FFFFFF")
    _style_light_axes(ax1)

    if samples:
        xs = [float(s.get("elapsed_sec", i)) for i, s in enumerate(samples)]
        max_bps = max((float(s.get("tx_bps") or 0) for s in samples), default=0)
        div = 1e9 if max_bps >= 800_000_000 else 1e6
        unit = "Gbps" if div == 1e9 else "Mbps"
        tx = [float(s.get("tx_bps") or 0) / div for s in samples]
        gw_cpu = [float(s["unifi_gw_cpu"]) if s.get("unifi_gw_cpu") is not None else None for s in samples]
        r640_cpu = [float(s.get("cpu_pct") or 0) for s in samples]
    else:
        xs, tx, gw_cpu, r640_cpu, unit = [0, 1], [0, 0], [None, None], [0, 0], "Mbps"

    l1 = ax1.plot(xs, tx, color="#1769D2", linewidth=2.0, label=f"TRex TX ({unit})")
    ax1.set_ylabel(f"Throughput ({unit})", color="#1769D2", fontsize=8.5, fontweight="bold")
    ax1.set_xlabel("Elapsed test time (seconds)", color="#64748B", fontsize=8)
    ax1.set_ylim(bottom=0)

    ax2 = ax1.twinx()
    ax2.spines["top"].set_visible(False)
    ax2.spines["left"].set_visible(False)
    ax2.spines["right"].set_color("#CBD5E1")
    ax2.tick_params(colors="#64748B", labelsize=8)
    ax2.set_ylim(0, 105)

    lines = list(l1)
    if any(v is not None for v in gw_cpu):
        xs_u = [x for x, v in zip(xs, gw_cpu) if v is not None]
        vs_u = [v for v in gw_cpu if v is not None]
        l2 = ax2.plot(xs_u, vs_u, color="#D97706", linewidth=1.8, label="UniFi EFG CPU (%)")
        lines.extend(l2)
        ax2.set_ylabel("EFG CPU Utilisation (%)", color="#D97706", fontsize=8.5, fontweight="bold")
    else:
        l2 = ax2.plot(xs, r640_cpu, color="#64748B", linewidth=1.5, linestyle="--", label="R640 Generator CPU (%)")
        lines.extend(l2)
        ax2.set_ylabel("R640 CPU (%)", color="#64748B", fontsize=8.5, fontweight="bold")

    labels = [ln.get_label() for ln in lines]
    ax1.legend(lines, labels, loc="lower right", frameon=True, facecolor="#FFFFFF", edgecolor="#E2E8F0", fontsize=7.5)
    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", facecolor="#FFFFFF")
    plt.close(fig)
    buf.seek(0)
    return buf


# ---------------------------------------------------------------------------
# Reusable PDF Building Blocks (KPI Cards, Callouts, NumberedCanvas)
# ---------------------------------------------------------------------------
class _ReportNumberedCanvas(canvas.Canvas):
    """Two-pass canvas rendering the dark navy header banner and exact 'XX / YY' page numbers."""

    def __init__(self, *args, run_label: str = "LIVE RECORDED RUN", footer_left: str = "", **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states: List[Dict[str, Any]] = []
        self._run_label = run_label
        self._footer_left = footer_left or "CISCO TRex + UniFi | RECORDED NETWORK PERFORMANCE REPORT"

    def showPage(self) -> None:
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self) -> None:
        total_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self._draw_page_chrome(total_pages)
            super().showPage()
        super().save()

    def _draw_page_chrome(self, total_pages: int) -> None:
        page_num = self._pageNumber
        w, h = A4
        if page_num == 1:
            # Cover Page Dark Navy Top Hero Block
            hero_h = 84 * mm
            self.setFillColor(NAVY)
            self.rect(0, h - hero_h, w, hero_h, stroke=0, fill=1)

            # Pill Badge
            self.setFillColor(BLUE)
            self.roundRect(16 * mm, h - 28 * mm, 54 * mm, 7.5 * mm, 2 * mm, stroke=0, fill=1)
            self.setFillColor(colors.white)
            self.setFont("Helvetica-Bold", 7.5)
            self.drawString(20 * mm, h - 25.4 * mm, self._run_label[:28])

            # Cover Title
            self.setFont("Helvetica-Bold", 26)
            self.drawString(16 * mm, h - 44 * mm, "NETWORK")
            self.drawString(16 * mm, h - 55 * mm, "PERFORMANCE")
            self.setFont("Helvetica-Bold", 21)
            self.setFillColor(colors.HexColor("#DBEAFE"))
            self.drawString(16 * mm, h - 65 * mm, "TEST REPORT")

            # Subtle Cover Footer
            self.setStrokeColor(BORDER)
            self.setLineWidth(0.6)
            self.line(16 * mm, 16 * mm, w - 16 * mm, 16 * mm)
            self.setFillColor(TEXT_MUTED)
            self.setFont("Helvetica", 7.5)
            self.drawString(16 * mm, 11 * mm, self._footer_left)
            self.drawRightString(w - 16 * mm, 11 * mm, f"01 / {total_pages:02d}")
            return

        # Content Pages Top Navy Banner
        banner_h = 24 * mm
        self.setFillColor(NAVY)
        self.rect(0, h - banner_h, w, banner_h, stroke=0, fill=1)
        self.setFillColor(colors.white)
        self.setFont("Helvetica-Bold", 10.5)
        self.drawString(16 * mm, h - 10.5 * mm, "NETWORK PERFORMANCE REPORT")
        self.setFillColor(colors.HexColor("#94A3B8"))
        self.setFont("Helvetica", 8)
        self.drawString(16 * mm, h - 16.5 * mm, "Cisco TRex traffic generation  /  UniFi infrastructure telemetry")
        self.setFillColor(colors.HexColor("#DBEAFE"))
        self.setFont("Helvetica-Bold", 8)
        self.drawRightString(w - 16 * mm, h - 13.5 * mm, self._run_label)

        # Content Pages Footer
        self.setStrokeColor(BORDER)
        self.setLineWidth(0.6)
        self.line(16 * mm, 15 * mm, w - 16 * mm, 15 * mm)
        self.setFillColor(TEXT_MUTED)
        self.setFont("Helvetica", 7.5)
        self.drawString(16 * mm, 10.5 * mm, self._footer_left)
        self.drawRightString(w - 16 * mm, 10.5 * mm, f"{page_num:02d} / {total_pages:02d}")


def _kpi_card_row(cards: List[Dict[str, Any]], total_width_mm: float = 178.0) -> Table:
    """Build a 3-column row of white KPI cards with colored vertical pill accents."""
    n = len(cards)
    gap_mm = 4.0
    card_w = (total_width_mm - gap_mm * (n - 1)) / n
    styles = getSampleStyleSheet()

    cell_tables = []
    for c in cards:
        accent = c.get("accent", "#1769D2")
        lbl = _esc(str(c.get("label", "")).upper())
        val = _esc(str(c.get("value", "—")))
        sub = _esc(str(c.get("sub", "")))

        p = Paragraph(
            f"<font name='Helvetica-Bold' size='7.5' color='#64748B'>{lbl}</font><br/>"
            f"<font name='Helvetica-Bold' size='15' color='#0F1D31'>{val}</font><br/>"
            f"<font name='Helvetica' size='7.5' color='#64748B'>{sub}</font>",
            ParagraphStyle("kpicell", parent=styles["Normal"], leading=14),
        )
        inner = Table([["", p]], colWidths=[1.6 * mm, (card_w - 4.0) * mm])
        inner.setStyle(
            TableStyle([
                ("BACKGROUND", (0, 0), (0, 0), colors.HexColor(accent)),
                ("BACKGROUND", (1, 0), (1, 0), colors.white),
                ("LEFTPADDING", (0, 0), (0, 0), 0),
                ("RIGHTPADDING", (0, 0), (0, 0), 0),
                ("LEFTPADDING", (1, 0), (1, 0), 7),
                ("RIGHTPADDING", (1, 0), (1, 0), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                ("BOX", (0, 0), (-1, -1), 0.7, BORDER),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ])
        )
        cell_tables.append(inner)

    col_widths = []
    row_items = []
    for idx, tbl in enumerate(cell_tables):
        row_items.append(tbl)
        col_widths.append(card_w * mm)
        if idx < n - 1:
            row_items.append("")
            col_widths.append(gap_mm * mm)

    outer = Table([row_items], colWidths=col_widths)
    outer.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0), ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]))
    return outer


def _styled_table(rows: List[List[Any]], col_widths_mm: List[float]) -> Table:
    styles = getSampleStyleSheet()
    cell_style = ParagraphStyle("tblc", parent=styles["Normal"], fontName="Helvetica", fontSize=8.3, leading=11.5, textColor=TEXT_MAIN)
    hdr_style = ParagraphStyle("tblh", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=8.3, leading=11.5, textColor=colors.white)

    formatted_rows = []
    for r_idx, row in enumerate(rows):
        formatted_rows.append([
            Paragraph(_esc(str(col)), hdr_style if r_idx == 0 else cell_style) if not isinstance(col, Paragraph) else col
            for col in row
        ])

    tbl = Table(formatted_rows, colWidths=[w * mm for w in col_widths_mm])
    tbl.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), NAVY),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, ROW_ALT]),
            ("LINEBELOW", (0, 1), (-1, -1), 0.5, BORDER),
            ("BOX", (0, 0), (-1, -1), 0.6, BORDER),
            ("TOPPADDING", (0, 0), (-1, -1), 6.5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6.5),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ])
    )
    return tbl


def _callout_box(title: str, body: str, tone: str = "info") -> Table:
    palettes = {
        "info": ("#EFF6FF", "#BFDBFE", "#1D4ED8", "#1E3A8A"),
        "pass": ("#ECFDF5", "#A7F3D0", "#15803D", "#065F46"),
        "fail": ("#FEF2F2", "#FECACA", "#DC2626", "#991B1B"),
        "warn": ("#FFFBEB", "#FDE68A", "#B45309", "#92400E"),
    }
    bg, brd, t_clr, b_clr = palettes.get(tone, palettes["info"])
    styles = getSampleStyleSheet()
    p = Paragraph(
        f"<font name='Helvetica-Bold' size='8.5' color='{t_clr}'>{_esc(str(title))}</font><br/>"
        f"<font name='Helvetica' size='8.3' color='{b_clr}'>{_esc(str(body))}</font>",
        ParagraphStyle("callout", parent=styles["Normal"], leading=12.5),
    )
    t = Table([[p]], colWidths=[178 * mm])
    t.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(bg)),
            ("BOX", (0, 0), (-1, -1), 0.7, colors.HexColor(brd)),
            ("TOPPADDING", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ("LEFTPADDING", (0, 0), (-1, -1), 10),
            ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ])
    )
    return t


def _chart_card(title: str, img_buf: io.BytesIO, width_mm: float = 174.0, height_mm: float = 67.0) -> Table:
    styles = getSampleStyleSheet()
    hdr = Paragraph(f"<font name='Helvetica-Bold' size='9.5' color='#0F1D31'>{title}</font>", styles["Normal"])
    img = Image(img_buf, width=width_mm * mm, height=height_mm * mm)
    t = Table([[hdr], [img]], colWidths=[178 * mm])
    t.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.white),
            ("BOX", (0, 0), (-1, -1), 0.7, BORDER),
            ("TOPPADDING", (0, 0), (0, 0), 8),
            ("LEFTPADDING", (0, 0), (0, 0), 10),
            ("BOTTOMPADDING", (1, 0), (1, 0), 6),
            ("ALIGN", (0, 1), (0, 1), "CENTER"),
        ])
    )
    return t


# ---------------------------------------------------------------------------
# Full 9-Page Technical & 3-Page Executive PDF Generator
# ---------------------------------------------------------------------------
def generate_pdf_bytes(
    run: Dict[str, Any],
    report_type: str = "technical",
    custom_title: Optional[str] = None,
    custom_client: Optional[str] = None,
) -> bytes:
    """
    Generate client-ready multi-page Light-Mode PDF Report.
    report_type: 'technical' (full 9-page engineering report) | 'executive' (3-page executive summary).
    """
    buf = io.BytesIO()
    summary = _ensure_run_summary(run)
    cfg = run.get("config") or {}
    samples = run.get("samples") or []
    unifi_samples = run.get("unifi_samples") or []
    snmp_samples = run.get("snmp_samples") or []

    run_id = run.get("id", 0)
    started_dt = datetime.datetime.fromtimestamp(float(run.get("started_at") or datetime.datetime.now().timestamp()))
    project_name = custom_client or run.get("client_name") or cfg.get("client_name") or "Enterprise Network Performance Validation"
    dut_name = run.get("dut_name") or cfg.get("dut_name") or "UniFi Enterprise Fortress Gateway (EFG)"
    operator_name = run.get("operator_name") or cfg.get("operator_name") or "Stephan Van Vuuren"
    engine_code = str(run.get("traffic_engine") or cfg.get("traffic_engine") or "trex_astf")
    engine_label = {
        "trex_astf": "Cisco TRex v3.04 ASTF (Stateful TCP/UDP)",
        "trex_stl": "Cisco TRex v3.04 STL (Stateless DPDK)",
        "internet_wan": "Live Internet / WAN Multi-Worker Engine",
        "hybrid": "Hybrid Cisco TRex + Live Internet/WAN",
    }.get(engine_code, engine_code)

    thresholds_configured = bool(summary.get("thresholds_configured"))
    verdict = str(summary.get("verdict") or run.get("verdict") or "COMPLETED").upper()
    if not thresholds_configured and verdict in ("PASS", "RECORDED"):
        verdict = "COMPLETED"

    target_bps = float(cfg.get("base_target_bps") or cfg.get("target_bps") or (float(run.get("target_rate_pct") or 50) / 100.0 * 10e9))
    avg_tx_bps = float(summary.get("avg_tx_bps") or 0.0)
    avg_rx_bps = float(summary.get("avg_rx_bps") or 0.0)
    max_tx_bps = float(summary.get("max_tx_bps") or 0.0)
    max_rx_bps = float(summary.get("max_rx_bps") or 0.0)
    drop_pct = float(summary.get("drop_pct") or 0.0)
    lat_avg = float(summary.get("lat_avg_us") or 0.0)
    p95_lat = float(summary.get("p95_lat_us") or 0.0)
    p99_lat = float(summary.get("p99_lat_us") or 0.0)
    jitter_avg = float(summary.get("jitter_avg_us") or 0.0)
    sim_users = int(run.get("simulated_users") or 0)
    emulated_ips = int(summary.get("emulated_client_ips") or cfg.get("emulated_client_ips") or sim_users)
    peak_flows = int(summary.get("peak_active_flows") or 0)
    peak_est = int(summary.get("peak_established_sessions") or 0)
    peak_cps = float(summary.get("peak_cps") or 0.0)

    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=16 * mm,
        rightMargin=16 * mm,
        topMargin=30 * mm,
        bottomMargin=20 * mm,
        title=custom_title or f"Cisco TRex Network Performance Report — Run #{run_id}",
    )

    styles = getSampleStyleSheet()
    h1_style = ParagraphStyle("PageH1", parent=styles["Heading1"], fontName="Helvetica-Bold", fontSize=18, leading=22, textColor=NAVY, spaceAfter=2)
    sub_style = ParagraphStyle("PageSub", parent=styles["Normal"], fontName="Helvetica", fontSize=9.2, leading=13, textColor=TEXT_MUTED, spaceAfter=10)
    sec_style = ParagraphStyle("SecH2", parent=styles["Heading2"], fontName="Helvetica-Bold", fontSize=11, leading=15, textColor=NAVY, spaceBefore=9, spaceAfter=5)
    body_style = ParagraphStyle("BodyP", parent=styles["Normal"], fontName="Helvetica", fontSize=8.8, leading=13.5, textColor=TEXT_MAIN, spaceAfter=6)
    meta_lbl_style = ParagraphStyle("MetaLbl", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=7.5, leading=10, textColor=TEXT_MUTED)
    meta_val_style = ParagraphStyle("MetaVal", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=10.5, leading=14, textColor=NAVY, spaceAfter=8)

    story: List[Any] = []

    # =========================================================================
    # PAGE 1: COVER PAGE
    # =========================================================================
    story.append(Spacer(1, 60 * mm))
    banner_title = custom_title or f"Cisco TRex + {dut_name}"
    banner_sub = f"{sim_users:,} simulated enterprise users  |  Target {_fmt_bps(target_bps)}  |  {run.get('profile_name', 'Enterprise Mix')}"
    cover_card = Table(
        [[Paragraph(
            f"<font name='Helvetica-Bold' size='12.5' color='#0F1D31'>{_esc(str(banner_title))}</font><br/>"
            f"<font name='Helvetica' size='9.2' color='#64748B'>{_esc(str(banner_sub))}</font>",
            ParagraphStyle("covb", parent=styles["Normal"], leading=16),
        )]],
        colWidths=[178 * mm],
    )
    cover_card.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F8FAFC")),
        ("BOX", (0, 0), (-1, -1), 0.8, BORDER),
        ("TOPPADDING", (0, 0), (-1, -1), 12),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
        ("LEFTPADDING", (0, 0), (-1, -1), 12),
        ("RIGHTPADDING", (0, 0), (-1, -1), 12),
    ]))
    story.append(cover_card)
    story.append(Spacer(1, 9 * mm))

    cover_fields = [
        ("PROJECT", project_name),
        ("DEVICE UNDER TEST", dut_name),
        ("TRAFFIC GENERATOR", f"Dell PowerEdge R640  |  {engine_label}"),
        ("TEST IDENTIFIER & OPERATOR", f"RUN-{started_dt.strftime('%Y%m%d')}-{int(run_id):04d}  |  {operator_name}"),
        ("REPORT DATE", started_dt.strftime("%d %B %Y  (%H:%M:%S)")),
    ]
    for k, v in cover_fields:
        story.append(Paragraph(k, meta_lbl_style))
        story.append(Paragraph(_esc(str(v)), meta_val_style))

    story.append(Spacer(1, 8 * mm))
    topo_snap = cfg.get("topology_snapshot") or {}
    topo_note = (
        "All throughput, latency, packet loss, and session figures in this report were captured from live execution on the Dell PowerEdge R640. "
        + (
            "Note: Physical test interfaces eno1-eno4 had no carrier during configuration; verify external LAN-to-WAN cabling across the EFG before certifying firewall forwarding capacity."
            if topo_snap.get("active_mode_code") == "internal_veth_loopback"
            else "Measurement sources and per-interface hardware capabilities are documented in Section 3."
        )
    )
    story.append(_callout_box("RECORDED MEASUREMENT PROVENANCE", topo_note, tone="info"))
    story.append(PageBreak())

    # =========================================================================
    # PAGE 2: EXECUTIVE SUMMARY
    # =========================================================================
    story.append(Paragraph("Executive summary", h1_style))
    story.append(Paragraph(
        f"Run #{run_id}: {_fmt_duration(summary.get('actual_duration_sec', run.get('duration_sec', 0)))} {_esc(str(run.get('profile_name') or ''))} ({sim_users:,} simulated users)",
        sub_style,
    ))

    pct_of_target = (avg_tx_bps / target_bps * 100.0) if target_bps > 0 else 0.0
    pct_rx_of_tx = (avg_rx_bps / avg_tx_bps * 100.0) if avg_tx_bps > 0 else 0.0
    verdict_accent = "#15803D" if verdict == "PASS" else ("#DC2626" if verdict == "FAIL" else "#1769D2")
    verdict_sub = "Configured thresholds evaluated" if thresholds_configured else "No pass/fail thresholds configured"

    story.append(_kpi_card_row([
        {"label": "TX Throughput (Avg)", "value": _fmt_bps(avg_tx_bps), "sub": f"{pct_of_target:.1f}% of {_fmt_bps(target_bps)} target", "accent": "#1769D2"},
        {"label": "RX Throughput (Avg)", "value": _fmt_bps(avg_rx_bps), "sub": f"{pct_rx_of_tx:.1f}% of transmitted", "accent": "#1769D2"},
        {"label": "Packet Loss", "value": f"{drop_pct:.4f}%", "sub": f"{int(summary.get('total_dropped_packets', 0)):,} dropped pkts", "accent": "#15803D" if drop_pct <= 0.05 else "#DC2626"},
    ]))
    story.append(Spacer(1, 3.5 * mm))
    story.append(_kpi_card_row([
        {"label": "Latency / Avg", "value": f"{lat_avg:.2f} us" if lat_avg > 0 else "N/A", "sub": str(summary.get("telemetry_source") or "TRex probe")[:32], "accent": "#1769D2"},
        {"label": "P99 Tail Latency", "value": f"{p99_lat:.2f} us" if p99_lat > 0 else "N/A", "sub": f"Jitter avg: {jitter_avg:.2f} us" if jitter_avg > 0 else "Histogram 99th pct", "accent": "#1769D2"},
        {"label": "Test Outcome", "value": verdict, "sub": verdict_sub, "accent": verdict_accent},
    ]))
    story.append(Spacer(1, 5 * mm))

    story.append(Paragraph("Primary Objective Assessment", sec_style))
    efg_answer = (
        f"This test exercised <b>{_esc(str(dut_name))}</b> with <b>{sim_users:,} simulated enterprise users</b> "
        f"({emulated_ips:,} distinct client IPv4 endpoints) using <b>{_esc(str(engine_label))}</b>. "
        f"Across {summary.get('sample_count', len(samples))} recorded 1-second intervals, the appliance transmitted an average of "
        f"<b>{_fmt_bps(avg_tx_bps)}</b> (peak <b>{_fmt_bps(max_tx_bps)}</b>), received <b>{_fmt_bps(avg_rx_bps)}</b>, "
        f"established up to <b>{peak_est:,}</b> concurrent TCP sessions (<b>{peak_flows:,}</b> active L4 flows at <b>{peak_cps:,.1f} CPS</b>), "
        f"and recorded <b>{drop_pct:.4f}%</b> counter-derived packet loss."
    )
    story.append(Paragraph(efg_answer, body_style))

    story.append(Paragraph("Acceptance Criteria Evaluation", sec_style))
    checks = summary.get("threshold_checks") or []
    if thresholds_configured and checks:
        t_rows = [["Metric", "Configured Requirement", "Measured Result", "Outcome"]]
        for ch in checks:
            t_rows.append([ch.get("metric", ""), ch.get("requirement", ""), ch.get("actual", ""), ch.get("outcome", "")])
        story.append(_styled_table(t_rows, [52, 44, 46, 36]))
    else:
        t_rows = [
            ["Metric", "Configured Threshold", "Measured Result", "Status"],
            ["Average RX Throughput", "Not configured", _fmt_bps(avg_rx_bps), "RECORDED"],
            ["Packet Loss Percentage", "Not configured", f"{drop_pct:.4f}%", "RECORDED"],
            ["Average / P99 Latency", "Not configured", f"{lat_avg:.2f} us / {p99_lat:.2f} us", "RECORDED"],
            ["Peak Concurrent Flows / Sessions", "Not configured", f"{peak_flows:,} flows / {peak_est:,} TCP est.", "RECORDED"],
        ]
        story.append(_styled_table(t_rows, [54, 42, 48, 34]))

    story.append(Spacer(1, 4 * mm))
    story.append(_callout_box(
        "METHODOLOGY NOTE — USERS VS FLOWS VS SESSIONS",
        f"Simulated Users ({sim_users:,}), Emulated Client IPs ({emulated_ips:,}), Active L4 Flows ({peak_flows:,}), and Established TCP Sessions ({peak_est:,}) are tracked independently and never conflated.",
        tone="info",
    ))

    if report_type == "executive":
        story.append(PageBreak())
        story.append(Paragraph("Throughput & Workload Summary", h1_style))
        story.append(Paragraph("Recorded throughput timeline and synthetic workload distribution", sub_style))
        story.append(_chart_card("Recorded Throughput Timeline", _chart_throughput(samples, target_bps), height_mm=62))
        story.append(Spacer(1, 4 * mm))
        if cfg.get("protocol_mix"):
            story.append(_chart_card("Configured Enterprise Workload Allocation", _chart_workload_donut(cfg.get("protocol_mix")), height_mm=58))
        else:
            # normalize_mix_to_100({}) returns the DEFAULT mix; never chart a mix the run did not use
            story.append(_callout_box("NO APPLICATION MIX CONFIGURED", "This run did not use an application workload mix (e.g. fixed-frame STL sweep).", tone="info"))
        doc.build(
            story,
            canvasmaker=lambda *a, **kw: _ReportNumberedCanvas(
                *a,
                run_label=f"EXECUTIVE REPORT  |  RUN #{run_id}",
                footer_left=f"CISCO TRex + UniFi  |  RUN #{run_id} EXECUTIVE SUMMARY",
                **kw,
            ),
        )
        buf.seek(0)
        return buf.getvalue()

    story.append(PageBreak())

    # =========================================================================
    # PAGE 3: TEST CONFIGURATION & HARDWARE INVENTORY
    # =========================================================================
    story.append(Paragraph("Test configuration", h1_style))
    story.append(Paragraph("Immutable run settings, emulated user pool, and hardware inventory", sub_style))

    story.append(Paragraph("Test identity and traffic settings", sec_style))
    cfg_rows = [
        ["Parameter", "Configured Value"],
        ["Test ID & Name", f"RUN-{int(run_id):04d} — {run.get('name', '')}"],
        ["Profile", f"{run.get('profile_name', '')} ({run.get('profile_id', '')})"],
        ["Traffic Engine & Mode", f"{engine_label}  |  Execution: {str(run.get('test_mode', '')).upper()}"],
        ["Duration", f"{_fmt_duration(summary.get('actual_duration_sec', run.get('duration_sec', 0)))} (Ramp-up {cfg.get('ramp_up_sec', 0)}s / Steady {cfg.get('steady_sec', run.get('duration_sec', 0))}s / Ramp-down {cfg.get('ramp_down_sec', 0)}s)"],
        ["Configured Target Rate", f"{_fmt_bps(target_bps)} ({run.get('target_rate_pct', 0)}% of {cfg.get('link_capacity_mbps', 10000)} Mbps reference)"],
        ["Simulated Population", f"{sim_users:,} simulated users  |  {emulated_ips:,} client IPs ({cfg.get('src_ip_start', '16.0.0.1')} – {cfg.get('src_ip_end', '')})"],
        ["Frame Size / VLAN / DSCP", f"Avg ~{cfg.get('frame_size', 594)} bytes (64–9000B)  |  VLAN: {cfg.get('vlan_id', 0) or 'Untagged'}  |  DSCP: {cfg.get('dscp', 0)}"],
    ]
    story.append(_styled_table(cfg_rows, [56, 122]))

    story.append(Paragraph("Hardware and monitoring sources", sec_style))
    hw_rows = [
        ["Component", "Verified Configuration / Telemetry Source"],
        ["Traffic Generator Host", "Dell PowerEdge R640 — Dual Intel Xeon Silver 4110 (32 threads), 500 GB RAM"],
        ["Packet / Session Engine", f"{engine_label} (DPDK HugePages enabled)"],
        ["Device Under Test (DUT)", dut_name],
        ["Topology / Path Mode", topo_snap.get("active_mode_label") or "Configured TRex Dual-Port Interface Pair"],
        ["UniFi Telemetry", f"{len(unifi_samples)} samples captured via UniFi Network API" if unifi_samples else "Not connected during run (TRex standalone measurements)"],
        ["SNMP Interface Counters", f"{len(snmp_samples)} IF-MIB counter polls captured" if snmp_samples else "Optional SNMP disabled or not polled during run"],
    ]
    story.append(_styled_table(hw_rows, [56, 122]))
    story.append(Spacer(1, 4 * mm))
    story.append(_callout_box(
        "HARDWARE & TOPOLOGY VERIFICATION",
        topo_snap.get("honest_10g_explanation")
        or "Verify physical link negotiation on both LAN ingress and WAN responder interfaces. A 10 Gbps target requires 10GbE physical test ports on both sides of the DUT.",
        tone="warn",
    ))
    story.append(PageBreak())

    # =========================================================================
    # PAGE 4: THROUGHPUT & SESSION PERFORMANCE
    # =========================================================================
    story.append(Paragraph("Throughput & session performance", h1_style))
    story.append(Paragraph("Transmitted/received bandwidth and stateful connection concurrency across the test window", sub_style))

    story.append(_kpi_card_row([
        {"label": "Peak TX Rate", "value": _fmt_bps(max_tx_bps), "sub": f"Avg: {_fmt_bps(avg_tx_bps)}", "accent": "#1769D2"},
        {"label": "Peak RX Rate", "value": _fmt_bps(max_rx_bps), "sub": f"Avg: {_fmt_bps(avg_rx_bps)}", "accent": "#1769D2"},
        {"label": "Configured Target", "value": _fmt_bps(target_bps), "sub": f"Peak PPS: {_fmt_pps(summary.get('max_tx_pps', 0))}", "accent": "#1769D2"},
    ]))
    story.append(Spacer(1, 4 * mm))
    story.append(_chart_card("Recorded Throughput Timeline (TRex TX vs RX vs Target)", _chart_throughput(samples, target_bps), height_mm=66))
    story.append(Spacer(1, 4 * mm))

    story.append(Paragraph("Throughput and stateful session metrics", sec_style))
    tp_rows = [
        ["Measurement", "Recorded Value", "Telemetry Source"],
        ["Configured Target Throughput", _fmt_bps(target_bps), "Run configuration"],
        ["Average / Peak Transmitted", f"{_fmt_bps(avg_tx_bps)}  /  {_fmt_bps(max_tx_bps)}", "Cisco TRex TX port counters"],
        ["Average / Peak Received", f"{_fmt_bps(avg_rx_bps)}  /  {_fmt_bps(max_rx_bps)}", "Cisco TRex RX port counters"],
        ["Packet Rate (Avg / Peak)", f"{_fmt_pps(summary.get('avg_tx_pps', 0))}  /  {_fmt_pps(summary.get('max_tx_pps', 0))}", "Cisco TRex PPS counters"],
        ["Peak Active Flows / TCP Sessions", f"{peak_flows:,} active flows  /  {peak_est:,} established TCP", "TRex ASTF/STL flow table"],
        ["Connection Rate & Total Handshakes", f"{peak_cps:,.1f} peak CPS  /  {int(summary.get('total_tcp_connects', 0)):,} TCP connects", "TRex TCP state machine"],
    ]
    story.append(_styled_table(tp_rows, [62, 66, 50]))
    story.append(PageBreak())

    # =========================================================================
    # PAGE 5: LATENCY, JITTER & PACKET LOSS
    # =========================================================================
    story.append(Paragraph("Latency, jitter and packet loss", h1_style))
    story.append(Paragraph("End-to-end forwarding delay, tail latency percentiles, and counter-derived loss", sub_style))

    story.append(_kpi_card_row([
        {"label": "Average Latency", "value": f"{lat_avg:.2f} us" if lat_avg > 0 else "N/A", "sub": f"P95: {p95_lat:.2f} us", "accent": "#1769D2"},
        {"label": "P99 Tail Latency", "value": f"{p99_lat:.2f} us" if p99_lat > 0 else "N/A", "sub": f"Jitter: {jitter_avg:.2f} us", "accent": "#D97706" if p99_lat > 5000 else "#1769D2"},
        {"label": "Packet Loss", "value": f"{drop_pct:.4f}%", "sub": f"TX {int(summary.get('total_tx_packets', 0)):,} / RX {int(summary.get('total_rx_packets', 0)):,}", "accent": "#15803D" if drop_pct <= 0.05 else "#DC2626"},
    ]))
    story.append(Spacer(1, 4 * mm))
    story.append(_chart_card("Recorded Latency & Jitter Trend", _chart_latency(samples), height_mm=65))
    story.append(Spacer(1, 4 * mm))

    story.append(Paragraph("Quality & reliability metrics", sec_style))
    lat_rows = [
        ["Metric", "Measured Value", "Method / Provenance"],
        ["Minimum / Average Latency", f"{float(summary.get('lat_min_us', 0)):.2f} us  /  {lat_avg:.2f} us", summary.get("telemetry_source", "TRex latency probe")],
        ["P95 / P99 / Max Latency", f"{p95_lat:.2f} us  /  {p99_lat:.2f} us  /  {float(summary.get('lat_max_us', 0)):.2f} us", "TRex hardware/software latency histogram"],
        ["Inter-Packet Jitter (Avg)", f"{jitter_avg:.2f} us" if jitter_avg > 0 else "0.00 us", "RFC 3550 / TRex probe interarrival jitter"],
        ["TCP Drops / Retransmissions", f"{int(summary.get('total_tcp_drops', 0)):,} drops  /  {int(summary.get('total_tcp_retransmits', 0)):,} rexmits", "TRex ASTF TCP stack counters"],
        ["Estimated Voice MOS (G.107)", f"{float(summary.get('mos_avg', 0)):.2f} / 4.50" if float(summary.get("mos_avg", 0)) > 0 else "N/A", "Derived from measured RTT, jitter & loss"],
    ]
    story.append(_styled_table(lat_rows, [56, 62, 60]))
    story.append(Spacer(1, 4 * mm))
    story.append(_callout_box(
        "MEASUREMENT GUIDANCE",
        "Latency and jitter are measured directly by timestamped TRex probe packets between TX and RX interfaces, never inferred from gateway CPU or SNMP counters.",
        tone="info",
    ))
    story.append(PageBreak())

    # =========================================================================
    # PAGE 6: TRAFFIC WORKLOAD BREAKDOWN
    # =========================================================================
    story.append(Paragraph("Traffic workload breakdown", h1_style))
    story.append(Paragraph("Synthetic enterprise application-mix distribution and protocol modelling classification", sub_style))

    mix = cfg.get("protocol_mix") or {}
    if mix:
        story.append(_chart_card("Configured Enterprise Workload Allocation (100% Normalized)", _chart_workload_donut(mix), height_mm=64))
    else:
        # normalize_mix_to_100({}) returns the DEFAULT mix; never chart a mix the run did not use
        story.append(_callout_box("NO APPLICATION MIX CONFIGURED", "This run did not use an application workload mix (e.g. fixed-frame STL sweep).", tone="info"))
    story.append(Spacer(1, 4 * mm))

    story.append(Paragraph("Traffic profile methodology", sec_style))
    story.append(Paragraph(
        "Application category names describe synthetic workload characteristics (frame-size distributions, TCP/UDP state transitions, "
        "request/response burst sizes, think-time delays, and DSCP markings). They do not execute proprietary commercial logins or "
        "DRM-encrypted protocols (such as authenticated WhatsApp, Facebook, Netflix, or Microsoft 365 tenant sessions).",
        body_style,
    ))

    class_rows = [
        ["Engine Mode", "Active in Run", "Engineering Interpretation"],
        ["Stateful ASTF (trex_astf)", "YES" if engine_code == "trex_astf" else "No", "Full TCP 3-way handshakes, sliding windows, retransmissions & UDP flows across emulated user IPs"],
        ["Stateless STL (trex_stl)", "YES" if engine_code == "trex_stl" else "No", "Wire-speed L2–L4 stream generation with Field Engine IP/port ranges and PG_ID latency probes"],
        ["Live Internet / WAN (internet_wan)", "YES" if engine_code in ("internet_wan", "hybrid") else "No", "Genuine outbound HTTP/HTTPS/DNS sockets routed via management/WAN gateway"],
    ]
    story.append(_styled_table(class_rows, [48, 28, 102]))
    story.append(PageBreak())

    # =========================================================================
    # PAGE 7: UNIFI INFRASTRUCTURE & SNMP OBSERVATIONS
    # =========================================================================
    story.append(Paragraph("UniFi infrastructure observations", h1_style))
    story.append(Paragraph("Correlated gateway, switch, access-point, and SNMP interface telemetry", sub_style))

    if unifi_samples:
        cpu_vals = [float(u["gw_cpu_pct"]) for u in unifi_samples if u.get("gw_cpu_pct") is not None]
        mem_vals = [float(u["gw_mem_pct"]) for u in unifi_samples if u.get("gw_mem_pct") is not None]
        wan_vals = [float(u.get("wan_rx_bps") or 0) + float(u.get("wan_tx_bps") or 0) for u in unifi_samples if u.get("wan_rx_bps") is not None or u.get("wan_tx_bps") is not None]
        last_u = unifi_samples[-1]
        peak_u_cpu = f"{max(cpu_vals):.1f}%" if cpu_vals else "Unavailable"
        peak_u_mem = f"{max(mem_vals):.1f}%" if mem_vals else "Unavailable"
        peak_wan = _fmt_bps(max(wan_vals)) if wan_vals else "Unavailable"
        sw_tot = int(last_u.get("switches_total") or 0)
        sw_on = int(last_u.get("switches_online") or 0)
        ap_tot = int(last_u.get("aps_total") or 0)
        ap_on = int(last_u.get("aps_online") or 0)
        dev_str = f"{sw_on + ap_on + (1 if last_u.get('gw_online') else 0)} / {sw_tot + ap_tot + 1}"

        story.append(_kpi_card_row([
            {"label": "Gateway Peak CPU", "value": peak_u_cpu, "sub": f"Peak RAM: {peak_u_mem}", "accent": "#D97706" if (cpu_vals and max(cpu_vals) > 80) else "#1769D2"},
            {"label": "Observed WAN Rate", "value": peak_wan, "sub": last_u.get("gw_name") or dut_name[:26], "accent": "#1769D2"},
            {"label": "UniFi Device Health", "value": dev_str, "sub": f"Clients: {last_u.get('active_clients') if last_u.get('active_clients') is not None else 'Unavailable'}", "accent": "#15803D"},
        ]))
        story.append(Spacer(1, 4 * mm))

        u_rows = [
            ["Monitored Tier", "Status", "Recorded Observation"],
            [last_u.get("gw_name") or "UniFi Gateway (EFG)", "Online" if last_u.get("gw_online") else "Offline", f"CPU peak {peak_u_cpu}; Memory peak {peak_u_mem}; WAN {peak_wan}"],
            ["UniFi Switching Tier", f"{sw_on} / {sw_tot} Online", "Polled via read-only UniFi Network API"],
            ["UniFi Wireless AP Tier", f"{ap_on} / {ap_tot} Online", "Polled via read-only UniFi Network API"],
            ["SNMP Interface Counters", f"{len(snmp_samples)} samples" if snmp_samples else "Not enabled", "IF-MIB 64-bit HC octets, errors & discards" if snmp_samples else "Configure SNMPv2c/v3 for port-level error counters"],
        ]
        story.append(_styled_table(u_rows, [52, 36, 90]))
    else:
        story.append(_kpi_card_row([
            {"label": "Gateway CPU", "value": "Unavailable", "sub": "UniFi API not connected", "accent": "#64748B"},
            {"label": "WAN Rate", "value": "Unavailable", "sub": "UniFi API not connected", "accent": "#64748B"},
            {"label": "SNMP Counters", "value": f"{len(snmp_samples)} polls" if snmp_samples else "Disabled", "sub": "Read-only IF-MIB", "accent": "#1769D2" if snmp_samples else "#64748B"},
        ]))
        story.append(Spacer(1, 4 * mm))
        story.append(_callout_box(
            "UNIFI API TELEMETRY NOT CONNECTED DURING THIS RUN",
            "No UniFi controller metrics were fabricated or estimated. Connect a read-only Local UniFi Network API key (X-API-KEY) in Administration -> API Integrations to capture live EFG CPU, memory, WAN throughput, switch ports, and client counts during future runs.",
            tone="warn",
        ))

    story.append(Spacer(1, 4 * mm))
    story.append(Paragraph("Telemetry provenance & polling intervals", sec_style))
    prov_rows = [
        ["Signal", "Source", "Collection Interval"],
        ["TX / RX Throughput, PPS, Flows, Latency", "Cisco TRex ZMQ RPC (127.0.0.1:4501)", "250 ms live stream / 1 s persisted"],
        ["Gateway CPU, RAM, WAN & Device Health", "Local UniFi Network API (Read-Only)", "5 seconds (when enabled)"],
        ["Interface Octets, Errors & Discards", "SNMPv2c / SNMPv3 IF-MIB (ifXTable)", "5 seconds (when enabled)"],
    ]
    story.append(_styled_table(prov_rows, [68, 66, 44]))
    story.append(PageBreak())

    # =========================================================================
    # PAGE 8: TREX & UNIFI CORRELATION
    # =========================================================================
    story.append(Paragraph("TRex and infrastructure correlation", h1_style))
    story.append(Paragraph("Synchronized timeline comparing offered TRex traffic load against gateway/system CPU utilisation", sub_style))

    story.append(_chart_card("Synchronized Load vs Resource Utilisation Timeline", _chart_correlation(samples), height_mm=68))
    story.append(Spacer(1, 4 * mm))

    story.append(Paragraph("Correlation observations", sec_style))
    story.append(Paragraph(
        "Aligning timestamped Cisco TRex load steps against gateway CPU, memory, and SNMP interface error counters helps pinpoint "
        "saturation knees where stateful firewall inspection, NAT table lookups, or QoS queues begin introducing latency or tail drops. "
        "Note that UniFi API polling (5s) and TRex telemetry (1s) operate on independent clocks.",
        body_style,
    ))

    corr_rows = [
        ["Operational Check", "Recorded Observation"],
        ["TRex Achieved Rate vs Target", f"Avg {_fmt_bps(avg_tx_bps)} achieved against {_fmt_bps(target_bps)} target ({pct_of_target:.1f}%)"],
        ["Gateway CPU Headroom", f"Peak {summary.get('peak_gw_cpu_pct')}% recorded" if summary.get("peak_gw_cpu_pct") is not None else "UniFi gateway CPU telemetry unavailable during run"],
        ["Packet Loss Correlation", f"{drop_pct:.4f}% overall counter-derived loss ({int(summary.get('total_dropped_packets', 0)):,} packets)"],
        ["Timeline Synchronization", f"{len(samples)} 1-second TRex samples aligned with {len(unifi_samples)} UniFi & {len(snmp_samples)} SNMP polls"],
    ]
    story.append(_styled_table(corr_rows, [58, 120]))
    story.append(PageBreak())

    # =========================================================================
    # PAGE 9: FINDINGS, LIMITATIONS & RECOMMENDATIONS
    # =========================================================================
    story.append(Paragraph("Findings, limitations and next steps", h1_style))
    story.append(Paragraph("Engineering conclusions, methodology caveats, and operational recommendations", sub_style))

    outcome_tone = "pass" if verdict == "PASS" else ("fail" if verdict == "FAIL" else "info")
    outcome_heading = (
        f"{verdict} — Configured acceptance thresholds evaluated"
        if thresholds_configured
        else f"{verdict} — Recorded benchmark (no explicit pass/fail thresholds configured)"
    )
    story.append(_callout_box(
        outcome_heading,
        f"Run #{run_id} completed {_fmt_duration(summary.get('actual_duration_sec', 0))} of {engine_label} testing across {sim_users:,} simulated users with {_fmt_bps(avg_rx_bps)} average RX throughput and {drop_pct:.4f}% packet loss.",
        tone=outcome_tone,
    ))
    story.append(Spacer(1, 4 * mm))

    story.append(Paragraph("Key technical findings", sec_style))
    findings = [
        f"• <b>Throughput Delivery:</b> Transmitted {_fmt_bps(avg_tx_bps)} average ({_fmt_bps(max_tx_bps)} peak) and received {_fmt_bps(avg_rx_bps)} average ({_fmt_bps(max_rx_bps)} peak).",
        f"• <b>User & Session Concurrency:</b> Emulated {sim_users:,} users ({emulated_ips:,} client IPs), reaching {peak_flows:,} peak active flows and {peak_est:,} concurrent established TCP sessions at {peak_cps:,.1f} peak CPS.",
        f"• <b>Latency & Packet Loss:</b> Recorded {lat_avg:.2f} us average latency, {p99_lat:.2f} us P99 tail latency, {jitter_avg:.2f} us average jitter, and {drop_pct:.4f}% packet loss.",
        f"• <b>Infrastructure Telemetry:</b> {'Captured live UniFi gateway/device telemetry (' + str(len(unifi_samples)) + ' polls).' if unifi_samples else 'UniFi API was not connected during this run; only direct TRex/R640 metrics were recorded.'}",
    ]
    for f_line in findings:
        story.append(Paragraph(f_line, body_style))

    story.append(Paragraph("Methodology limitations & disclosures", sec_style))
    story.append(Paragraph(
        "1. Synthetic application profiles emulate realistic packet sizes, burst intervals, and TCP/UDP session lifecycles, but do not execute commercial TLS/DRM authentication flows. "
        "2. End-to-end EFG firewall validation requires TRex Port 0 connected to an EFG LAN switch port and TRex Port 1 connected to an isolated WAN responder VLAN/port on the EFG WAN side. "
        "3. Because the Dell R640 currently uses its single 10GbE port (enp216s0) for management and exposes four 1GbE ports (eno1–eno4), external physical LAN-to-WAN hairpin throughput is bounded by physical link speed unless a dual-port 10GbE NIC is installed.",
        body_style,
    ))

    doc.build(
        story,
        canvasmaker=lambda *a, **kw: _ReportNumberedCanvas(
            *a,
            run_label=f"RUN #{run_id}  |  {verdict}",
            footer_left=f"CISCO TRex + UniFi  |  RUN #{run_id} — {dut_name.upper()[:38]}",
            **kw,
        ),
    )
    buf.seek(0)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Side-by-Side Comparison PDF Report
# ---------------------------------------------------------------------------
def generate_comparison_pdf_bytes(comp: Dict[str, Any]) -> bytes:
    """Generate a clean Light-Mode Side-by-Side Comparison PDF for two recorded runs."""
    buf = io.BytesIO()
    ra = comp["run_a"]
    rb = comp["run_b"]
    sa = _ensure_run_summary(ra)
    sb = _ensure_run_summary(rb)
    deltas = comp.get("deltas") or {}

    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=16 * mm,
        rightMargin=16 * mm,
        topMargin=30 * mm,
        bottomMargin=20 * mm,
        title=f"Comparison Report — Run #{ra['id']} vs Run #{rb['id']}",
    )
    styles = getSampleStyleSheet()
    h1_style = ParagraphStyle("CH1", parent=styles["Heading1"], fontName="Helvetica-Bold", fontSize=18, leading=22, textColor=NAVY, spaceAfter=2)
    sub_style = ParagraphStyle("CSub", parent=styles["Normal"], fontName="Helvetica", fontSize=9.2, leading=13, textColor=TEXT_MUTED, spaceAfter=10)
    sec_style = ParagraphStyle("CSec", parent=styles["Heading2"], fontName="Helvetica-Bold", fontSize=11, leading=15, textColor=NAVY, spaceBefore=8, spaceAfter=5)

    story: List[Any] = []
    story.append(Spacer(1, 60 * mm))
    story.append(_callout_box(
        "SIDE-BY-SIDE BENCHMARK COMPARISON REPORT",
        f"Baseline Run #{ra['id']} ({ra.get('name')})  vs  Candidate Run #{rb['id']} ({rb.get('name')})",
        tone="info",
    ))
    story.append(PageBreak())

    story.append(Paragraph("Side-by-side run comparison", h1_style))
    story.append(Paragraph(f"Run #{ra['id']} ({int(ra.get('simulated_users') or 0):,} users) vs Run #{rb['id']} ({int(rb.get('simulated_users') or 0):,} users)", sub_style))

    def _fmt_d(key: str, unit: str = "") -> str:
        d = deltas.get(key) or {}
        val = d.get("delta")
        pct = d.get("delta_pct")
        if val is None:
            return "—"
        sign = "+" if val > 0 else ""
        pct_s = f" ({sign}{pct:.1f}%)" if pct is not None else ""
        return f"{sign}{val:.2f}{unit}{pct_s}"

    rows = [
        ["Metric", f"Run #{ra['id']} (Baseline)", f"Run #{rb['id']} (Comparison)", "Delta (B - A)"],
        ["Simulated Users", f"{int(ra.get('simulated_users') or 0):,}", f"{int(rb.get('simulated_users') or 0):,}", f"{int(rb.get('simulated_users') or 0) - int(ra.get('simulated_users') or 0):+,}"],
        ["Average TX Throughput", _fmt_bps(sa.get("avg_tx_bps", 0)), _fmt_bps(sb.get("avg_tx_bps", 0)), _fmt_d("avg_tx_mbps", " Mbps")],
        ["Average RX Throughput", _fmt_bps(sa.get("avg_rx_bps", 0)), _fmt_bps(sb.get("avg_rx_bps", 0)), _fmt_d("avg_rx_mbps", " Mbps")],
        ["Peak RX Throughput", _fmt_bps(sa.get("max_rx_bps", 0)), _fmt_bps(sb.get("max_rx_bps", 0)), _fmt_d("max_rx_mbps", " Mbps")],
        ["Packet Loss (%)", f"{float(sa.get('drop_pct', 0)):.4f}%", f"{float(sb.get('drop_pct', 0)):.4f}%", _fmt_d("drop_pct", "%")],
        ["Average Latency (us)", f"{float(sa.get('lat_avg_us', 0)):.2f} us", f"{float(sb.get('lat_avg_us', 0)):.2f} us", _fmt_d("lat_avg_us", " us")],
        ["P99 Latency (us)", f"{float(sa.get('p99_lat_us', 0)):.2f} us", f"{float(sb.get('p99_lat_us', 0)):.2f} us", _fmt_d("p99_lat_us", " us")],
        ["Peak Active Flows", f"{int(sa.get('peak_active_flows', 0)):,}", f"{int(sb.get('peak_active_flows', 0)):,}", _fmt_d("peak_active_flows", "")],
        ["Peak Established TCP", f"{int(sa.get('peak_established_sessions', 0)):,}", f"{int(sb.get('peak_established_sessions', 0)):,}", _fmt_d("peak_established_sessions", "")],
        ["Outcome", str(sa.get("verdict", "COMPLETED")), str(sb.get("verdict", "COMPLETED")), "—"],
    ]
    story.append(_styled_table(rows, [46, 44, 44, 44]))
    story.append(Spacer(1, 5 * mm))

    # Overlaid Throughput Chart
    fig, ax = plt.subplots(figsize=(7.1, 2.7), dpi=160)
    fig.patch.set_facecolor("#FFFFFF")
    _style_light_axes(ax)
    s_a = ra.get("samples") or []
    s_b = rb.get("samples") or []
    max_b = max(
        max((float(x.get("rx_bps") or 0) for x in s_a), default=0),
        max((float(x.get("rx_bps") or 0) for x in s_b), default=0),
    )
    div = 1e9 if max_b >= 800_000_000 else 1e6
    unit = "Gbps" if div == 1e9 else "Mbps"
    if s_a:
        ax.plot([x["elapsed_sec"] for x in s_a], [float(x.get("rx_bps") or 0) / div for x in s_a], color="#1769D2", linewidth=2.0, label=f"Run #{ra['id']} RX ({unit})")
    if s_b:
        ax.plot([x["elapsed_sec"] for x in s_b], [float(x.get("rx_bps") or 0) / div for x in s_b], color="#15803D", linewidth=2.0, linestyle="--", label=f"Run #{rb['id']} RX ({unit})")
    ax.set_ylabel(f"RX Throughput ({unit})", color="#334155", fontsize=8.5, fontweight="bold")
    ax.set_xlabel("Elapsed seconds", color="#64748B", fontsize=8)
    ax.set_ylim(bottom=0)
    ax.legend(loc="lower right", frameon=True, facecolor="#FFFFFF", edgecolor="#E2E8F0", fontsize=8)
    fig.tight_layout()
    c_buf = io.BytesIO()
    fig.savefig(c_buf, format="png", facecolor="#FFFFFF")
    plt.close(fig)
    c_buf.seek(0)

    story.append(Paragraph("Overlaid RX throughput progression", sec_style))
    story.append(_chart_card(f"Run #{ra['id']} vs Run #{rb['id']} RX Throughput", c_buf, height_mm=65))

    doc.build(
        story,
        canvasmaker=lambda *a, **kw: _ReportNumberedCanvas(
            *a,
            run_label=f"COMPARISON  |  #{ra['id']} VS #{rb['id']}",
            footer_left=f"CISCO TRex + UniFi  |  COMPARISON REPORT #{ra['id']} VS #{rb['id']}",
            **kw,
        ),
    )
    buf.seek(0)
    return buf.getvalue()
