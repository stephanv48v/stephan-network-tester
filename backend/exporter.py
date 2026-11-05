"""
Codeblue Network Test Studio - PDF, CSV and JSON report generator.

PDF design system (light, print-friendly):
  * Navy (#0F1D31) cover hero and content-page banners with the Codeblue logo (_ReportNumberedCanvas).
  * White KPI tiles with coloured accent bars, navy-header tables with alternating rows.
  * Matplotlib charts rendered with the object API (matplotlib.figure.Figure + Agg canvas, never pyplot
    global state, so concurrent exports in asyncio.to_thread workers cannot interfere). Every chart is
    rendered at its exact printed size, so fonts are true point sizes and consistent across charts.
  * Two charts per page where it makes sense; sections flow (CondPageBreak) instead of forcing half-empty pages.

Engineering integrity rules:
  * Charts are drawn ONLY from measured samples. A chart whose data is all zero/None is skipped and replaced
    by a one-line note; nothing is interpolated or invented.
  * Pass/Fail verdicts appear only when acceptance thresholds were configured for the run.
  * Hardware/topology statements come from the run's own config (e.g. config['topology_snapshot']) or are left out.
  * MOS is labelled as an estimate (simplified ITU-T G.107 E-model computed from measured latency/jitter/loss).
  * Large runs (e.g. 24 h soak = 86,400 samples) are bucket-averaged to <= MAX_PLOT_POINTS points for plotting;
    statistics tables always use every sample.
"""
import csv
import datetime
import io
import json
import math
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from xml.sax.saxutils import escape as _esc_raw

import numpy as np
import matplotlib
matplotlib.use("Agg")
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
from matplotlib.ticker import FuncFormatter, MaxNLocator
from matplotlib.transforms import blended_transform_factory

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.platypus import (
    CondPageBreak,
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


def _esc(v: Any) -> str:
    return _esc_raw(str(v if v is not None else ""))


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


def _fmt_us(us: Optional[float]) -> str:
    """Latency in microseconds -> 'xx us' / 'x.xx ms' (WinAnsi-safe for reportlab's base fonts)."""
    if us is None:
        return "N/A"
    v = float(us)
    if v <= 0:
        return "N/A"
    if v >= 1000:
        return f"{v / 1000:.2f} ms"
    return f"{v:.0f} µs" if v >= 100 else f"{v:.1f} µs"


def _fmt_duration(seconds: Any) -> str:
    try:
        sec = max(0, int(float(seconds or 0)))
    except (TypeError, ValueError):
        sec = 0
    if sec < 60:
        return f"{sec} seconds"
    mins, rem = divmod(sec, 60)
    if mins < 60:
        return f"{mins} min {rem} sec" if rem else f"{mins} minutes"
    hrs, mins = divmod(mins, 60)
    return f"{hrs}h {mins}m"


def _f(v: Any) -> Optional[float]:
    """Float or None (None/NaN/inf/garbage -> None)."""
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def _ensure_run_summary(run: Dict[str, Any]) -> Dict[str, Any]:
    summary = dict(run.get("summary") or {})
    samples = run.get("samples") or []
    if not summary and samples:
        lat_vals = [float(s.get("lat_avg_us") or 0) for s in samples if float(s.get("lat_avg_us") or 0) > 0]
        p99_vals = [float(s.get("p99_lat_us") or 0) for s in samples if float(s.get("p99_lat_us") or 0) > 0]
        jit_vals = [float(s.get("jitter_us") or 0) for s in samples if float(s.get("jitter_us") or 0) > 0]
        summary = {
            "sample_count": len(samples),
            "actual_duration_sec": int(samples[-1].get("elapsed_sec") or len(samples)),
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
# Time-series helper: columns as numpy arrays, downsampling, phase segments
# ---------------------------------------------------------------------------
MAX_PLOT_POINTS = 1500

_PHASE_NAMES = {
    "ramp_up": "Ramp-up",
    "steady": "Steady",
    "ramp_down": "Ramp-down",
    "continuous": "Continuous",
    "idle": "Idle",
    "soak": "Soak",
}


def _phase_label(p: Any) -> str:
    p = str(p or "").strip()
    if not p:
        return "Run"
    if p in _PHASE_NAMES:
        return _PHASE_NAMES[p]
    m = re.match(r"^step_(\d+)_(\d+(?:\.\d+)?)pct$", p)
    if m:
        return f"Step {m.group(1)} ({m.group(2)}%)"
    m = re.match(r"^step_(\d+)$", p)
    if m:
        return f"Step {m.group(1)}"
    if re.match(r"^\d+\s*B$", p):
        return p.replace(" ", "")
    return p.replace("_", " ").capitalize()


def _time_scale(span_sec: float) -> Tuple[float, str]:
    if span_sec <= 300:
        return 1.0, "Elapsed time (s)"
    if span_sec <= 3 * 3600:
        return 60.0, "Elapsed time (min)"
    return 3600.0, "Elapsed time (h)"


def _amax(a: np.ndarray) -> float:
    fin = a[np.isfinite(a)] if a.size else a
    return float(fin.max()) if fin.size else 0.0


def _bucket(a: np.ndarray, starts: np.ndarray, how: str = "mean") -> np.ndarray:
    fin = np.isfinite(a)
    if how == "max":
        r = np.maximum.reduceat(np.where(fin, a, -np.inf), starts)
        r[np.isneginf(r)] = np.nan
        return r
    sums = np.add.reduceat(np.where(fin, a, 0.0), starts)
    cnt = np.add.reduceat(fin.astype(float), starts)
    with np.errstate(invalid="ignore", divide="ignore"):
        r = sums / cnt
    r[cnt == 0] = np.nan
    return r


class _TS:
    """Per-second samples as cached numpy columns (None -> NaN) plus phase segments."""

    def __init__(self, samples: Optional[Sequence[Dict[str, Any]]]):
        self.samples = [s for s in (samples or []) if isinstance(s, dict)]
        self.n = len(self.samples)
        self._c: Dict[str, np.ndarray] = {}
        x = self.col("elapsed_sec").copy()
        if self.n:
            idx = np.arange(self.n, dtype=float)
            bad = ~np.isfinite(x)
            x[bad] = idx[bad]
        self.x = x
        span = float(x.max() - x.min()) if self.n else 0.0
        self.tdiv, self.xlabel = _time_scale(span)
        step = float(np.median(np.diff(x))) if self.n > 1 else 1.0
        self.step = step if (math.isfinite(step) and step > 0) else 1.0
        self.segs = self._segments()

    def col(self, key: str) -> np.ndarray:
        if key not in self._c:
            raw = [s.get(key) for s in self.samples]
            try:
                a = np.array(raw, dtype=float)
            except (TypeError, ValueError):
                a = np.array([(_f(v) if _f(v) is not None else np.nan) for v in raw], dtype=float)
            if a.ndim != 1:
                a = np.full(self.n, np.nan)
            a[~np.isfinite(a)] = np.nan
            self._c[key] = a
        return self._c[key]

    def has(self, key: str) -> bool:
        a = self.col(key)
        return bool(np.any(np.isfinite(a) & (a != 0)))

    def _segments(self) -> List[Tuple[str, float, float]]:
        segs: List[Tuple[str, float, float]] = []
        cur: Optional[str] = None
        start = 0.0
        for i, s in enumerate(self.samples):
            p = str(s.get("phase_name") or "").strip()
            if i == 0 or p != cur:
                if i > 0:
                    segs.append((cur or "", start, float(self.x[i])))
                cur, start = p, float(self.x[i])
        if self.n:
            segs.append((cur or "", start, float(self.x[-1]) + self.step))
        return segs

    def xy(self, keys: Sequence[str], how: str = "mean") -> Tuple[np.ndarray, List[np.ndarray]]:
        xs = self.x / self.tdiv
        ys = [self.col(k) for k in keys]
        if self.n <= MAX_PLOT_POINTS:
            return xs, ys
        starts = np.unique(np.linspace(0, self.n, MAX_PLOT_POINTS, endpoint=False).astype(int))
        return _bucket(xs, starts, "mean"), [_bucket(y, starts, how) for y in ys]

    def bands(self, ax: Any, labels: bool = False) -> None:
        """Shade alternate test phases (ramp-up / steady / ramp-down / step N) behind the data."""
        segs = self.segs
        if len(segs) < 2 or len(segs) > 60 or len({s[0] for s in segs}) < 2:
            return
        total = max(segs[-1][2] - segs[0][1], 1e-9)
        trans = blended_transform_factory(ax.transData, ax.transAxes)
        for i, (p, a, b) in enumerate(segs):
            a_, b_ = a / self.tdiv, b / self.tdiv
            if i % 2 == 0:
                ax.axvspan(a_, b_, color=PHASE_FILL, lw=0, zorder=0)
            if i > 0:
                ax.axvline(a_, color="#B6C2D2", lw=0.6, ls=(0, (2, 2)), zorder=1)
            if labels and (b - a) / total >= 0.07:
                ax.text(
                    (a_ + min(b_, self.x[-1] / self.tdiv)) / 2, 0.035, _phase_label(p), transform=trans,
                    ha="center", va="bottom", fontsize=6.5, color=C_MUTED, zorder=6,
                    bbox=dict(boxstyle="round,pad=0.25", fc="white", ec="none", alpha=0.85),
                )

    def phase_groups(self) -> List[Tuple[str, List[Dict[str, Any]]]]:
        order: List[str] = []
        groups: Dict[str, List[Dict[str, Any]]] = {}
        for s in self.samples:
            p = str(s.get("phase_name") or "").strip()
            if p not in groups:
                groups[p] = []
                order.append(p)
            groups[p].append(s)
        return [(p, groups[p]) for p in order]


# ---------------------------------------------------------------------------
# Chart system (light, consistent sizes/fonts/colours)
# ---------------------------------------------------------------------------
C_BLUE = "#1769D2"     # primary series (TX, run A, avg)
C_ORANGE = "#D46F00"   # second series (RX, run B, P99)
C_TEAL = "#0F9D8A"     # third series (sessions, P95, RAM)
C_VIOLET = "#8B5CF6"   # fourth series (CPS)
C_TARGET = "#94A3B8"
C_INK = "#334155"
C_MUTED = "#64748B"
C_GRID = "#E2E8F0"
C_AXIS = "#CBD5E1"
PHASE_FILL = "#E9F2FC"

CHART_DPI = 200
FULL_IMG_MM = 172.0
HALF_IMG_MM = 82.0
FULL_W_IN = FULL_IMG_MM / 25.4
HALF_W_IN = HALF_IMG_MM / 25.4

ChartImg = Tuple[io.BytesIO, float, float]  # (png, width_mm, height_mm)


def _style_ax(ax: Any) -> None:
    ax.set_facecolor("#FFFFFF")
    ax.tick_params(colors=C_MUTED, labelsize=7, length=2.5, width=0.6)
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)
    for sp in ("left", "bottom"):
        ax.spines[sp].set_color(C_AXIS)
        ax.spines[sp].set_linewidth(0.7)
    ax.grid(True, axis="y", color=C_GRID, lw=0.6)
    ax.grid(True, axis="x", color="#F1F5F9", lw=0.5)
    ax.set_axisbelow(True)
    ax.yaxis.set_major_locator(MaxNLocator(nbins=5, min_n_ticks=3))


# Backwards-compatible name
_style_light_axes = _style_ax


def _new_fig(w_in: float, h_in: float, nrows: int = 1, height_ratios: Optional[List[float]] = None) -> Tuple[Figure, List[Any]]:
    fig = Figure(figsize=(w_in, h_in), dpi=CHART_DPI, facecolor="#FFFFFF", layout="constrained")
    try:
        fig.get_layout_engine().set(w_pad=0.03, h_pad=0.03, hspace=0.06)
    except Exception:
        pass
    FigureCanvasAgg(fig)
    if nrows <= 1:
        axes = [fig.add_subplot(1, 1, 1)]
    else:
        axes = list(fig.subplots(nrows, 1, sharex=True, gridspec_kw={"height_ratios": height_ratios or [1] * nrows}))
    for ax in axes:
        _style_ax(ax)
    return fig, axes


def _fig_png(fig: Figure) -> ChartImg:
    buf = io.BytesIO()
    w_in, h_in = fig.get_size_inches()
    fig.savefig(buf, format="png", dpi=CHART_DPI, facecolor="#FFFFFF")
    fig.clf()
    buf.seek(0)
    return buf, float(w_in) * 25.4, float(h_in) * 25.4


def _legend_top(ax: Any, ncol: Optional[int] = None) -> None:
    h, lab = ax.get_legend_handles_labels()
    if not h:
        return
    ax.legend(
        h, lab, loc="lower left", bbox_to_anchor=(0.0, 1.0), ncol=ncol or len(h), frameon=False, fontsize=7,
        handlelength=1.8, columnspacing=1.3, borderaxespad=0.2, borderpad=0.1, labelcolor=C_INK,
    )


def _ylabel(ax: Any, text: str) -> None:
    ax.set_ylabel(text, color=C_INK, fontsize=7.5)


def _xlabel(ax: Any, text: str) -> None:
    ax.set_xlabel(text, color=C_MUTED, fontsize=7.5)


def _xlim(ax: Any, xs: np.ndarray) -> None:
    fin = xs[np.isfinite(xs)] if xs.size else xs
    if fin.size == 0:
        return
    lo, hi = float(fin.min()), float(fin.max())
    if hi - lo < 1e-9:
        lo, hi = lo - 0.5, hi + 0.5
    ax.set_xlim(lo, hi)


def _line_kw(n_points: int) -> Dict[str, Any]:
    # Single/sparse samples would be invisible as lines; show markers instead.
    return {"marker": "o", "markersize": 3} if n_points < 3 else {}


_count_fmt = FuncFormatter(lambda v, _p: f"{v:,.0f}")


def _bps_unit(maxv: float) -> Tuple[float, str]:
    if maxv >= 1e9:
        return 1e9, "Gbps"
    if maxv >= 1e5:
        return 1e6, "Mbps"
    return 1e3, "Kbps"


def _us_unit(maxv: float) -> Tuple[float, str]:
    return (1000.0, "ms") if maxv >= 5000 else (1.0, "µs")


def _chart_throughput(S: _TS, target_bps: float = 0.0, w_in: float = FULL_W_IN, h_in: float = 2.5, phase_labels: bool = True) -> Optional[ChartImg]:
    if S.n == 0 or not (S.has("tx_bps") or S.has("rx_bps")):
        return None
    has_tgt = S.has("target_bps")
    tgt_const = (not has_tgt) and target_bps > 0
    peak = max(_amax(S.col("tx_bps")), _amax(S.col("rx_bps")), _amax(S.col("target_bps")) if has_tgt else 0.0, target_bps if tgt_const else 0.0)
    div, unit = _bps_unit(peak)
    x, (tx, rx, tg) = S.xy(["tx_bps", "rx_bps", "target_bps"])
    fig, (ax,) = _new_fig(w_in, h_in)
    S.bands(ax, labels=phase_labels)
    kw = _line_kw(len(x))
    if S.has("tx_bps"):
        ax.plot(x, tx / div, color=C_BLUE, lw=2.6, label="TX", zorder=3, solid_capstyle="round", **kw)
    if S.has("rx_bps"):
        # thin RX drawn inside the wider TX line, so both stay visible when RX == TX (lossless runs)
        ax.plot(x, rx / div, color=C_ORANGE, lw=0.95, label="RX", zorder=4, **kw)
    if has_tgt:
        ax.plot(x, tg / div, color=C_TARGET, lw=1.0, ls=(0, (4, 3)), label="Target", zorder=2)
    elif tgt_const:
        ax.axhline(target_bps / div, color=C_TARGET, lw=1.0, ls=(0, (4, 3)), label="Target", zorder=2)
    ax.set_ylim(0, max(peak / div * 1.12, 1e-6))
    _xlim(ax, x)
    _ylabel(ax, f"Throughput ({unit})")
    _xlabel(ax, S.xlabel)
    _legend_top(ax)
    return _fig_png(fig)


def _chart_sparkline(S: _TS) -> Optional[ChartImg]:
    if S.n == 0 or not S.has("tx_bps"):
        return None
    div, unit = _bps_unit(_amax(S.col("tx_bps")))
    x, (tx,) = S.xy(["tx_bps"])
    fig = Figure(figsize=(FULL_W_IN, 0.9), dpi=CHART_DPI, facecolor="#FFFFFF")
    FigureCanvasAgg(fig)
    ax = fig.add_axes((0.0, 0.06, 1.0, 0.9))
    ax.set_facecolor("#FFFFFF")
    S.bands(ax)
    y = np.nan_to_num(tx / div)
    ax.plot(x, y, color=C_BLUE, lw=1.4, **_line_kw(len(x)))
    ax.fill_between(x, y, color=C_BLUE, alpha=0.12, lw=0)
    ax.set_ylim(0, max(float(y.max()) * 1.15 if y.size else 1.0, 1e-6))
    _xlim(ax, x)
    for sp in ax.spines.values():
        sp.set_visible(False)
    ax.axhline(0, color=C_AXIS, lw=0.8)
    ax.set_xticks([])
    ax.set_yticks([])
    return _fig_png(fig)


def _chart_pps(S: _TS, w_in: float = FULL_W_IN, h_in: float = 1.95) -> Optional[ChartImg]:
    if S.n == 0 or not (S.has("tx_pps") or S.has("rx_pps")):
        return None
    peak = max(_amax(S.col("tx_pps")), _amax(S.col("rx_pps")))
    div, unit = (1e6, "Mpps") if peak >= 1e6 else ((1e3, "Kpps") if peak >= 1e3 else (1.0, "pps"))
    x, (tx, rx) = S.xy(["tx_pps", "rx_pps"])
    fig, (ax,) = _new_fig(w_in, h_in)
    S.bands(ax)
    kw = _line_kw(len(x))
    if S.has("tx_pps"):
        ax.plot(x, tx / div, color=C_BLUE, lw=2.6, label="TX packets/s", zorder=3, solid_capstyle="round", **kw)
    if S.has("rx_pps"):
        ax.plot(x, rx / div, color=C_ORANGE, lw=0.95, label="RX packets/s", zorder=4, **kw)
    ax.set_ylim(0, max(peak / div * 1.12, 1e-6))
    _xlim(ax, x)
    _ylabel(ax, f"Packet rate ({unit})")
    _xlabel(ax, S.xlabel)
    _legend_top(ax)
    return _fig_png(fig)


def _chart_concurrency(S: _TS, w_in: float = FULL_W_IN, h_in: float = 2.75) -> Optional[ChartImg]:
    has_f, has_e, has_c = S.has("active_flows"), S.has("established_sessions"), S.has("cps")
    if S.n == 0 or not (has_f or has_e or has_c):
        return None
    panels = []
    if has_f or has_e:
        panels.append("flows")
    if has_c:
        panels.append("cps")
    if len(panels) == 1:
        h_in = min(h_in, 2.0)
    fig, axes = _new_fig(w_in, h_in, nrows=len(panels), height_ratios=[1.45, 1.0][: len(panels)])
    x, (fl, es, cps) = S.xy(["active_flows", "established_sessions", "cps"])
    kw = _line_kw(len(x))
    for ax, kind in zip(axes, panels):
        S.bands(ax)
        if kind == "flows":
            if has_f:
                ax.plot(x, fl, color=C_BLUE, lw=1.7, label="Active flows", zorder=3, **kw)
            if has_e:
                ax.plot(x, es, color=C_TEAL, lw=1.1, ls=(0, (4, 2)), label="Established TCP sessions", zorder=4, **kw)
            _ylabel(ax, "Concurrent")
            peak = max(_amax(S.col("active_flows")), _amax(S.col("established_sessions")))
        else:
            ax.plot(x, cps, color=C_VIOLET, lw=1.4, label="New connections per second (CPS)", zorder=3, **kw)
            ax.fill_between(x, np.nan_to_num(cps), color=C_VIOLET, alpha=0.08, lw=0)
            _ylabel(ax, "Connections/s")
            peak = _amax(S.col("cps"))
        ax.set_ylim(0, max(peak * 1.15, 1.0))
        ax.yaxis.set_major_formatter(_count_fmt)
        ax.yaxis.set_major_locator(MaxNLocator(nbins=4, min_n_ticks=3))
        _legend_top(ax)
    _xlim(axes[-1], x)
    _xlabel(axes[-1], S.xlabel)
    return _fig_png(fig)


def _chart_latency(S: _TS, w_in: float = FULL_W_IN, h_in: float = 2.3, legend_ncol: Optional[int] = None) -> Optional[ChartImg]:
    keys = [("lat_avg_us", "Average", C_BLUE, "-", 1.7), ("p95_lat_us", "P95", C_TEAL, (0, (4, 2)), 1.1), ("p99_lat_us", "P99", C_ORANGE, "-", 1.1)]
    present = [k for k in keys if S.has(k[0])]
    if S.n == 0 or not present:
        return None
    peak = max(_amax(S.col(k[0])) for k in present)
    div, unit = _us_unit(peak)
    x, ys = S.xy([k[0] for k in present])
    fig, (ax,) = _new_fig(w_in, h_in)
    S.bands(ax)
    kw = _line_kw(len(x))
    for (key, lbl, clr, ls, lw), y in zip(present, ys):
        ax.plot(x, y / div, color=clr, lw=lw, ls=ls, label=lbl, zorder=3, **kw)
    ax.set_ylim(0, max(peak / div * 1.15, 1e-6))
    _xlim(ax, x)
    _ylabel(ax, f"Latency ({unit})")
    _xlabel(ax, S.xlabel)
    _legend_top(ax, ncol=legend_ncol)
    return _fig_png(fig)


def _chart_latency_percentiles(summary: Dict[str, Any], w_in: float = HALF_W_IN, h_in: float = 2.15) -> Optional[ChartImg]:
    spec = [("Min", "lat_min_us"), ("Avg", "lat_avg_us"), ("P95", "p95_lat_us"), ("P99", "p99_lat_us"), ("Max", "lat_max_us")]
    vals = [(lbl, _f(summary.get(k))) for lbl, k in spec]
    vals = [(lbl, v) for lbl, v in vals if v is not None and v > 0]
    if len(vals) < 2:
        return None
    peak = max(v for _l, v in vals)
    div, unit = _us_unit(peak)
    fig, (ax,) = _new_fig(w_in, h_in)
    ax.grid(False, axis="x")
    xs = np.arange(len(vals))
    ys = [v / div for _l, v in vals]
    bars = ax.bar(xs, ys, width=0.58, color=C_BLUE, zorder=3)
    for b, (_l, v) in zip(bars, vals):
        ax.text(b.get_x() + b.get_width() / 2, b.get_height(), _fmt_us(v), ha="center", va="bottom", fontsize=6.5, color=C_INK)
    ax.set_xticks(xs)
    ax.set_xticklabels([lbl for lbl, _v in vals])
    ax.set_ylim(0, peak / div * 1.18)
    _ylabel(ax, f"Latency ({unit})")
    return _fig_png(fig)


def _chart_jitter_mos(S: _TS, w_in: float = FULL_W_IN, h_in: float = 2.6) -> Optional[ChartImg]:
    has_j, has_m = S.has("jitter_us"), S.has("mos_score")
    if S.n == 0 or not (has_j or has_m):
        return None
    panels = (["jitter"] if has_j else []) + (["mos"] if has_m else [])
    if len(panels) == 1:
        h_in = min(h_in, 1.9)
    fig, axes = _new_fig(w_in, h_in, nrows=len(panels))
    x, (jit, mos) = S.xy(["jitter_us", "mos_score"])
    kw = _line_kw(len(x))
    for ax, kind in zip(axes, panels):
        S.bands(ax)
        if kind == "jitter":
            div, unit = _us_unit(_amax(S.col("jitter_us")))
            ax.plot(x, jit / div, color=C_TEAL, lw=1.4, label="Jitter (inter-packet delay variation)", zorder=3, **kw)
            ax.set_ylim(0, max(_amax(S.col("jitter_us")) / div * 1.15, 1e-6))
            _ylabel(ax, f"Jitter ({unit})")
        else:
            mos_m = np.where(mos > 0, mos, np.nan)  # 0 = not computed for that second
            ax.plot(x, mos_m, color=C_BLUE, lw=1.6, label="Estimated MOS (simplified ITU-T G.107 E-model)", zorder=3, **kw)
            ax.axhline(4.0, color=C_TARGET, lw=0.8, ls=(0, (3, 3)), zorder=2)
            ax.text(1.0, 4.0, " 4.0", transform=blended_transform_factory(ax.transAxes, ax.transData), fontsize=6.5, color=C_MUTED, va="center", ha="left")
            ax.set_ylim(1.0, 5.0)
            ax.set_yticks([1, 2, 3, 4, 5])
            _ylabel(ax, "MOS (1-5)")
        _legend_top(ax)
    _xlim(axes[-1], x)
    _xlabel(axes[-1], S.xlabel)
    return _fig_png(fig)


def _chart_loss(S: _TS, w_in: float = FULL_W_IN, h_in: float = 2.45) -> Optional[ChartImg]:
    has_p, has_d = S.has("drop_pct"), S.has("dropped_packets")
    if S.n == 0 or not (has_p or has_d):
        return None
    panels = (["pct"] if has_p else []) + (["pkts"] if has_d else [])
    if len(panels) == 1:
        h_in = min(h_in, 1.9)
    fig, axes = _new_fig(w_in, h_in, nrows=len(panels))
    x, (pct, pk) = S.xy(["drop_pct", "dropped_packets"], how="max")
    kw = _line_kw(len(x))
    for ax, kind in zip(axes, panels):
        S.bands(ax)
        if kind == "pct":
            ax.plot(x, pct, color=C_ORANGE, lw=1.5, label="Cumulative packet loss (%)", zorder=3, **kw)
            ax.set_ylim(0, max(_amax(S.col("drop_pct")) * 1.15, 1e-6))
            ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _p: f"{v:.3g}%"))
            _ylabel(ax, "Loss (%)")
        else:
            ax.plot(x, pk, color=C_BLUE, lw=1.4, label="Dropped packets (cumulative)", zorder=3, **kw)
            ax.fill_between(x, np.nan_to_num(pk), color=C_BLUE, alpha=0.08, lw=0)
            ax.set_ylim(0, max(_amax(S.col("dropped_packets")) * 1.15, 1.0))
            ax.yaxis.set_major_formatter(_count_fmt)
            _ylabel(ax, "Packets")
        _legend_top(ax)
    _xlim(axes[-1], x)
    _xlabel(axes[-1], S.xlabel)
    return _fig_png(fig)


def _chart_resources(S: _TS, w_in: float = HALF_W_IN, h_in: float = 2.1) -> Optional[ChartImg]:
    if S.n == 0 or not (S.has("cpu_pct") or S.has("ram_pct")):
        return None
    x, (cpu, ram) = S.xy(["cpu_pct", "ram_pct"])
    fig, (ax,) = _new_fig(w_in, h_in)
    S.bands(ax)
    kw = _line_kw(len(x))
    if S.has("cpu_pct"):
        ax.plot(x, cpu, color=C_BLUE, lw=1.5, label="CPU", zorder=3, **kw)
    if S.has("ram_pct"):
        ax.plot(x, ram, color=C_TEAL, lw=1.2, ls=(0, (4, 2)), label="RAM", zorder=3, **kw)
    ax.set_ylim(0, 100)
    _xlim(ax, x)
    _ylabel(ax, "Utilisation (%)")
    _xlabel(ax, S.xlabel)
    _legend_top(ax)
    return _fig_png(fig)


def _gateway_series(run: Dict[str, Any], S: _TS) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Gateway CPU/RAM vs elapsed seconds, from UniFi polls (preferred) or per-sample fields."""
    us = [u for u in (run.get("unifi_samples") or []) if isinstance(u, dict)]
    t0 = _f(run.get("started_at"))
    if t0 is None and S.n:
        t0 = _f(S.samples[0].get("ts"))
    pts = []
    if us and t0 is not None:
        for u in us:
            ts = _f(u.get("ts"))
            c, m = _f(u.get("gw_cpu_pct")), _f(u.get("gw_mem_pct"))
            if ts is not None and (c is not None or m is not None):
                pts.append((ts - t0, c, m))
    if not pts:
        for xv, s in zip(S.x, S.samples):
            c, m = _f(s.get("unifi_gw_cpu")), _f(s.get("unifi_gw_mem"))
            if c is not None or m is not None:
                pts.append((float(xv), c, m))
    if not pts:
        e = np.array([], dtype=float)
        return e, e, e
    pts.sort(key=lambda p: p[0])
    arr = np.array([[p[0], np.nan if p[1] is None else p[1], np.nan if p[2] is None else p[2]] for p in pts], dtype=float)
    return arr[:, 0], arr[:, 1], arr[:, 2]


def _chart_gateway(run: Dict[str, Any], S: _TS, w_in: float = HALF_W_IN, h_in: float = 2.1) -> Optional[ChartImg]:
    t, cpu, mem = _gateway_series(run, S)
    if t.size == 0 or not (np.any(np.isfinite(cpu)) or np.any(np.isfinite(mem))):
        return None
    if t.size > MAX_PLOT_POINTS:
        starts = np.unique(np.linspace(0, t.size, MAX_PLOT_POINTS, endpoint=False).astype(int))
        t, cpu, mem = _bucket(t, starts), _bucket(cpu, starts), _bucket(mem, starts)
    xs = t / S.tdiv
    fig, (ax,) = _new_fig(w_in, h_in)
    S.bands(ax)
    kw = _line_kw(len(xs)) if len(xs) >= 3 else {"marker": "o", "markersize": 3}
    if np.any(np.isfinite(cpu)):
        ax.plot(xs, cpu, color=C_ORANGE, lw=1.5, label="Gateway CPU", zorder=3, **kw)
    if np.any(np.isfinite(mem)):
        ax.plot(xs, mem, color=C_TEAL, lw=1.2, ls=(0, (4, 2)), label="Gateway RAM", zorder=3, **kw)
    ax.set_ylim(0, 100)
    _xlim(ax, xs)
    _ylabel(ax, "Utilisation (%)")
    _xlabel(ax, S.xlabel)
    _legend_top(ax)
    return _fig_png(fig)


def _chart_workload_donut(mix: Dict[str, Any], w_in: float = HALF_W_IN, h_in: float = 2.15) -> ChartImg:
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
        lbl = meta["short_name"] if meta else ("Other workloads" if k == "other_combined" else str(k).replace("_", " ").title())
        clr = meta["color"] if meta else palette_fallback[idx % len(palette_fallback)]
        labels.append(f"{lbl}  ({val:.0f}%)")
        sizes.append(max(0.1, float(val)))
        clrs.append(clr)

    fig = Figure(figsize=(w_in, h_in), dpi=CHART_DPI, facecolor="#FFFFFF", layout="constrained")
    FigureCanvasAgg(fig)
    ax_pie, ax_leg = fig.subplots(1, 2, gridspec_kw={"width_ratios": [1.0, 1.25]})
    wedges, _ = ax_pie.pie(
        sizes, colors=clrs, startangle=90, counterclock=False,
        wedgeprops={"width": 0.36, "edgecolor": "#FFFFFF", "linewidth": 1.5},
    )
    ax_pie.text(0, 0, "Traffic\nmix", ha="center", va="center", fontsize=7, color=C_MUTED)
    ax_pie.axis("equal")
    ax_leg.axis("off")
    ax_leg.legend(wedges, labels, loc="center left", frameon=False, fontsize=6.8, labelcolor="#17243A", handlelength=1.0)
    return _fig_png(fig)


_FRAME_RE = re.compile(r"^(\d+)\s*B$")


def _rfc2544_matrix(S: _TS) -> List[Dict[str, Any]]:
    """Per-frame-size results, aggregated the same way main.py's sweep does (avg rates; latency/loss from the
    trial's last, post-drain sample)."""
    rows = []
    for p, grp in S.phase_groups():
        m = _FRAME_RE.match(p)
        if not m or not grp:
            continue
        last = grp[-1]

        def _avg(key: str) -> Optional[float]:
            vals = [v for v in (_f(s.get(key)) for s in grp) if v is not None]
            return (sum(vals) / len(vals)) if vals else None

        rows.append({
            "frame": int(m.group(1)),
            "tx_bps": _avg("tx_bps"),
            "rx_bps": _avg("rx_bps"),
            "rx_pps": _avg("rx_pps"),
            "lat_avg_us": _f(last.get("lat_avg_us")),
            "p99_lat_us": _f(last.get("p99_lat_us")),
            "jitter_us": _f(last.get("jitter_us")),
            "drop_pct": _f(last.get("drop_pct")),
            "seconds": len(grp),
        })
    rows.sort(key=lambda r: r["frame"])
    return rows


def _chart_rfc2544(rows: List[Dict[str, Any]], w_in: float = FULL_W_IN, h_in: float = 3.0) -> Optional[ChartImg]:
    if not rows or not any((r["rx_bps"] or 0) > 0 or (r["tx_bps"] or 0) > 0 for r in rows):
        return None
    has_lat = any((r["lat_avg_us"] or 0) > 0 or (r["p99_lat_us"] or 0) > 0 for r in rows)
    fig, axes = _new_fig(w_in, h_in if has_lat else 2.1, nrows=2 if has_lat else 1, height_ratios=[1.5, 1.0] if has_lat else None)
    xs = np.arange(len(rows))
    tx = np.array([(r["tx_bps"] or 0) / 1e6 for r in rows])
    rx = np.array([(r["rx_bps"] or 0) / 1e6 for r in rows])
    ax = axes[0]
    ax.grid(False, axis="x")
    ax.bar(xs - 0.2, tx, width=0.38, color=C_BLUE, label="Offered (TX)", zorder=3)
    ax.bar(xs + 0.2, rx, width=0.38, color=C_ORANGE, label="Throughput (RX)", zorder=3)
    ax.set_ylim(0, max(float(max(tx.max(), rx.max())) * 1.15, 1e-6))
    _ylabel(ax, "Mbps")
    _legend_top(ax)
    if has_lat:
        lax = axes[1]
        lat = np.array([(r["lat_avg_us"] or np.nan) for r in rows], dtype=float)
        p99 = np.array([(r["p99_lat_us"] or np.nan) for r in rows], dtype=float)
        div, unit = _us_unit(max(_amax(lat), _amax(p99)))
        lax.plot(xs, lat / div, color=C_BLUE, lw=1.5, marker="o", markersize=4, label="Average latency", zorder=3)
        if np.any(np.isfinite(p99)):
            lax.plot(xs, p99 / div, color=C_ORANGE, lw=1.2, marker="s", markersize=3.5, label="P99 latency", zorder=3)
        lax.set_ylim(0, max(max(_amax(lat), _amax(p99)) / div * 1.2, 1e-6))
        _ylabel(lax, f"Latency ({unit})")
        _legend_top(lax)
    axes[-1].set_xticks(xs)
    axes[-1].set_xticklabels([f"{r['frame']} B" for r in rows])
    axes[-1].set_xlim(-0.6, len(rows) - 0.4)
    _xlabel(axes[-1], "Frame size (bytes)")
    return _fig_png(fig)


def _chart_overlay(series: List[Tuple[_TS, str]], key: str, kind: str, w_in: float = FULL_W_IN, h_in: float = 2.15) -> Optional[ChartImg]:
    """Run A vs run B overlay of one metric. kind: 'bps' | 'us' | 'count'."""
    present = [(S, lbl) for S, lbl in series if S.n and S.has(key)]
    if not present:
        return None
    peak = max(_amax(S.col(key)) for S, _l in present)
    if kind == "bps":
        div, unit = _bps_unit(peak)
        ylab = f"RX throughput ({unit})"
    elif kind == "us":
        div, unit = _us_unit(peak)
        ylab = f"Average latency ({unit})"
    else:
        div, unit = 1.0, ""
        ylab = {"active_flows": "Active flows", "cps": "Connections/s", "established_sessions": "TCP sessions"}.get(key, key)
    span = max(float(S.x.max() - S.x.min()) for S, _l in present)
    tdiv, xlabel = _time_scale(span)
    fig, (ax,) = _new_fig(w_in, h_in)
    palette = [(C_BLUE, "-", 1.7), (C_ORANGE, "-", 1.3)]  # colour follows the run (A/B), not its rank
    lo, hi = None, None
    for idx, (S, lbl) in enumerate(series):
        if not (S.n and S.has(key)):
            continue
        clr, ls, lw = palette[idx % 2]
        x, (y,) = S.xy([key])
        x = x * S.tdiv / tdiv
        ax.plot(x, y / div, color=clr, lw=lw, ls=ls, label=lbl, zorder=3, **_line_kw(len(x)))
        if x.size:
            lo = float(np.nanmin(x)) if lo is None else min(lo, float(np.nanmin(x)))
            hi = float(np.nanmax(x)) if hi is None else max(hi, float(np.nanmax(x)))
    if lo is not None and hi is not None:
        ax.set_xlim(lo, hi if hi > lo else lo + 1)
    ax.set_ylim(0, max(peak / div * 1.15, 1e-6))
    if kind == "count":
        ax.yaxis.set_major_formatter(_count_fmt)
    _ylabel(ax, ylab)
    _xlabel(ax, xlabel)
    _legend_top(ax)
    return _fig_png(fig)


# ---------------------------------------------------------------------------
# Codeblue logo: the official artwork, traced to vector (frontend/static/brand/*.svg)
# and rendered to transparent PNGs (backend/assets/) because reportlab can't draw SVG.
# ---------------------------------------------------------------------------
_ASSETS_DIR = Path(__file__).resolve().parent / "assets"
LOGO_ASPECT = 1924.0 / 512.0  # width / height of the logo artwork


def draw_codeblue_logo(c: Any, x: float, y: float, height: float, on_dark: bool = False, with_tagline: bool = True) -> float:
    """Draw the codeblue logo with its bottom-left at (x, y); white lettering on dark backgrounds.
    Returns the drawn width (0 if the artwork file is missing)."""
    img = _ASSETS_DIR / ("codeblue-logo-white.png" if on_dark else "codeblue-logo.png")
    if not img.exists():
        return 0.0
    width = height * LOGO_ASPECT
    c.drawImage(str(img), x, y, width=width, height=height, mask="auto", preserveAspectRatio=True)
    return width

# ---------------------------------------------------------------------------
# Reusable PDF Building Blocks (KPI Cards, Callouts, NumberedCanvas)
# ---------------------------------------------------------------------------
class _ReportNumberedCanvas(canvas.Canvas):
    """Two-pass canvas rendering the dark navy header banner and exact 'XX / YY' page numbers."""

    def __init__(self, *args, run_label: str = "LIVE RECORDED RUN", footer_left: str = "", cover_line3: str = "TEST REPORT",
                 cover_lines: Tuple[str, str] = ("NETWORK", "PERFORMANCE"), banner_title: str = "NETWORK PERFORMANCE REPORT", **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states: List[Dict[str, Any]] = []
        self._run_label = run_label
        self._footer_left = footer_left or "CODEBLUE IT SERVICES  |  NETWORK PERFORMANCE REPORT"
        self._cover_line3 = cover_line3
        self._cover_lines = cover_lines
        self._banner_title = banner_title

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

            # Codeblue logo, top-right of the cover hero
            logo_h = 15 * mm
            logo_w = LOGO_ASPECT * logo_h
            draw_codeblue_logo(self, w - 16 * mm - logo_w, h - 14 * mm - logo_h, logo_h, on_dark=True)

            # Cover Title
            self.setFont("Helvetica-Bold", 26)
            self.drawString(16 * mm, h - 44 * mm, self._cover_lines[0])
            self.drawString(16 * mm, h - 55 * mm, self._cover_lines[1])
            self.setFont("Helvetica-Bold", 21)
            self.setFillColor(colors.HexColor("#85C6FF"))
            self.drawString(16 * mm, h - 65 * mm, self._cover_line3)

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
        self.drawString(16 * mm, h - 10.5 * mm, self._banner_title)
        self.setFillColor(colors.HexColor("#94A3B8"))
        self.setFont("Helvetica", 8)
        self.drawString(16 * mm, h - 16.5 * mm, "Codeblue IT Services  /  Network Test Studio")
        # Small codeblue wordmark on the right, run label underneath it
        logo_h = 9 * mm
        logo_w = LOGO_ASPECT * logo_h
        draw_codeblue_logo(self, w - 16 * mm - logo_w, h - 3.5 * mm - logo_h, logo_h, on_dark=True)
        self.setFillColor(colors.HexColor("#DBEAFE"))
        self.setFont("Helvetica-Bold", 7.5)
        self.drawRightString(w - 16 * mm, h - 19.5 * mm, self._run_label)

        # Content Pages Footer
        self.setStrokeColor(BORDER)
        self.setLineWidth(0.6)
        self.line(16 * mm, 15 * mm, w - 16 * mm, 15 * mm)
        self.setFillColor(TEXT_MUTED)
        self.setFont("Helvetica", 7.5)
        self.drawString(16 * mm, 10.5 * mm, self._footer_left)
        self.drawRightString(w - 16 * mm, 10.5 * mm, f"{page_num:02d} / {total_pages:02d}")


_SS = getSampleStyleSheet()


def _kpi_card_row(cards: List[Dict[str, Any]], total_width_mm: float = 178.0, value_size: float = 15.0, gap_mm: float = 4.0) -> Table:
    """A row of white KPI cards with coloured vertical accent bars."""
    n = max(1, len(cards))
    card_w = (total_width_mm - gap_mm * (n - 1)) / n
    lead = value_size + 1.5
    cell_tables = []
    for c in cards:
        accent = c.get("accent", "#1769D2")
        lbl = _esc(str(c.get("label", "")).upper())
        val = _esc(str(c.get("value", "-")))
        sub = _esc(str(c.get("sub", "")))
        val_clr = c.get("value_color", "#0F1D31")
        p = Paragraph(
            f"<font name='Helvetica-Bold' size='6.8' color='#64748B'>{lbl}</font><br/>"
            f"<font name='Helvetica-Bold' size='{value_size}' color='{val_clr}'>{val}</font><br/>"
            f"<font name='Helvetica' size='7' color='#64748B'>{sub}</font>",
            ParagraphStyle("kpicell", parent=_SS["Normal"], leading=lead * 0.86 if value_size > 12 else 12),
        )
        inner = Table([["", p]], colWidths=[1.6 * mm, (card_w - 1.6) * mm])
        inner.setStyle(
            TableStyle([
                ("BACKGROUND", (0, 0), (0, 0), colors.HexColor(accent)),
                ("BACKGROUND", (1, 0), (1, 0), colors.white),
                ("LEFTPADDING", (0, 0), (0, 0), 0),
                ("RIGHTPADDING", (0, 0), (0, 0), 0),
                ("LEFTPADDING", (1, 0), (1, 0), 7),
                ("RIGHTPADDING", (1, 0), (1, 0), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("BOX", (0, 0), (-1, -1), 0.7, BORDER),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ])
        )
        cell_tables.append(inner)

    col_widths = []
    row_items: List[Any] = []
    for idx, tbl in enumerate(cell_tables):
        row_items.append(tbl)
        col_widths.append(card_w * mm)
        if idx < n - 1:
            row_items.append("")
            col_widths.append(gap_mm * mm)

    outer = Table([row_items], colWidths=col_widths)
    outer.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0), ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    return outer


def _styled_table(rows: List[List[Any]], col_widths_mm: List[float], font_size: float = 8.0, pad: float = 4.2, hpad: float = 6.0) -> Table:
    cell_style = ParagraphStyle("tblc", parent=_SS["Normal"], fontName="Helvetica", fontSize=font_size, leading=font_size + 3, textColor=TEXT_MAIN)
    hdr_style = ParagraphStyle("tblh", parent=_SS["Normal"], fontName="Helvetica-Bold", fontSize=font_size, leading=font_size + 3, textColor=colors.white)

    formatted_rows = []
    for r_idx, row in enumerate(rows):
        formatted_rows.append([
            Paragraph(_esc(str(col)), hdr_style if r_idx == 0 else cell_style) if not isinstance(col, Paragraph) else col
            for col in row
        ])

    tbl = Table(formatted_rows, colWidths=[w * mm for w in col_widths_mm], repeatRows=1)
    tbl.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), NAVY),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, ROW_ALT]),
            ("LINEBELOW", (0, 1), (-1, -1), 0.5, BORDER),
            ("BOX", (0, 0), (-1, -1), 0.6, BORDER),
            ("TOPPADDING", (0, 0), (-1, -1), pad),
            ("BOTTOMPADDING", (0, 0), (-1, -1), pad),
            ("LEFTPADDING", (0, 0), (-1, -1), hpad),
            ("RIGHTPADDING", (0, 0), (-1, -1), hpad),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ])
    )
    return tbl


def _callout_box(title: str, body: str, tone: str = "info", width_mm: float = 178.0, body_is_markup: bool = False) -> Table:
    palettes = {
        "info": ("#EFF6FF", "#BFDBFE", "#1D4ED8", "#1E3A8A"),
        "pass": ("#ECFDF5", "#A7F3D0", "#15803D", "#065F46"),
        "fail": ("#FEF2F2", "#FECACA", "#DC2626", "#991B1B"),
        "warn": ("#FFFBEB", "#FDE68A", "#B45309", "#92400E"),
        "muted": ("#F8FAFC", "#E2E8F0", "#475569", "#475569"),
    }
    bg, brd, t_clr, b_clr = palettes.get(tone, palettes["info"])
    body_txt = str(body) if body_is_markup else _esc(str(body))
    p = Paragraph(
        f"<font name='Helvetica-Bold' size='8.2' color='{t_clr}'>{_esc(str(title))}</font><br/>"
        f"<font name='Helvetica' size='8' color='{b_clr}'>{body_txt}</font>",
        ParagraphStyle("callout", parent=_SS["Normal"], leading=11.5),
    )
    t = Table([[p]], colWidths=[width_mm * mm])
    t.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(bg)),
            ("BOX", (0, 0), (-1, -1), 0.7, colors.HexColor(brd)),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ("LEFTPADDING", (0, 0), (-1, -1), 9),
            ("RIGHTPADDING", (0, 0), (-1, -1), 9),
        ])
    )
    return t


def _chart_card(title: str, chart: Any, width_mm: float = 178.0, height_mm: Optional[float] = None, caption: Optional[str] = None) -> Table:
    """White bordered card: title (+ optional caption) above a chart image rendered at its true size."""
    if isinstance(chart, tuple):
        buf, w_mm, h_mm = chart
    else:  # legacy: bare BytesIO
        buf, w_mm, h_mm = chart, width_mm - 4, height_mm or 60.0
    hdr_txt = f"<font name='Helvetica-Bold' size='8.8' color='#0F1D31'>{_esc(title)}</font>"
    if caption:
        hdr_txt += f"<br/><font name='Helvetica' size='6.9' color='#64748B'>{_esc(caption)}</font>"
    hdr = Paragraph(hdr_txt, ParagraphStyle("cardh", parent=_SS["Normal"], leading=10))
    img = Image(buf, width=w_mm * mm, height=h_mm * mm)
    t = Table([[hdr], [img]], colWidths=[width_mm * mm])
    t.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.white),
            ("BOX", (0, 0), (-1, -1), 0.7, BORDER),
            ("TOPPADDING", (0, 0), (0, 0), 6),
            ("BOTTOMPADDING", (0, 0), (0, 0), 1),
            ("LEFTPADDING", (0, 0), (0, 0), 8),
            ("RIGHTPADDING", (0, 0), (0, 0), 8),
            ("TOPPADDING", (0, 1), (0, 1), 1),
            ("BOTTOMPADDING", (0, 1), (0, 1), 4),
            ("LEFTPADDING", (0, 1), (0, 1), 0),
            ("RIGHTPADDING", (0, 1), (0, 1), 0),
            ("ALIGN", (0, 1), (0, 1), "CENTER"),
        ])
    )
    return t


def _side_by_side(left: Any, right: Any, gap_mm: float = 4.0, total_mm: float = 178.0) -> Table:
    w = (total_mm - gap_mm) / 2
    t = Table([[left, "", right]], colWidths=[w * mm, gap_mm * mm, w * mm])
    t.setStyle(TableStyle([
        ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    return t


HALF_CARD_MM = 87.0


def _styles() -> Dict[str, ParagraphStyle]:
    s = _SS
    return {
        "h1": ParagraphStyle("PageH1", parent=s["Heading1"], fontName="Helvetica-Bold", fontSize=16, leading=19, textColor=NAVY, spaceBefore=9, spaceAfter=1),
        "sub": ParagraphStyle("PageSub", parent=s["Normal"], fontName="Helvetica", fontSize=8.6, leading=11.5, textColor=TEXT_MUTED, spaceAfter=6),
        "h2": ParagraphStyle("SecH2", parent=s["Heading2"], fontName="Helvetica-Bold", fontSize=10.5, leading=13, textColor=NAVY, spaceBefore=7, spaceAfter=4),
        "body": ParagraphStyle("BodyP", parent=s["Normal"], fontName="Helvetica", fontSize=8.6, leading=12.4, textColor=TEXT_MAIN, spaceAfter=4),
        "bullet": ParagraphStyle("BulletP", parent=s["Normal"], fontName="Helvetica", fontSize=8.6, leading=12.2, textColor=TEXT_MAIN, leftIndent=9, bulletIndent=0, spaceAfter=3),
        "meta_lbl": ParagraphStyle("MetaLbl", parent=s["Normal"], fontName="Helvetica-Bold", fontSize=6.8, leading=9, textColor=TEXT_MUTED),
        "meta_val": ParagraphStyle("MetaVal", parent=s["Normal"], fontName="Helvetica-Bold", fontSize=9.2, leading=11.5, textColor=NAVY),
        "eyebrow": ParagraphStyle("Eyebrow", parent=s["Normal"], fontName="Helvetica-Bold", fontSize=8, leading=10, textColor=BLUE, spaceBefore=2, spaceAfter=4),
        "note": ParagraphStyle("Note", parent=s["Normal"], fontName="Helvetica", fontSize=7.2, leading=9.5, textColor=TEXT_MUTED, spaceBefore=2, spaceAfter=2),
    }


def _section(story: List[Any], st: Dict[str, ParagraphStyle], title: str, sub: str, first: Any = None, need_mm: float = 95.0) -> None:
    """Start a section on the current page if there is room for its heading plus first block, else a new page."""
    story.append(CondPageBreak(need_mm * mm))
    head = [Paragraph(_esc(title), st["h1"]), Paragraph(_esc(sub), st["sub"])]
    if first is not None:
        head.append(first)
    story.append(KeepTogether(head))


# ---------------------------------------------------------------------------
# Report context (all derived values in one place; nothing hard-coded about hardware)
# ---------------------------------------------------------------------------
_ENGINE_LABELS = {
    "trex_astf": "Cisco TRex ASTF (stateful TCP/UDP)",
    "trex_stl": "Cisco TRex STL (stateless streams)",
    "internet_wan": "Live Internet / WAN multi-worker engine",
    "hybrid": "Hybrid: Cisco TRex + live Internet/WAN",
}
_MODE_LABELS = {
    "phased": "Phased (ramp-up / steady / ramp-down)",
    "timed": "Timed constant load",
    "step_ramp": "Step ramp",
    "soak": "Soak (long duration)",
    "continuous": "Continuous",
    "rfc2544_sweep": "RFC 2544-style frame-size sweep",
}


def _mos_band(m: float) -> str:
    # ITU-T G.107 user-satisfaction bands (R 90/80/70/60 -> MOS 4.34/4.03/3.60/3.10)
    if m >= 4.34:
        return "users very satisfied"
    if m >= 4.03:
        return "users satisfied"
    if m >= 3.60:
        return "some users dissatisfied"
    if m >= 3.10:
        return "many users dissatisfied"
    return "nearly all users dissatisfied"


def _int(v: Any) -> int:
    x = _f(v)
    return int(x) if x is not None else 0


def _build_ctx(run: Dict[str, Any], custom_title: Optional[str] = None, custom_client: Optional[str] = None) -> Dict[str, Any]:
    run = run or {}
    summary = _ensure_run_summary(run)
    cfg = run.get("config") or {}
    S = _TS(run.get("samples"))
    rid = _int(run.get("id"))
    started_ts = _f(run.get("started_at"))
    started_dt = datetime.datetime.fromtimestamp(started_ts) if started_ts else datetime.datetime.now()
    engine_code = str(run.get("traffic_engine") or cfg.get("traffic_engine") or "trex_astf")
    engine_label = _ENGINE_LABELS.get(engine_code, engine_code)
    if cfg.get("trex_version") and engine_code.startswith("trex"):
        engine_label += f" v{cfg.get('trex_version')}"
    test_mode = str(run.get("test_mode") or cfg.get("test_mode") or "")
    thresholds_configured = bool(summary.get("thresholds_configured"))
    verdict = str(summary.get("verdict") or run.get("verdict") or "COMPLETED").upper()
    if not thresholds_configured and verdict in ("PASS", "RECORDED"):
        verdict = "COMPLETED"
    topo = cfg.get("topology_snapshot") or {}
    if not isinstance(topo, dict):
        topo = {}
    loopback = engine_code in ("trex_astf", "trex_stl", "hybrid") and "loopback" in str(topo.get("active_mode_code") or "")

    target_bps = _f(cfg.get("base_target_bps")) or _f(cfg.get("target_bps")) or 0.0
    actual_s = _f(summary.get("actual_duration_sec")) or (float(S.x[-1] - S.x[0] + S.step) if S.n else 0.0) or _f(run.get("duration_sec")) or 0.0
    planned_s = None
    if test_mode == "phased":
        p = sum(_f(cfg.get(k)) or 0.0 for k in ("ramp_up_sec", "steady_sec", "ramp_down_sec"))
        planned_s = p or None
    elif test_mode == "step_ramp" and cfg.get("ramp_steps_pct") and _f(cfg.get("ramp_step_sec")):
        try:
            planned_s = len(cfg.get("ramp_steps_pct")) * float(cfg.get("ramp_step_sec"))
        except TypeError:
            planned_s = None
    elif test_mode in ("timed", "soak"):
        planned_s = _f(run.get("duration_sec")) or _f(cfg.get("steady_sec"))
    ended_early = bool(planned_s and actual_s and actual_s < planned_s * 0.9)

    if engine_code == "internet_wan":
        lat_method = "round-trip times measured by the Internet/WAN test workers"
    elif engine_code == "hybrid":
        lat_method = "TRex latency probes plus Internet/WAN worker round-trip times"
    else:
        lat_method = "timestamped TRex latency probe packets"

    sim_users = _int(run.get("simulated_users"))
    ctx = {
        "run": run, "summary": summary, "cfg": cfg, "S": S, "run_id": rid, "started_dt": started_dt,
        "title": custom_title,
        "project": custom_client or run.get("client_name") or cfg.get("client_name") or "Network performance validation",
        "dut": run.get("dut_name") or cfg.get("dut_name") or "Device under test (not specified)",
        "operator": run.get("operator_name") or cfg.get("operator_name") or "Not recorded",
        "profile": run.get("profile_name") or cfg.get("profile_name") or "Custom profile",
        "engine_code": engine_code, "engine_label": engine_label,
        "test_mode": test_mode, "mode_label": _MODE_LABELS.get(test_mode, test_mode.replace("_", " ").title() or "Not recorded"),
        "verdict": verdict, "thresholds_configured": thresholds_configured,
        "topo": topo, "loopback": loopback,
        "target_bps": target_bps,
        "avg_tx": _f(summary.get("avg_tx_bps")) or 0.0, "avg_rx": _f(summary.get("avg_rx_bps")) or 0.0,
        "max_tx": _f(summary.get("max_tx_bps")) or 0.0, "max_rx": _f(summary.get("max_rx_bps")) or 0.0,
        "drop_pct": _f(summary.get("drop_pct")) or 0.0,
        "dropped": _int(summary.get("total_dropped_packets")),
        "tx_packets": _int(summary.get("total_tx_packets")),
        "lat_avg": _f(summary.get("lat_avg_us")) or 0.0, "p95": _f(summary.get("p95_lat_us")) or 0.0,
        "p99": _f(summary.get("p99_lat_us")) or 0.0, "jitter": _f(summary.get("jitter_avg_us")) or 0.0,
        "mos": _f(summary.get("mos_avg")) or 0.0,
        "sim_users": sim_users,
        "client_ips": _int(summary.get("emulated_client_ips") or cfg.get("emulated_client_ips")) or sim_users,
        "peak_flows": _int(summary.get("peak_active_flows")), "peak_est": _int(summary.get("peak_established_sessions")),
        "peak_cps": _f(summary.get("peak_cps")) or 0.0, "avg_cps": _f(summary.get("avg_cps")) or 0.0,
        "actual_s": actual_s, "planned_s": planned_s, "ended_early": ended_early,
        "lat_method": lat_method,
        "telemetry_source": summary.get("telemetry_source") or "",
        "unifi_samples": run.get("unifi_samples") or [], "snmp_samples": run.get("snmp_samples") or [],
        "is_sweep": test_mode == "rfc2544_sweep",
    }
    if not ctx["mos"] and S.has("mos_score"):  # older summaries lack mos_avg: average the measured per-second estimates
        m = S.col("mos_score")
        m = m[np.isfinite(m) & (m > 0)]
        ctx["mos"] = float(m.mean()) if m.size else 0.0
    ctx["pct_of_target"] = (ctx["avg_tx"] / target_bps * 100.0) if target_bps > 0 else None
    ctx["phases"] = [p for p, _g in S.phase_groups()]
    steady = [s for s in S.samples if str(s.get("phase_name") or "") == "steady"]
    if steady and len(set(ctx["phases"])) > 1:
        ctx["steady_S"], ctx["steady_label"] = _TS(steady), f"steady phase only ({len(steady)} samples)"
    else:
        ctx["steady_S"], ctx["steady_label"] = S, f"entire run ({S.n} samples; no separate steady phase recorded)"
    return ctx


def _nanstats(a: np.ndarray) -> Optional[Tuple[float, float, float, float, int]]:
    a = a[np.isfinite(a)] if a.size else a
    if a.size == 0:
        return None
    return float(a.mean()), float(a.min()), float(a.max()), float(a.std()), int(a.size)


def _steady_stats_rows(S: _TS) -> List[List[str]]:
    spec = [
        ("TX throughput", "tx_bps", _fmt_bps),
        ("RX throughput", "rx_bps", _fmt_bps),
        ("TX packet rate", "tx_pps", _fmt_pps),
        ("Average latency", "lat_avg_us", _fmt_us),
        ("P99 latency", "p99_lat_us", _fmt_us),
        ("Jitter", "jitter_us", _fmt_us),
        ("Active flows", "active_flows", lambda v: f"{v:,.0f}"),
        ("Established TCP sessions", "established_sessions", lambda v: f"{v:,.0f}"),
        ("New connections/s", "cps", lambda v: f"{v:,.0f}"),
        ("Estimated MOS", "mos_score", lambda v: f"{v:.2f}"),
        ("Generator CPU", "cpu_pct", lambda v: f"{v:.1f}%"),
    ]
    rows = [["Metric", "Mean", "Min", "Max", "Std dev"]]
    for lbl, key, fmt in spec:
        if not S.has(key):
            continue
        a = S.col(key)
        if key == "mos_score":
            a = np.where(a > 0, a, np.nan)
        st = _nanstats(a)
        if not st:
            continue
        mean, mn, mx, sd, _n = st

        def _fz(v: float) -> str:
            return fmt(v) if v > 0 else "0"

        sd_txt = _fz(sd) if fmt is not _fmt_us else (_fmt_us(sd) if sd > 0 else "0")
        rows.append([lbl, _fz(mean), _fz(mn), _fz(mx), sd_txt])
    return rows if len(rows) > 1 else []


def _phase_table_rows(S: _TS) -> List[List[str]]:
    groups = S.phase_groups()
    if len(groups) < 2:
        return []
    has_flows = S.has("active_flows")
    has_cps = S.has("cps")
    hdr = ["Phase", "Duration", "Avg TX", "Avg RX", "Avg latency"] + (["Peak flows"] if has_flows else []) + (["Peak CPS"] if has_cps else [])
    rows = [hdr]
    for p, grp in groups:
        G = _TS(grp)

        def _mean(k: str) -> Optional[float]:
            st = _nanstats(G.col(k))
            return st[0] if st else None

        lat = _mean("lat_avg_us")
        row = [_phase_label(p), _fmt_duration(len(grp) * S.step), _fmt_bps(_mean("tx_bps") or 0), _fmt_bps(_mean("rx_bps") or 0), _fmt_us(lat)]
        if has_flows:
            row.append(f"{_amax(G.col('active_flows')):,.0f}")
        if has_cps:
            row.append(f"{_amax(G.col('cps')):,.0f}")
        rows.append(row)
    return rows


def _plain_findings(ctx: Dict[str, Any]) -> List[str]:
    """Plain-English findings derived only from recorded values (returns reportlab markup)."""
    out: List[str] = []
    S: _TS = ctx["S"]
    if S.n == 0 and not ctx["avg_tx"]:
        out.append("No telemetry samples were recorded for this run, so there are no measured results to interpret.")
        return out
    tgt = ""
    if ctx["pct_of_target"] is not None:
        tgt = f" against a configured target of {_fmt_bps(ctx['target_bps'])} ({ctx['pct_of_target']:.0f}% of target)"
    out.append(f"<b>Throughput:</b> the test averaged <b>{_fmt_bps(ctx['avg_tx'])}</b> transmitted and {_fmt_bps(ctx['avg_rx'])} received, peaking at {_fmt_bps(max(ctx['max_tx'], ctx['max_rx']))}{tgt}.")
    SS: _TS = ctx["steady_S"]
    if SS is not S and SS.has("tx_bps"):
        st = _nanstats(SS.col("tx_bps"))
        if st and st[0] > 0:
            cv = st[3] / st[0] * 100.0
            out.append(f"<b>Stability:</b> during the steady phase throughput averaged {_fmt_bps(st[0])} and varied by {cv:.1f}% (standard deviation {_fmt_bps(st[3])}).")
    if ctx["dropped"] > 0 or ctx["drop_pct"] > 0:
        out.append(f"<b>Packet loss:</b> {ctx['dropped']:,} packets were lost ({ctx['drop_pct']:.4f}% of traffic).")
    elif ctx["tx_packets"] > 0:
        out.append(f"<b>Packet loss:</b> no packets were lost ({ctx['tx_packets']:,} packets sent).")
    if ctx["lat_avg"] > 0:
        p99 = f"; 99% of measurements were at or below <b>{_fmt_us(ctx['p99'])}</b>" if ctx["p99"] > 0 else ""
        out.append(f"<b>Latency:</b> average delay was <b>{_fmt_us(ctx['lat_avg'])}</b>{p99} (measured with {_esc(ctx['lat_method'])}).")
    if ctx["mos"] > 0:
        jit = f" with {_fmt_us(ctx['jitter'])} average jitter" if ctx["jitter"] > 0 else ""
        out.append(f"<b>Voice quality (estimate):</b> estimated MOS {ctx['mos']:.2f} of 4.5{jit}; on the ITU-T G.107 scale this corresponds to {_mos_band(ctx['mos'])}. This is a calculated estimate, not a listening test.")
    if ctx["peak_flows"] or ctx["peak_cps"]:
        users = f" from {ctx['sim_users']:,} simulated users" if ctx["sim_users"] else ""
        out.append(f"<b>Scale:</b> up to <b>{ctx['peak_flows']:,}</b> concurrent flows ({ctx['peak_est']:,} established TCP sessions) and a peak of <b>{ctx['peak_cps']:,.0f}</b> new connections per second{users}.")
    if S.has("cpu_pct"):
        out.append(f"<b>Test generator load:</b> host CPU peaked at {_amax(S.col('cpu_pct')):.1f}% and RAM at {_amax(S.col('ram_pct')):.1f}% (whole-host averages).")
    if ctx["ended_early"]:
        out.append(f"<b>Run length:</b> the run recorded {_fmt_duration(ctx['actual_s'])} of a planned {_fmt_duration(ctx['planned_s'])}"
                   + ("; the steady phase was never reached, so results reflect ramp-up only." if ctx["test_mode"] == "phased" and "steady" not in ctx["phases"] else "."))
    return out


def _next_steps(ctx: Dict[str, Any]) -> List[str]:
    out = []
    if ctx["loopback"]:
        out.append(f"Cable two test ports through {_esc(ctx['dut'])} and repeat the test so traffic actually traverses the device.")
    if ctx["ended_early"]:
        out.append("Re-run for the full planned duration to capture a complete steady-state window.")
    if not ctx["thresholds_configured"]:
        out.append("Configure acceptance thresholds (minimum throughput, maximum loss and latency) so future runs produce a PASS/FAIL verdict.")
    if not ctx["unifi_samples"] and not ctx["S"].has("unifi_gw_cpu"):
        out.append("Connect the read-only UniFi Network API so gateway CPU/RAM is recorded alongside the traffic.")
    if ctx["drop_pct"] > 0.1:
        out.append("Investigate the packet loss: compare against gateway CPU and interface error counters, then re-test at a lower rate to find the loss-free point.")
    return out


# ---------------------------------------------------------------------------
# Story sections
# ---------------------------------------------------------------------------
def _story_cover(story: List[Any], st: Dict[str, ParagraphStyle], ctx: Dict[str, Any], exec_mode: bool) -> None:
    run = ctx["run"]
    story.append(Spacer(1, 55 * mm))
    banner_title = ctx["title"] or (run.get("name") or f"Network performance test - {ctx['dut']}")
    sub_bits = []
    if ctx["sim_users"]:
        sub_bits.append(f"{ctx['sim_users']:,} simulated users")
    if ctx["target_bps"] > 0:
        sub_bits.append(f"target {_fmt_bps(ctx['target_bps'])}")
    sub_bits.append(str(ctx["profile"]))
    cover_card = Table(
        [[Paragraph(
            f"<font name='Helvetica-Bold' size='12.5' color='#0F1D31'>{_esc(banner_title)}</font><br/>"
            f"<font name='Helvetica' size='8.6' color='#64748B'>{_esc('  |  '.join(sub_bits))}</font>",
            ParagraphStyle("covb", parent=_SS["Normal"], leading=15),
        )]],
        colWidths=[178 * mm],
    )
    cover_card.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F8FAFC")),
        ("BOX", (0, 0), (-1, -1), 0.8, BORDER),
        ("LINEBEFORE", (0, 0), (0, -1), 3, colors.HexColor("#85C6FF")),
        ("TOPPADDING", (0, 0), (-1, -1), 9),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ("LEFTPADDING", (0, 0), (-1, -1), 11),
        ("RIGHTPADDING", (0, 0), (-1, -1), 11),
    ]))
    story.append(cover_card)
    story.append(Spacer(1, 5 * mm))

    dur = _fmt_duration(ctx["actual_s"])
    if ctx["ended_early"]:
        dur += f" (of {_fmt_duration(ctx['planned_s'])} planned)"
    fields = [
        ("PROJECT", ctx["project"]), ("DEVICE UNDER TEST", ctx["dut"]),
        ("TEST ID  |  OPERATOR", f"RUN-{ctx['started_dt'].strftime('%Y%m%d')}-{ctx['run_id']:04d}  |  {ctx['operator']}"), ("TEST DATE", ctx["started_dt"].strftime("%d %B %Y, %H:%M")),
        ("TRAFFIC ENGINE", ctx["engine_label"]), ("TEST MODE  |  DURATION", f"{ctx['mode_label']}  |  {dur}"),
    ]
    cells = []
    for i in range(0, len(fields), 2):
        row = []
        for k, v in fields[i:i + 2]:
            row.append([Paragraph(_esc(k), st["meta_lbl"]), Paragraph(_esc(v), st["meta_val"])])
        cells.append(row)
    meta = Table(cells, colWidths=[89 * mm, 89 * mm])
    meta.setStyle(TableStyle([
        ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    story.append(meta)
    story.append(Spacer(1, 3 * mm))

    # ---- Results at a glance ------------------------------------------------
    story.append(Paragraph("RESULTS AT A GLANCE", st["eyebrow"]))
    verdict = ctx["verdict"]
    v_accent = "#15803D" if verdict == "PASS" else ("#DC2626" if verdict == "FAIL" else "#64748B")
    tp_sub = f"Peak {_fmt_bps(max(ctx['max_tx'], ctx['max_rx']))}"
    if ctx["pct_of_target"] is not None:
        tp_sub += f"  |  {ctx['pct_of_target']:.0f}% of target"
    if ctx["sim_users"] and ctx["peak_flows"]:
        scale_val, scale_sub = f"{ctx['sim_users']:,} users", f"{ctx['peak_flows']:,} peak flows  |  {ctx['peak_cps']:,.0f} CPS"
    elif ctx["sim_users"]:
        scale_val, scale_sub = f"{ctx['sim_users']:,} users", f"{ctx['client_ips']:,} client IPs"
    elif ctx["peak_flows"]:
        scale_val, scale_sub = f"{ctx['peak_flows']:,} flows", "Peak concurrent flows"
    else:
        scale_val, scale_sub = "N/A", "No user or flow counts recorded"
    loss_ok = ctx["drop_pct"] <= 0.05
    tiles1 = [
        {"label": "Average throughput", "value": _fmt_bps(ctx["avg_tx"]) if ctx["avg_tx"] else "N/A", "sub": tp_sub, "accent": "#1769D2"},
        {"label": "Average latency", "value": _fmt_us(ctx["lat_avg"]), "sub": f"P95 {_fmt_us(ctx['p95'])}" if ctx["p95"] else "Not measured" if not ctx["lat_avg"] else "", "accent": "#1769D2"},
        {"label": "P99 latency", "value": _fmt_us(ctx["p99"]), "sub": f"Jitter avg {_fmt_us(ctx['jitter'])}" if ctx["jitter"] else "", "accent": "#1769D2"},
    ]
    tiles2 = [
        {"label": "Packet loss", "value": f"{ctx['drop_pct']:.4f}%" if (ctx["tx_packets"] or ctx["drop_pct"]) else "N/A", "sub": f"{ctx['dropped']:,} of {ctx['tx_packets']:,} packets", "accent": "#15803D" if loss_ok else "#DC2626"},
        {"label": "Scale", "value": scale_val, "sub": scale_sub, "accent": "#85C6FF"},
        {"label": "Outcome", "value": verdict, "sub": "Thresholds evaluated" if ctx["thresholds_configured"] else "No pass/fail thresholds set", "accent": v_accent,
         "value_color": "#15803D" if verdict == "PASS" else ("#DC2626" if verdict == "FAIL" else "#0F1D31")},
    ]
    story.append(_kpi_card_row(tiles1, value_size=14.5))
    story.append(Spacer(1, 3 * mm))
    story.append(_kpi_card_row(tiles2, value_size=14.5))
    story.append(Spacer(1, 3 * mm))
    spark = _chart_sparkline(ctx["S"])
    if spark:
        S = ctx["S"]
        cap = f"Transmitted throughput, 0 to {_fmt_duration(S.x[-1] - S.x[0] + S.step)}"
        if len(set(ctx["phases"])) > 1:
            cap += "; shaded bands mark test phases"
        story.append(_chart_card("Throughput over time", spark, caption=cap))
        story.append(Spacer(1, 3 * mm))

    if ctx["loopback"]:
        story.append(_callout_box(
            "TEST PATH: INTERNAL LOOPBACK",
            f"The topology snapshot saved with this run records the path as \"{ctx['topo'].get('active_mode_label') or ctx['topo'].get('active_mode_code')}\". "
            f"In this mode traffic loops inside the test generator and does not pass through {ctx['dut']}, so the figures describe the test path, not the device's forwarding capacity.",
            tone="warn",
        ))
    else:
        src = ctx["telemetry_source"] or ctx["engine_label"]
        n = ctx["S"].n
        story.append(_callout_box(
            "MEASUREMENT PROVENANCE",
            f"All figures come from {n:,} recorded one-second samples ({src}). Charts are drawn only from measured values; metrics that were not recorded are omitted."
            if n else "No per-second telemetry samples were stored for this run; only the run summary is available.",
            tone="info",
        ))
    story.append(PageBreak())


def _acceptance_table(ctx: Dict[str, Any]) -> Table:
    checks = ctx["summary"].get("threshold_checks") or []
    if ctx["thresholds_configured"] and checks:
        rows = [["Metric", "Requirement", "Measured", "Outcome"]]
        for ch in checks:
            rows.append([ch.get("metric", ""), ch.get("requirement", ""), ch.get("actual", ""), ch.get("outcome", "")])
        return _styled_table(rows, [56, 44, 44, 34])
    rows = [
        ["Metric", "Threshold", "Measured", "Status"],
        ["Average RX throughput", "Not configured", _fmt_bps(ctx["avg_rx"]), "RECORDED"],
        ["Packet loss", "Not configured", f"{ctx['drop_pct']:.4f}%", "RECORDED"],
        ["Average / P99 latency", "Not configured", f"{_fmt_us(ctx['lat_avg'])} / {_fmt_us(ctx['p99'])}", "RECORDED"],
    ]
    if ctx["peak_flows"] or ctx["peak_est"]:
        rows.append(["Peak flows / TCP sessions", "Not configured", f"{ctx['peak_flows']:,} / {ctx['peak_est']:,}", "RECORDED"])
    return _styled_table(rows, [56, 40, 52, 30])


def _story_exec_summary(story: List[Any], st: Dict[str, ParagraphStyle], ctx: Dict[str, Any]) -> None:
    run = ctx["run"]
    story.append(Paragraph("Executive summary", st["h1"]))
    story.append(Paragraph(_esc(f"Run #{ctx['run_id']}: {run.get('name') or ''}  |  {_fmt_duration(ctx['actual_s'])}  |  {ctx['profile']}"), st["sub"]))

    verdict = ctx["verdict"]
    tone = "pass" if verdict == "PASS" else ("fail" if verdict == "FAIL" else "info")
    head = f"{verdict}: configured acceptance thresholds evaluated" if ctx["thresholds_configured"] else f"{verdict}: recorded benchmark (no pass/fail thresholds configured)"
    verb = "targeted" if ctx["loopback"] else "exercised"
    body = (
        f"This test {verb} <b>{_esc(ctx['dut'])}</b> using <b>{_esc(ctx['engine_label'])}</b>"
        + (f" with <b>{ctx['sim_users']:,} simulated users</b> ({ctx['client_ips']:,} client IP addresses)" if ctx["sim_users"] else "")
        + (f". Across {ctx['S'].n:,} recorded one-second intervals it transmitted an average of <b>{_fmt_bps(ctx['avg_tx'])}</b> "
           f"(peak {_fmt_bps(ctx['max_tx'])}) and recorded <b>{ctx['drop_pct']:.4f}%</b> counter-derived packet loss."
           if (ctx["S"].n or ctx["avg_tx"]) else ". No telemetry samples or traffic counters were recorded for this run.")
    )
    story.append(_callout_box(head, body, tone=tone, body_is_markup=True))

    story.append(Paragraph("Key findings", st["h2"]))
    for line in _plain_findings(ctx):
        story.append(Paragraph(line, st["bullet"], bulletText="•"))

    story.append(Paragraph("Acceptance criteria", st["h2"]))
    story.append(_acceptance_table(ctx))
    if ctx["peak_flows"] or ctx["sim_users"]:
        story.append(Spacer(1, 3 * mm))
        story.append(_callout_box(
            "USERS, CLIENT IPS, FLOWS AND SESSIONS ARE COUNTED SEPARATELY",
            f"Simulated users ({ctx['sim_users']:,}) and client IPs ({ctx['client_ips']:,}) are configured; active L4 flows (peak {ctx['peak_flows']:,}) and established TCP sessions (peak {ctx['peak_est']:,}) are measured. "
            "Simulated users do not all hold a connection at the same instant, so peak flows are normally far lower than the user count.",
            tone="muted",
        ))


def _story_config(story: List[Any], st: Dict[str, ParagraphStyle], ctx: Dict[str, Any]) -> None:
    run, cfg = ctx["run"], ctx["cfg"]
    rows = [["Parameter", "Configured value"]]
    rows.append(["Test ID & name", f"RUN-{ctx['run_id']:04d}  |  {run.get('name') or ''}"])
    rows.append(["Profile", f"{ctx['profile']}" + (f"  ({run.get('profile_id')})" if run.get("profile_id") else "")])
    rows.append(["Traffic engine & mode", f"{ctx['engine_label']}  |  {ctx['mode_label']}"])
    if ctx["test_mode"] == "phased":
        rows.append(["Phases (planned)", f"Ramp-up {_int(cfg.get('ramp_up_sec'))} s  /  Steady {_int(cfg.get('steady_sec'))} s  /  Ramp-down {_int(cfg.get('ramp_down_sec'))} s"])
    elif ctx["test_mode"] == "step_ramp" and cfg.get("ramp_steps_pct"):
        rows.append(["Step plan", f"{', '.join(str(x) for x in cfg.get('ramp_steps_pct') or [])} % of target, {cfg.get('ramp_step_sec')} s each"])
    rows.append(["Recorded duration", _fmt_duration(ctx["actual_s"]) + (f" (planned {_fmt_duration(ctx['planned_s'])})" if ctx["planned_s"] else "")])
    if ctx["target_bps"] > 0:
        cap = f"  ({_f(run.get('target_rate_pct')):g}% of {cfg.get('link_capacity_mbps')} Mbps link reference)" if (_f(run.get("target_rate_pct")) and cfg.get("link_capacity_mbps")) else ""
        rows.append(["Target rate", _fmt_bps(ctx["target_bps"]) + cap])
    if ctx["sim_users"]:
        ip_rng = f"  ({cfg.get('src_ip_start')} - {cfg.get('src_ip_end')})" if cfg.get("src_ip_start") and cfg.get("src_ip_end") else ""
        rows.append(["Simulated population", f"{ctx['sim_users']:,} users  |  {ctx['client_ips']:,} client IPs{ip_rng}"])
    l2 = []
    if cfg.get("frame_size"):
        l2.append(f"avg frame {cfg.get('frame_size')} B")
    if cfg.get("tcp_pct") is not None and cfg.get("udp_pct") is not None:
        l2.append(f"TCP {cfg.get('tcp_pct')}% / UDP {cfg.get('udp_pct')}%")
    if "vlan_id" in cfg:
        l2.append(f"VLAN {cfg.get('vlan_id') or 'untagged'}")
    if "dscp" in cfg:
        l2.append(f"DSCP {cfg.get('dscp')}")
    if cfg.get("direction"):
        l2.append(str(cfg.get("direction")))
    if l2:
        rows.append(["Frames & marking", "  |  ".join(l2)])

    env = [["Item", "Recorded for this run"]]
    env.append(["Device under test", ctx["dut"]])
    env.append(["Traffic engine", ctx["engine_label"]])
    topo = ctx["topo"]
    if topo.get("active_mode_label") or topo.get("active_mode_code"):
        env.append(["Test path (topology snapshot)", topo.get("active_mode_label") or topo.get("active_mode_code")])
    if ctx["telemetry_source"]:
        env.append(["Measurement source", ctx["telemetry_source"]])
    n_u, n_s = len(ctx["unifi_samples"]), len(ctx["snmp_samples"])
    env.append(["UniFi gateway telemetry", f"{n_u:,} polls captured" if n_u else "Not connected during this run"])
    env.append(["SNMP interface counters", f"{n_s:,} polls captured" if n_s else "Not polled during this run"])

    _section(story, st, "Test configuration", "Run settings and measurement environment as recorded with the run", None, need_mm=60)
    story.append(_styled_table(rows, [50, 128]))
    story.append(Spacer(1, 3 * mm))
    story.append(KeepTogether([Paragraph("Measurement environment", st["h2"]), _styled_table(env, [50, 128])]))
    note = topo.get("limitation_summary") or topo.get("honest_10g_explanation")
    if note:
        story.append(Spacer(1, 2.5 * mm))
        story.append(_callout_box("HARDWARE DISCOVERY NOTE (RECORDED AT RUN START)", note, tone="muted"))

    mix = cfg.get("protocol_mix") or {}
    if mix and isinstance(mix, dict):
        story.append(Spacer(1, 3 * mm))
        donut = _chart_card("Configured application mix", _chart_workload_donut(mix), width_mm=HALF_CARD_MM, caption="Share of traffic per synthetic workload (normalised to 100%)")
        tpl = ((cfg.get("astf_meta") or {}).get("templates") or []) if isinstance(cfg.get("astf_meta"), dict) else []
        if tpl:
            t_rows = [["Workload", "Proto / port", "Share"]]
            for t in tpl[:10]:
                meta = WORKLOAD_MAP.get(t.get("key")) or {}
                t_rows.append([meta.get("short_name") or str(t.get("key") or "").replace("_", " "), f"{t.get('proto', '')} {t.get('port', '')}", f"{_f(t.get('weight_pct')) or 0:.0f}%"])
            right: Any = [_styled_table(t_rows, [40, 27, 20], font_size=7.3, pad=2.6)]
        else:
            right = []
        right.append(Paragraph(
            "Application names describe synthetic workload characteristics (packet sizes, TCP/UDP behaviour, burst sizes, DSCP marking); "
            "they do not log in to or run the real commercial services.", st["note"]))
        story.append(KeepTogether([Paragraph("Traffic workload", st["h2"]), _side_by_side(donut, right)]))


def _story_rfc2544(story: List[Any], st: Dict[str, ParagraphStyle], ctx: Dict[str, Any]) -> None:
    rows = _rfc2544_matrix(ctx["S"])
    if not rows:
        story.append(_callout_box("FRAME-SIZE SWEEP", "No per-frame-size samples were recorded for this sweep.", tone="muted"))
        return
    chart = _chart_rfc2544(rows)
    first = _chart_card("Throughput and latency per frame size", chart, caption="Bars: average offered (TX) and forwarded (RX) rate per trial. Latency and loss are read from each trial's final sample.") if chart else None
    _section(story, st, "Frame-size sweep results", f"RFC 2544-style sweep across {len(rows)} frame sizes", first, need_mm=120)
    m = [["Frame size", "Offered (TX)", "Throughput (RX)", "Packet rate", "Avg latency", "P99 latency", "Loss"]]
    for r in rows:
        m.append([f"{r['frame']} B", _fmt_bps(r["tx_bps"] or 0), _fmt_bps(r["rx_bps"] or 0), _fmt_pps(r["rx_pps"] or 0), _fmt_us(r["lat_avg_us"]), _fmt_us(r["p99_lat_us"]), f"{(r['drop_pct'] or 0):.4f}%"])
    story.append(Spacer(1, 3 * mm))
    story.append(KeepTogether([Paragraph("Frame-size results matrix", st["h2"]), _styled_table(m, [22, 26, 28, 24, 26, 26, 26], font_size=7.6, pad=3.2)]))


def _story_throughput(story: List[Any], st: Dict[str, ParagraphStyle], ctx: Dict[str, Any]) -> None:
    S = ctx["S"]
    tp = _chart_throughput(S, ctx["target_bps"])
    if not tp:
        _section(story, st, "Throughput & packet rate", "Transmitted and received traffic over the test window",
                 _callout_box("NO THROUGHPUT SAMPLES", "No per-second throughput was recorded for this run, so no throughput charts are shown.", tone="muted"), need_mm=40)
        return
    cap = "TX = sent by the generator, RX = received back"
    if len(set(ctx["phases"])) > 1:
        cap += "; shaded bands mark test phases"
    if S.n > MAX_PLOT_POINTS:
        cap += f"; {S.n:,} samples averaged into {MAX_PLOT_POINTS:,} plot points"
    _section(story, st, "Throughput & packet rate", "Transmitted and received traffic over the test window", _chart_card("Throughput over time (TX / RX / target)", tp, caption=cap), need_mm=100)
    pp = _chart_pps(S)
    if pp:
        story.append(Spacer(1, 3 * mm))
        story.append(_chart_card("Packet rate over time", pp, caption="Packets per second sent (TX) and received (RX)"))
    rows = [
        ["Measurement", "Average", "Peak"],
        ["Transmitted (TX)", _fmt_bps(ctx["avg_tx"]), _fmt_bps(ctx["max_tx"])],
        ["Received (RX)", _fmt_bps(ctx["avg_rx"]), _fmt_bps(ctx["max_rx"])],
        ["TX packet rate", _fmt_pps(_f(ctx["summary"].get("avg_tx_pps")) or 0), _fmt_pps(_f(ctx["summary"].get("max_tx_pps")) or 0)],
    ]
    if ctx["target_bps"] > 0:
        rows.append(["Configured target", _fmt_bps(ctx["target_bps"]), f"{ctx['pct_of_target']:.1f}% achieved (avg TX)"])
    story.append(Spacer(1, 3 * mm))
    story.append(_styled_table(rows, [60, 59, 59]))


def _story_concurrency(story: List[Any], st: Dict[str, ParagraphStyle], ctx: Dict[str, Any]) -> None:
    S = ctx["S"]
    ch = _chart_concurrency(S)
    summ = ctx["summary"]
    if not ch:
        reason = "stateless STL streams do not open TCP sessions" if ctx["engine_code"] == "trex_stl" else "the engine did not report flow/session counters"
        story.append(CondPageBreak(30 * mm))
        story.append(Paragraph("Concurrency & connection rate", st["h2"]))
        story.append(_callout_box("NO SESSION COUNTERS RECORDED", f"No active-flow, session or connection-rate data was recorded for this run ({reason}).", tone="muted"))
        return
    _section(story, st, "Concurrency & connection rate", "Concurrent flows, established TCP sessions and new connections per second",
             _chart_card("Concurrency over time", ch, caption="Top: concurrent active flows and established TCP sessions. Bottom: new connections opened per second."), need_mm=110)
    rows = [["Measurement", "Recorded value"]]
    if ctx["sim_users"]:
        rows.append(["Simulated users / client IPs", f"{ctx['sim_users']:,} / {ctx['client_ips']:,}"])
    rows.append(["Peak active flows", f"{ctx['peak_flows']:,}"])
    rows.append(["Peak established TCP sessions", f"{ctx['peak_est']:,}"])
    rows.append(["Connections per second (avg / peak)", f"{ctx['avg_cps']:,.0f} / {ctx['peak_cps']:,.0f}"])
    rows.append(["TCP connects / drops / retransmits", f"{_int(summ.get('total_tcp_connects')):,} / {_int(summ.get('total_tcp_drops')):,} / {_int(summ.get('total_tcp_retransmits')):,}"])
    story.append(Spacer(1, 3 * mm))
    story.append(_styled_table(rows, [80, 98]))


def _story_latency(story: List[Any], st: Dict[str, ParagraphStyle], ctx: Dict[str, Any]) -> None:
    S, summ = ctx["S"], ctx["summary"]
    lat = _chart_latency(S)
    pct = _chart_latency_percentiles(summ)
    jm = _chart_jitter_mos(S)
    if not (lat or pct or jm):
        story.append(CondPageBreak(30 * mm))
        story.append(Paragraph("Latency & voice quality", st["h2"]))
        story.append(_callout_box("NO LATENCY MEASUREMENTS", "No latency, jitter or MOS values were recorded for this run.", tone="muted"))
        return
    cap = f"Measured with {ctx['lat_method']}"
    if ctx["engine_code"].startswith("trex") or ctx["engine_code"] == "hybrid":
        cap += "; P95/P99 come from TRex histogram buckets, so they move in bucket steps"
    first = _chart_card("Latency over time (average / P95 / P99)", lat, caption=cap) if lat else None
    _section(story, st, "Latency & voice quality", "Forwarding delay, tail latency, jitter and estimated call quality", first, need_mm=100)

    rows = [["Metric", "Value"],
            ["Minimum / average", f"{_fmt_us(_f(summ.get('lat_min_us')))} / {_fmt_us(ctx['lat_avg'])}"],
            ["P95 / P99", f"{_fmt_us(ctx['p95'])} / {_fmt_us(ctx['p99'])}"],
            ["Maximum", _fmt_us(_f(summ.get("lat_max_us")))],
            ["Average jitter", _fmt_us(ctx["jitter"])],
            ["Estimated MOS", f"{ctx['mos']:.2f} / 4.5" if ctx["mos"] > 0 else "N/A"]]
    tbl = _styled_table(rows, [37, 50], font_size=7.6, pad=3.4)
    story.append(Spacer(1, 3 * mm))
    if pct:
        story.append(KeepTogether([_side_by_side(_chart_card("Latency percentiles (whole run)", pct, width_mm=HALF_CARD_MM), tbl)]))
    else:
        story.append(KeepTogether([_styled_table(rows, [60, 118])]))
    if jm:
        story.append(Spacer(1, 3 * mm))
        story.append(_chart_card(
            "Jitter and estimated MOS over time", jm,
            caption="MOS is an estimate from a simplified ITU-T G.107 E-model (G.711 assumptions) using measured latency, jitter and loss; 4.0 = users satisfied.",
        ))


def _story_loss(story: List[Any], st: Dict[str, ParagraphStyle], ctx: Dict[str, Any]) -> None:
    S = ctx["S"]
    ch = _chart_loss(S)
    if not ch:
        story.append(CondPageBreak(30 * mm))
        story.append(Paragraph("Packet loss", st["h2"]))
        if ctx["tx_packets"] > 0:
            story.append(_callout_box("NO PACKET LOSS RECORDED", f"0 of {ctx['tx_packets']:,} transmitted packets were dropped during this run, so no loss chart is shown.", tone="pass"))
        else:
            story.append(_callout_box("NO LOSS COUNTERS RECORDED", "Packet counters were not recorded for this run.", tone="muted"))
        return
    sub = ("Packet counters reset for each frame-size trial; per-trial loss is listed in the frame-size results matrix" if ctx["is_sweep"]
           else f"{ctx['dropped']:,} packets dropped ({ctx['drop_pct']:.4f}%) out of {ctx['tx_packets']:,} transmitted")
    _section(story, st, "Packet loss", sub,
             _chart_card("Packet loss over time", ch, caption="Derived from TX/RX counters. Counters are read while traffic is flowing, so packets still in flight can briefly appear as loss."), need_mm=90)


def _story_steady(story: List[Any], st: Dict[str, ParagraphStyle], ctx: Dict[str, Any]) -> None:
    rows = _steady_stats_rows(ctx["steady_S"])
    prow = [] if ctx["is_sweep"] else _phase_table_rows(ctx["S"])
    if not rows and not prow:
        return
    # The table may split across pages (header row repeats), so only the heading is kept with it.
    _section(story, st, "Steady-state statistics", f"Computed from every recorded sample in the {ctx['steady_label']}", None, need_mm=60)
    if rows:
        story.append(_styled_table(rows, [50, 32, 32, 32, 32], font_size=7.8, pad=3.4))
    if prow:
        n = len(prow[0])
        w0, w1 = 30, 22
        rest = (178 - w0 - w1) / (n - 2)
        story.append(Spacer(1, 3 * mm))
        story.append(KeepTogether([Paragraph("Per-phase breakdown", st["h2"]), _styled_table(prow, [w0, w1] + [rest] * (n - 2), font_size=7.6, pad=3.2)]))


def _story_resources(story: List[Any], st: Dict[str, ParagraphStyle], ctx: Dict[str, Any]) -> None:
    S, run = ctx["S"], ctx["run"]
    gen = _chart_resources(S)
    gw = _chart_gateway(run, S)
    if not gen and not gw:
        story.append(CondPageBreak(30 * mm))
        story.append(Paragraph("Resource utilisation", st["h2"]))
        story.append(_callout_box("NO RESOURCE TELEMETRY", "Neither generator nor gateway CPU/RAM was recorded for this run.", tone="muted"))
        return
    gen_card = _chart_card("Test generator CPU / RAM", gen, width_mm=HALF_CARD_MM, caption="Whole-host utilisation of the traffic generator") if gen else None
    if gw:
        gw_card = _chart_card("Gateway CPU / RAM (UniFi)", gw, width_mm=HALF_CARD_MM, caption="Polled from the read-only UniFi Network API")
    else:
        gw_card = _callout_box(
            "GATEWAY TELEMETRY NOT CONNECTED",
            "UniFi gateway CPU/RAM was not recorded during this run, so the gateway chart is omitted. Nothing has been estimated in its place. "
            "Connect a read-only UniFi Network API key to record it on future runs.",
            tone="muted", width_mm=HALF_CARD_MM,
        )
    block = _side_by_side(gen_card, gw_card) if gen_card else _chart_card("Gateway CPU / RAM (UniFi)", _chart_gateway(run, S, w_in=FULL_W_IN), caption="Polled from the read-only UniFi Network API")
    _section(story, st, "Resource utilisation", "Load on the test generator and, when connected, the gateway", block, need_mm=85)

    us = [u for u in ctx["unifi_samples"] if isinstance(u, dict)]
    if us:
        last = us[-1]
        cpu = [v for v in (_f(u.get("gw_cpu_pct")) for u in us) if v is not None]
        mem = [v for v in (_f(u.get("gw_mem_pct")) for u in us) if v is not None]
        wan = [(_f(u.get("wan_rx_bps")) or 0) + (_f(u.get("wan_tx_bps")) or 0) for u in us if u.get("wan_rx_bps") is not None or u.get("wan_tx_bps") is not None]
        rows = [["UniFi observation", "Recorded value"],
                ["Gateway", f"{last.get('gw_name') or 'Gateway'}{(' (' + str(last.get('gw_model')) + ')') if last.get('gw_model') else ''}  |  {'online' if last.get('gw_online') else 'offline / unknown'}"],
                ["Gateway CPU (avg / peak)", f"{sum(cpu) / len(cpu):.1f}% / {max(cpu):.1f}%" if cpu else "Not reported"],
                ["Gateway RAM (avg / peak)", f"{sum(mem) / len(mem):.1f}% / {max(mem):.1f}%" if mem else "Not reported"],
                ["Peak WAN rate (RX + TX)", _fmt_bps(max(wan)) if wan else "Not reported"],
                ["Switches / APs online", f"{_int(last.get('switches_online'))}/{_int(last.get('switches_total'))}  |  {_int(last.get('aps_online'))}/{_int(last.get('aps_total'))}"],
                ["Polls captured", f"{len(us):,}"]]
        story.append(Spacer(1, 3 * mm))
        story.append(_styled_table(rows, [60, 118]))


def _story_findings(story: List[Any], st: Dict[str, ParagraphStyle], ctx: Dict[str, Any]) -> None:
    steps = _next_steps(ctx)
    _section(story, st, "Limitations & next steps", "Methodology caveats and recommended follow-up", None, need_mm=45)
    lim = [
        "Synthetic application profiles reproduce realistic packet sizes, burst patterns and TCP/UDP session behaviour; they do not run real commercial services, logins or encryption handshakes.",
        "Packet loss is derived from generator TX/RX counters; latency and jitter come from " + _esc(ctx["lat_method"]) + ". Gateway metrics are only shown when they were actually polled.",
        "Estimated MOS uses a simplified ITU-T G.107 E-model and is a calculated indicator of voice quality, not a subjective listening test.",
    ]
    if ctx["loopback"]:
        lim.insert(0, "<b>Test path:</b> this run used the internal loopback path recorded in the topology snapshot, so the device under test was not in the traffic path.")
    if ctx["ended_early"]:
        lim.insert(0, f"<b>Partial run:</b> {_fmt_duration(ctx['actual_s'])} of a planned {_fmt_duration(ctx['planned_s'])} were recorded.")
    for line in lim:
        story.append(Paragraph(line, st["bullet"], bulletText="•"))
    if steps:
        story.append(Paragraph("Recommended next steps", st["h2"]))
        for i, line in enumerate(steps, 1):
            story.append(Paragraph(line, st["bullet"], bulletText=f"{i}."))


# ---------------------------------------------------------------------------
# Technical (full) & Executive (3-page) PDF generator
# ---------------------------------------------------------------------------
def generate_pdf_bytes(
    run: Dict[str, Any],
    report_type: str = "technical",
    custom_title: Optional[str] = None,
    custom_client: Optional[str] = None,
) -> bytes:
    """
    Generate a client-ready light-mode PDF report.
    report_type: 'technical' (full engineering report) | 'executive' (3-page summary).
    """
    buf = io.BytesIO()
    ctx = _build_ctx(run or {}, custom_title, custom_client)
    st = _styles()
    run_id = ctx["run_id"]
    exec_mode = report_type == "executive"
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=16 * mm,
        rightMargin=16 * mm,
        topMargin=30 * mm,
        bottomMargin=20 * mm,
        title=custom_title or f"Codeblue Network Performance Report - Run #{run_id}",
        author="Codeblue IT Services",
    )
    story: List[Any] = []
    _story_cover(story, st, ctx, exec_mode)

    if exec_mode:
        _story_executive_pages(story, st, ctx)
        label = f"EXECUTIVE REPORT  |  RUN #{run_id}"
        footer = f"CODEBLUE IT SERVICES  |  RUN #{run_id} EXECUTIVE SUMMARY"
        line3 = "EXECUTIVE SUMMARY"
    else:
        _story_exec_summary(story, st, ctx)
        _story_config(story, st, ctx)
        if ctx["is_sweep"]:
            _story_rfc2544(story, st, ctx)
        _story_throughput(story, st, ctx)
        _story_concurrency(story, st, ctx)
        _story_latency(story, st, ctx)
        _story_loss(story, st, ctx)
        _story_steady(story, st, ctx)
        _story_resources(story, st, ctx)
        _story_findings(story, st, ctx)
        label = f"RUN #{run_id}  |  {ctx['verdict']}"
        footer = f"CODEBLUE IT SERVICES  |  RUN #{run_id} - {str(ctx['dut']).upper()[:40]}"
        line3 = "TEST REPORT"

    doc.build(
        story,
        canvasmaker=lambda *a, **kw: _ReportNumberedCanvas(*a, run_label=label, footer_left=footer, cover_line3=line3, **kw),
    )
    buf.seek(0)
    return buf.getvalue()


def _story_executive_pages(story: List[Any], st: Dict[str, ParagraphStyle], ctx: Dict[str, Any]) -> None:
    S, run = ctx["S"], ctx["run"]
    # ---- Page 2: dense results summary -------------------------------------
    story.append(Paragraph("Results summary", st["h1"]))
    story.append(Paragraph(_esc(f"Run #{ctx['run_id']}: {run.get('name') or ''}  |  {_fmt_duration(ctx['actual_s'])}  |  {ctx['engine_label']}"), st["sub"]))
    tiles = [
        {"label": "Received (avg)", "value": _fmt_bps(ctx["avg_rx"]) if ctx["avg_rx"] else "N/A", "sub": f"{(ctx['avg_rx'] / ctx['avg_tx'] * 100):.1f}% of sent" if ctx["avg_tx"] else "", "accent": "#1769D2"},
        {"label": "Packets sent", "value": f"{ctx['tx_packets']:,}" if ctx["tx_packets"] else "N/A", "sub": f"{ctx['dropped']:,} lost", "accent": "#15803D" if ctx["drop_pct"] <= 0.05 else "#DC2626"},
        ({"label": "Peak conn./s", "value": f"{ctx['peak_cps']:,.0f}", "sub": f"{ctx['peak_est']:,} peak TCP sessions", "accent": "#85C6FF"} if ctx["peak_cps"] else
         {"label": "Average jitter", "value": _fmt_us(ctx["jitter"]), "sub": f"P99 latency {_fmt_us(ctx['p99'])}", "accent": "#85C6FF"}),
        {"label": "Est. voice MOS", "value": f"{ctx['mos']:.2f}" if ctx["mos"] else "N/A", "sub": _mos_band(ctx["mos"]) if ctx["mos"] else "Not computed", "accent": "#1769D2"},
    ]
    story.append(_kpi_card_row(tiles, value_size=13))
    story.append(Spacer(1, 3 * mm))
    sweep_rows = _rfc2544_matrix(S) if ctx["is_sweep"] else []
    tp = _chart_rfc2544(sweep_rows, h_in=2.3) if sweep_rows else None
    if tp:
        story.append(_chart_card("Throughput and latency per frame size", tp, caption="Offered (TX) vs forwarded (RX) rate per frame-size trial, with average/P99 latency"))
        story.append(Spacer(1, 1 * mm))
        story.append(Spacer(1, 3 * mm))
    else:
        tp = _chart_throughput(S, ctx["target_bps"], h_in=2.3)
        if tp:
            cap = "TX = sent, RX = received" + ("; shaded bands mark test phases" if len(set(ctx["phases"])) > 1 else "")
            story.append(_chart_card("Throughput over time", tp, caption=cap))
            story.append(Spacer(1, 3 * mm))
    lat = _chart_latency(S, w_in=HALF_W_IN, h_in=2.4)
    # Second (half-width) and third (full-width) charts: first available of concurrency / loss / jitter+MOS.
    candidates = [
        ("conc", "Concurrency over time", "Active flows / TCP sessions and new connections per second", _chart_concurrency),
        ("loss", "Packet loss over time", "Derived from TX/RX counters; in-flight packets can briefly appear as loss", _chart_loss),
        ("voice", "Jitter and estimated MOS over time", "MOS: simplified ITU-T G.107 E-model estimate from measured latency, jitter and loss", _chart_jitter_mos),
    ]
    has_data = {
        "conc": any(S.has(k) for k in ("active_flows", "established_sessions", "cps")),
        "loss": S.has("drop_pct") or S.has("dropped_packets"),
        "voice": S.has("jitter_us") or S.has("mos_score"),
    }
    avail = [c for c in candidates if has_data[c[0]]] if S.n else []
    second = second_title = second_cap = None
    if avail:
        _k, second_title, second_cap, fn = avail[0]
        second = fn(S, w_in=HALF_W_IN, h_in=2.4)
    third = avail[1] if len(avail) > 1 else None
    cards = []
    if lat:
        cards.append(_chart_card("Latency over time", lat, width_mm=HALF_CARD_MM, caption="Average, P95 and P99"))
    if second:
        cards.append(_chart_card(second_title, second, width_mm=HALF_CARD_MM, caption=second_cap))
    if len(cards) == 2:
        story.append(_side_by_side(cards[0], cards[1]))
    elif len(cards) == 1:
        story.append(_side_by_side(cards[0], _callout_box("NOTE", "Only the measured charts are shown; other metrics were not recorded for this run.", tone="muted", width_mm=HALF_CARD_MM)))
    if third:
        _k, t_title, t_cap, fn = third
        story.append(Spacer(1, 3 * mm))
        story.append(_chart_card(t_title, fn(S, w_in=FULL_W_IN, h_in=1.75), caption=t_cap))
    if not (tp or cards):
        story.append(_callout_box("NO TIME-SERIES DATA", "No per-second samples were recorded for this run, so no charts are shown.", tone="muted"))
    story.append(PageBreak())

    # ---- Page 3: what it means ---------------------------------------------
    story.append(Paragraph("What this means", st["h1"]))
    story.append(Paragraph("Plain-English findings, acceptance criteria and recommended next steps", st["sub"]))
    verdict = ctx["verdict"]
    tone = "pass" if verdict == "PASS" else ("fail" if verdict == "FAIL" else "info")
    head = f"Outcome: {verdict}" + ("" if ctx["thresholds_configured"] else " (no pass/fail thresholds were configured)")
    story.append(_callout_box(head, f"{_esc(ctx['dut'])} was tested with {_esc(ctx['engine_label'])}"
                              + (f" and {ctx['sim_users']:,} simulated users" if ctx["sim_users"] else "") + f" for {_fmt_duration(ctx['actual_s'])}.", tone=tone, body_is_markup=True))
    story.append(Paragraph("Findings", st["h2"]))
    for line in _plain_findings(ctx):
        story.append(Paragraph(line, st["bullet"], bulletText="•"))
    story.append(Paragraph("Acceptance criteria", st["h2"]))
    story.append(_acceptance_table(ctx))
    steps = _next_steps(ctx)
    if steps:
        story.append(Paragraph("Recommended next steps", st["h2"]))
        for i, line in enumerate(steps, 1):
            story.append(Paragraph(line, st["bullet"], bulletText=f"{i}."))
    if ctx["loopback"]:
        story.append(Spacer(1, 2 * mm))
        story.append(_callout_box("IMPORTANT: TEST PATH", f"This run used the internal loopback path recorded in the topology snapshot, so traffic did not pass through {ctx['dut']}. Treat the figures as a test-path baseline, not as the device's capacity.", tone="warn"))


# ---------------------------------------------------------------------------
# Side-by-Side Comparison PDF Report
# ---------------------------------------------------------------------------
def generate_comparison_pdf_bytes(comp: Dict[str, Any]) -> bytes:
    """Light-mode comparison PDF for two recorded runs: delta table plus overlaid throughput/latency/flows charts."""
    buf = io.BytesIO()
    ra = comp.get("run_a") or {}
    rb = comp.get("run_b") or {}
    ca, cb = _build_ctx(ra), _build_ctx(rb)
    deltas = comp.get("deltas") or {}
    ida, idb = ca["run_id"], cb["run_id"]
    st = _styles()

    doc = SimpleDocTemplate(
        buf, pagesize=A4, leftMargin=16 * mm, rightMargin=16 * mm, topMargin=30 * mm, bottomMargin=20 * mm,
        title=f"Comparison Report - Run #{ida} vs Run #{idb}", author="Codeblue IT Services",
    )
    story: List[Any] = []

    # ---- Cover --------------------------------------------------------------
    story.append(Spacer(1, 55 * mm))
    card = Table([[Paragraph(
        f"<font name='Helvetica-Bold' size='12.5' color='#0F1D31'>Run #{ida} (baseline) vs Run #{idb} (comparison)</font><br/>"
        f"<font name='Helvetica' size='8.6' color='#64748B'>{_esc(ra.get('name') or '')}  vs  {_esc(rb.get('name') or '')}</font>",
        ParagraphStyle("covc", parent=_SS["Normal"], leading=15))]], colWidths=[178 * mm])
    card.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F8FAFC")), ("BOX", (0, 0), (-1, -1), 0.8, BORDER),
        ("LINEBEFORE", (0, 0), (0, -1), 3, colors.HexColor("#85C6FF")),
        ("TOPPADDING", (0, 0), (-1, -1), 9), ("BOTTOMPADDING", (0, 0), (-1, -1), 10), ("LEFTPADDING", (0, 0), (-1, -1), 11),
    ]))
    story.append(card)
    story.append(Spacer(1, 5 * mm))

    def _dpct(key: str) -> str:
        d = deltas.get(key) or {}
        p = d.get("delta_pct")
        v = d.get("delta")
        if p is not None:
            return f"{p:+.1f}%"
        if v is not None and v != 0:
            return f"{v:+,.2f}"
        return "No change" if v == 0 else "-"

    story.append(Paragraph("HEADLINE CHANGES (RUN B VS RUN A)", st["eyebrow"]))
    story.append(_kpi_card_row([
        {"label": "Avg RX throughput", "value": _dpct("avg_rx_mbps"), "sub": f"{_fmt_bps(ca['avg_rx'])} -> {_fmt_bps(cb['avg_rx'])}", "accent": "#1769D2"},
        {"label": "Avg latency", "value": _dpct("lat_avg_us"), "sub": f"{_fmt_us(ca['lat_avg'])} -> {_fmt_us(cb['lat_avg'])}", "accent": "#1769D2"},
        {"label": "Packet loss", "value": f"{cb['drop_pct'] - ca['drop_pct']:+.4f} pts", "sub": f"{ca['drop_pct']:.4f}% -> {cb['drop_pct']:.4f}%", "accent": "#15803D" if cb["drop_pct"] <= ca["drop_pct"] else "#DC2626"},
        {"label": "Peak flows", "value": _dpct("peak_active_flows"), "sub": f"{ca['peak_flows']:,} -> {cb['peak_flows']:,}", "accent": "#85C6FF"},
    ], value_size=13))
    story.append(Spacer(1, 5 * mm))
    ident = [["", f"Run #{ida} (A, baseline)", f"Run #{idb} (B, comparison)"]]
    for lbl, fn in [
        ("Name", lambda c: c["run"].get("name") or ""),
        ("Date", lambda c: c["started_dt"].strftime("%d %b %Y, %H:%M")),
        ("Profile", lambda c: c["profile"]),
        ("Engine / mode", lambda c: f"{c['engine_label']}  |  {c['mode_label']}"),
        ("Simulated users", lambda c: f"{c['sim_users']:,}"),
        ("Recorded duration", lambda c: _fmt_duration(c["actual_s"])),
        ("Test path", lambda c: (c["topo"].get("active_mode_label") or "Not recorded")),
    ]:
        ident.append([lbl, fn(ca), fn(cb)])
    story.append(_styled_table(ident, [34, 72, 72], font_size=7.8, pad=3.4))
    if ca["loopback"] or cb["loopback"]:
        story.append(Spacer(1, 3 * mm))
        story.append(_callout_box("TEST PATH", "At least one of these runs used the internal loopback path recorded in its topology snapshot, so its traffic did not pass through the device under test.", tone="warn"))
    if ca["test_mode"] != cb["test_mode"] or ca["profile"] != cb["profile"]:
        story.append(Spacer(1, 3 * mm))
        story.append(_callout_box("NOT LIKE-FOR-LIKE", "The two runs used different profiles and/or test modes; differences reflect the test design as well as the network.", tone="muted"))
    story.append(PageBreak())

    # ---- Delta table + throughput overlay ---------------------------------
    story.append(Paragraph("Side-by-side results", st["h1"]))
    story.append(Paragraph(f"Run #{ida} ({ca['sim_users']:,} users) vs Run #{idb} ({cb['sim_users']:,} users); delta = B - A", st["sub"]))

    def _fmt_d(key: str, unit: str = "", digits: int = 2) -> str:
        d = deltas.get(key) or {}
        val = d.get("delta")
        pct = d.get("delta_pct")
        if val is None:
            return "-"
        pct_s = f" ({pct:+.1f}%)" if pct is not None else ""
        return f"{val:+,.{digits}f}{unit}{pct_s}"

    sa, sb = ca["summary"], cb["summary"]
    rows = [
        ["Metric", f"Run #{ida} (A)", f"Run #{idb} (B)", "Delta (B - A)"],
        ["Simulated users", f"{ca['sim_users']:,}", f"{cb['sim_users']:,}", f"{cb['sim_users'] - ca['sim_users']:+,}"],
        ["Average TX throughput", _fmt_bps(ca["avg_tx"]), _fmt_bps(cb["avg_tx"]), _fmt_d("avg_tx_mbps", " Mbps")],
        ["Average RX throughput", _fmt_bps(ca["avg_rx"]), _fmt_bps(cb["avg_rx"]), _fmt_d("avg_rx_mbps", " Mbps")],
        ["Peak RX throughput", _fmt_bps(ca["max_rx"]), _fmt_bps(cb["max_rx"]), _fmt_d("max_rx_mbps", " Mbps")],
        ["Average TX packet rate", _fmt_pps(_f(sa.get("avg_tx_pps")) or 0), _fmt_pps(_f(sb.get("avg_tx_pps")) or 0), _fmt_d("avg_tx_pps", " pps", 0)],
        ["Packet loss", f"{ca['drop_pct']:.4f}%", f"{cb['drop_pct']:.4f}%", _fmt_d("drop_pct", " pts", 4)],
        ["Average latency", _fmt_us(ca["lat_avg"]), _fmt_us(cb["lat_avg"]), _fmt_d("lat_avg_us", " µs")],
        ["P99 latency", _fmt_us(ca["p99"]), _fmt_us(cb["p99"]), _fmt_d("p99_lat_us", " µs")],
        ["Average jitter", _fmt_us(ca["jitter"]), _fmt_us(cb["jitter"]), _fmt_d("jitter_avg_us", " µs")],
        ["Peak active flows", f"{ca['peak_flows']:,}", f"{cb['peak_flows']:,}", _fmt_d("peak_active_flows", "", 0)],
        ["Peak established TCP", f"{ca['peak_est']:,}", f"{cb['peak_est']:,}", _fmt_d("peak_established_sessions", "", 0)],
        ["Peak connections/s", f"{ca['peak_cps']:,.0f}", f"{cb['peak_cps']:,.0f}", _fmt_d("peak_cps", "", 0)],
        ["Peak gateway CPU", f"{sa.get('peak_gw_cpu_pct')}%" if sa.get("peak_gw_cpu_pct") is not None else "Not recorded",
         f"{sb.get('peak_gw_cpu_pct')}%" if sb.get("peak_gw_cpu_pct") is not None else "Not recorded",
         _fmt_d("peak_gw_cpu_pct", " pts", 1) if (sa.get("peak_gw_cpu_pct") is not None and sb.get("peak_gw_cpu_pct") is not None) else "-"],
        ["Outcome", ca["verdict"], cb["verdict"], "-"],
    ]
    story.append(_styled_table(rows, [46, 40, 40, 52], font_size=7.8, pad=3.4))
    story.append(Spacer(1, 4 * mm))
    series = [(ca["S"], f"Run #{ida} (A)"), (cb["S"], f"Run #{idb} (B)")]
    tp = _chart_overlay(series, "rx_bps", "bps", h_in=2.35)
    if tp:
        story.append(_chart_card("Received throughput: run A vs run B", tp, caption="Each run plotted against its own elapsed time"))

    # ---- Latency + flows overlays ------------------------------------------
    lat = _chart_overlay(series, "lat_avg_us", "us", h_in=2.35)
    fl = _chart_overlay(series, "active_flows", "count", h_in=2.35)
    if lat or fl:
        _section(story, st, "Latency & concurrency overlays", "How delay and concurrent flows evolved in each run",
                 _chart_card("Average latency: run A vs run B", lat, caption="Lower is better") if lat else None, need_mm=120)
        if fl:
            story.append(Spacer(1, 4 * mm))
            story.append(_chart_card("Active flows: run A vs run B", fl, caption="Concurrent L4 flows reported by the traffic engine"))
        cps = _chart_overlay(series, "cps", "count", h_in=2.35)
        if cps:
            story.append(Spacer(1, 4 * mm))
            story.append(_chart_card("New connections per second: run A vs run B", cps, caption="TCP/UDP connection setup rate reported by the traffic engine"))
        elif lat:
            story.append(Spacer(1, 4 * mm))
            story.append(_callout_box("NO FLOW COUNTERS", "Neither run recorded active-flow counters (e.g. stateless STL), so no concurrency overlay is shown.", tone="muted"))
    if not (tp or lat or fl):
        story.append(_callout_box("NO TIME-SERIES DATA", "Neither run has per-second samples, so no overlay charts are shown.", tone="muted"))

    doc.build(
        story,
        canvasmaker=lambda *a, **kw: _ReportNumberedCanvas(
            *a,
            run_label=f"COMPARISON  |  #{ida} VS #{idb}",
            footer_left=f"CODEBLUE IT SERVICES  |  COMPARISON REPORT #{ida} VS #{idb}",
            cover_line3="COMPARISON REPORT",
            **kw,
        ),
    )
    buf.seek(0)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Breaking-point (capacity finder) report
# ---------------------------------------------------------------------------
_CAUSE_TEXT = {
    "loss": "packet loss",
    "latency": "latency",
    "delivery": "delivery (received vs sent)",
    "no_traffic": "no traffic",
    "error": "a test error",
}
C_GOOD = "#15803D"
C_BAD = "#DC2626"


def _cap_settings(state: Dict[str, Any]) -> Dict[str, Any]:
    s = dict(state.get("settings") or {})
    return {
        "start_users": _int(s.get("start_users")),
        "max_users": _int(s.get("max_users")),
        "step_users": _int(s.get("step_users")),
        "step_sec": _int(s.get("step_sec")),
        "target_gbps": _f(s.get("target_gbps")),
        "per_user_kbps": _f(s.get("per_user_kbps")),
        "max_loss_pct": _f(s.get("max_loss_pct")),
        "max_latency_ms": _f(s.get("max_latency_ms")),
        "min_rx_ratio": _f(s.get("min_rx_ratio")),
        "profile_id": s.get("profile_id") or "",
    }


def _cap_run_for(runs: Dict[Any, Any], run_id: Any) -> Optional[Dict[str, Any]]:
    if run_id is None or not isinstance(runs, dict):
        return None
    for key in (run_id, str(run_id)):
        if key in runs and isinstance(runs[key], dict):
            return runs[key]
    try:
        r = runs.get(int(run_id))
        return r if isinstance(r, dict) else None
    except (TypeError, ValueError):
        return None


def _cap_steps(state: Dict[str, Any], runs: Dict[Any, Any], s: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Normalise steps; fill missing numbers from the step's run summary (measured values only)."""
    out = []
    for i, st in enumerate(state.get("steps") or []):
        if not isinstance(st, dict):
            continue
        d = dict(st)
        d["step"] = _int(st.get("step")) or (i + 1)
        d["users"] = _int(st.get("users"))
        run = _cap_run_for(runs, st.get("run_id"))
        summ = (run or {}).get("summary") or {}
        for k in ("avg_tx_bps", "avg_rx_bps", "max_rx_bps", "drop_pct", "lat_avg_us", "p99_lat_us", "jitter_avg_us",
                  "peak_active_flows", "peak_cps", "peak_gw_cpu_pct", "peak_established_sessions"):
            v = _f(st.get(k))
            d[k] = v if v is not None else _f(summ.get(k))
        tgt = _f(st.get("target_bps"))
        if tgt is None and s["per_user_kbps"] and d["users"]:
            tgt = d["users"] * s["per_user_kbps"] * 1000.0
        if tgt is None and s["target_gbps"]:
            tgt = s["target_gbps"] * 1e9
        if tgt is None:
            tgt = _f(((run or {}).get("config") or {}).get("base_target_bps"))
        d["target_bps"] = tgt
        d["run"] = run
        d["ok"] = bool(st.get("ok"))
        d["refine"] = bool(st.get("refine"))
        d["reason"] = str(st.get("reason") or "")
        causes = [c for c in (st.get("break_causes") or []) if isinstance(c, str)]
        if not causes and not d["ok"]:
            causes = _cap_causes_from_numbers(d, s)
        d["causes"] = causes
        out.append(d)
    out.sort(key=lambda x: x["step"])
    return out


def _cap_causes_from_numbers(d: Dict[str, Any], s: Dict[str, Any]) -> List[str]:
    c = []
    tx, rx = d.get("avg_tx_bps") or 0.0, d.get("avg_rx_bps") or 0.0
    if d.get("run_id") is None and not tx:
        return ["error"]
    if s["max_loss_pct"] is not None and (d.get("drop_pct") or 0) > s["max_loss_pct"]:
        c.append("loss")
    if s["max_latency_ms"] is not None and (d.get("lat_avg_us") or 0) / 1000.0 > s["max_latency_ms"]:
        c.append("latency")
    if tx > 0 and s["min_rx_ratio"] is not None and rx / tx < s["min_rx_ratio"]:
        c.append("delivery")
    if tx <= 0:
        c.append("no_traffic")
    return c


def _cap_break_moment(run: Optional[Dict[str, Any]], s: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """First per-second sample in the breaking step where any limit was crossed."""
    samples = [x for x in ((run or {}).get("samples") or []) if isinstance(x, dict)]
    if not samples:
        return None
    tx_peak = max((_f(x.get("tx_bps")) or 0.0) for x in samples)
    prev_tx = prev_rx = None
    for x in samples:
        crossed = []
        # drop_pct in each sample is a running total, so early seconds (very few packets) can look
        # alarming. Use the loss within this one-second interval when packet counters allow it,
        # otherwise only trust the running total once enough packets have been sent.
        tx_p, rx_p = _f(x.get("tx_packets")), _f(x.get("rx_packets"))
        loss = None
        if tx_p is not None and rx_p is not None and prev_tx is not None and prev_rx is not None:
            d_tx, d_rx = tx_p - prev_tx, rx_p - prev_rx
            if d_tx >= 1000:
                loss = max(0.0, (d_tx - d_rx) / d_tx * 100.0)
        elif (tx_p or 0) >= 10000:
            loss = _f(x.get("drop_pct"))
        prev_tx, prev_rx = tx_p, rx_p
        lat = _f(x.get("lat_avg_us"))
        tx, rx = _f(x.get("tx_bps")) or 0.0, _f(x.get("rx_bps"))
        if s["max_loss_pct"] is not None and loss is not None and loss > s["max_loss_pct"]:
            crossed.append(("loss", f"loss {loss:.3f}% > {s['max_loss_pct']:g}%"))
        if s["max_latency_ms"] is not None and lat is not None and lat / 1000.0 > s["max_latency_ms"]:
            crossed.append(("latency", f"latency {lat / 1000.0:.2f} ms > {s['max_latency_ms']:g} ms"))
        # ignore the first trickle of the ramp (<5% of the step's peak rate) for the delivery check
        if s["min_rx_ratio"] is not None and rx is not None and tx > 0.05 * tx_peak and tx > 0 and rx / tx < s["min_rx_ratio"]:
            crossed.append(("delivery", f"only {rx / tx * 100:.1f}% of traffic got through"))
        if crossed:
            return {"sample": x, "elapsed": _f(x.get("elapsed_sec")) or 0.0, "phase": str(x.get("phase_name") or ""), "crossed": crossed}
    return None


def _cap_likely_causes(good: Optional[Dict[str, Any]], bad: Dict[str, Any], s: Dict[str, Any]) -> List[str]:
    """Simple, explainable rules. Returns human phrases, most likely first."""
    out = []
    causes = bad.get("causes") or []
    gw = bad.get("peak_gw_cpu_pct")
    if gw is not None and gw >= 90:
        out.append(f"gateway CPU saturation (gateway CPU reached {gw:.0f}%)")
    rx_b = bad.get("avg_rx_bps") or 0.0
    rx_peak = max(rx_b, bad.get("max_rx_bps") or 0.0)
    tgt_b = bad.get("target_bps") or 0.0
    rx_g = (good or {}).get("avg_rx_bps") or 0.0
    lossy = "loss" in causes or "delivery" in causes
    if lossy and rx_b > 0:
        link = None
        for L in (1e8, 1e9, 1e10, 2.5e9, 2.5e10, 4e10, 1e11):
            if 0.85 * L <= rx_peak <= 1.03 * L:
                link = L
                break
        plateau = rx_g > 0 and rx_b <= rx_g * 1.05 and (tgt_b > (good or {}).get("target_bps", 0) * 1.02 if good and good.get("target_bps") else True)
        near_target = tgt_b > 0 and rx_b >= 0.9 * tgt_b
        if link:
            out.append(f"a bandwidth ceiling: received throughput levelled off around {_fmt_bps(rx_peak)}, close to a {_fmt_bps(link)} link, while loss rose")
        elif plateau:
            out.append(f"a bandwidth ceiling: received throughput stopped growing (about {_fmt_bps(rx_b)}) while loss rose")
        elif near_target:
            out.append(f"a bandwidth ceiling near the step's {_fmt_bps(tgt_b)} target, where loss began")
    lat_b = bad.get("lat_avg_us") or 0.0
    lat_g = (good or {}).get("lat_avg_us") or 0.0
    if lat_g > 0 and lat_b >= 2 * lat_g and rx_b > rx_g * 1.02:
        out.append(f"queuing or CPU saturation: latency rose sharply ({_fmt_us(lat_g)} to {_fmt_us(lat_b)}) while throughput was still growing")
    fl_b, fl_g = bad.get("peak_active_flows") or 0.0, (good or {}).get("peak_active_flows") or 0.0
    cps_b, cps_g = bad.get("peak_cps") or 0.0, (good or {}).get("peak_cps") or 0.0
    if fl_g > 0 and cps_g > 0 and fl_b <= fl_g * 1.05 and cps_b >= cps_g * 1.10:
        out.append(f"a connection-table / session limit: open connections levelled off near {fl_b:,.0f} while new connections per second kept rising")
    return out


def _cap_user_fmt(maxu: float) -> FuncFormatter:
    if maxu >= 10000:
        return FuncFormatter(lambda v, _p: f"{v / 1000:,.0f}k" if abs(v - round(v / 1000) * 1000) < 1 else f"{v / 1000:,.1f}k")
    return _count_fmt


def _cap_marks(ax: Any, good: Optional[int], bad: Optional[int], labels: bool = True) -> None:
    trans = blended_transform_factory(ax.transData, ax.transAxes)
    if good:
        ax.axvline(good, color=C_GOOD, lw=1.0, ls=(0, (3, 2)), zorder=2)
        if labels:
            ax.text(good, 0.97, "max clean", transform=trans, rotation=90, ha="right", va="top", fontsize=6.2, color=C_GOOD, zorder=6,
                    bbox=dict(boxstyle="square,pad=0.1", fc="white", ec="none", alpha=0.8))
    if bad:
        ax.axvline(bad, color=C_BAD, lw=1.0, ls=(0, (3, 2)), zorder=2)
        if labels:
            ax.text(bad, 0.97, "broke", transform=trans, rotation=90, ha="left", va="top", fontsize=6.2, color=C_BAD, zorder=6,
                    bbox=dict(boxstyle="square,pad=0.1", fc="white", ec="none", alpha=0.8))


def _cap_xlim(ax: Any, users: List[float]) -> None:
    lo, hi = min(users), max(users)
    pad = (hi - lo) * 0.07 if hi > lo else max(hi * 0.2, 1.0)
    ax.set_xlim(lo - pad, hi + pad)


def _cap_limit_line(ax: Any, limit: Optional[float], data_max: float, label: str) -> float:
    """Draw a dashed limit line when it is on a readable scale; otherwise note it. Returns the y-top to use."""
    top = max(data_max * 1.18, 1e-6)
    if limit is None:
        return top
    if data_max <= 0:  # nothing measured above zero: show the limit so the gap is visible
        ax.axhline(limit, color=C_MUTED, lw=0.9, ls=(0, (4, 3)), zorder=2, label=label)
        return limit * 1.3
    if limit <= max(data_max, 1e-9) * 3:
        ax.axhline(limit, color=C_MUTED, lw=0.9, ls=(0, (4, 3)), zorder=2, label=label)
        return max(top, limit * 1.15)
    ax.plot([], [], color=C_MUTED, lw=0.9, ls=(0, (4, 3)), label=f"{label} {limit:g} (off scale)")
    return top



def _chart_cap_throughput(steps: List[Dict[str, Any]], good: Optional[int], bad: Optional[int], w_in: float = HALF_W_IN, h_in: float = 2.25) -> Optional[ChartImg]:
    pts = [st for st in steps if st["users"] and (st["avg_rx_bps"] is not None or st["target_bps"])]
    if not pts or not any((st["avg_rx_bps"] or 0) > 0 for st in pts):
        return None
    pts = sorted(pts, key=lambda x: x["users"])
    users = [st["users"] for st in pts]
    peak = max(max((st["avg_rx_bps"] or 0) for st in pts), max((st["target_bps"] or 0) for st in pts))
    div, unit = _bps_unit(peak)
    fig, (ax,) = _new_fig(w_in, h_in)
    rx = np.array([(st["avg_rx_bps"] / div) if st["avg_rx_bps"] is not None else np.nan for st in pts], dtype=float)
    ax.plot(users, rx, color=C_BLUE, lw=1.6, zorder=3, label="Received")
    ax.fill_between(users, np.nan_to_num(rx), color=C_BLUE, alpha=0.07, lw=0)
    face = [("white" if st["refine"] else (C_BLUE if st["ok"] else C_ORANGE)) for st in pts]
    edge = [(C_BLUE if st["ok"] else C_ORANGE) for st in pts]
    ax.scatter(users, rx, s=22, facecolors=face, edgecolors=edge, linewidths=1.1, zorder=5)
    if any(not st["ok"] for st in pts):
        ax.scatter([], [], s=22, color=C_ORANGE, label="Step crossed a limit")
    tg = [(st["target_bps"] or np.nan) / div if st["target_bps"] else np.nan for st in pts]
    if any(np.isfinite(tg)):
        ax.plot(users, tg, color=C_MUTED, lw=1.0, ls=(0, (4, 3)), marker="o", markersize=2.5, label="Target", zorder=4)
    _cap_marks(ax, good, bad)
    ax.set_ylim(0, peak / div * 1.2)
    _cap_xlim(ax, users)
    ax.xaxis.set_major_formatter(_cap_user_fmt(max(users)))
    _ylabel(ax, f"Throughput ({unit})")
    _xlabel(ax, "Simulated users")
    _legend_top(ax)
    return _fig_png(fig)


def _chart_cap_metric(steps: List[Dict[str, Any]], good: Optional[int], bad: Optional[int], series: List[Tuple[str, str, str, float]],
                      ylab: str, limit: Optional[float], limit_label: str, fmt: Optional[FuncFormatter] = None,
                      w_in: float = HALF_W_IN, h_in: float = 2.25) -> Optional[ChartImg]:
    """Generic per-step line chart vs users. series: (key, label, colour, divisor)."""
    pts = sorted([st for st in steps if st["users"]], key=lambda x: x["users"])
    present = [sr for sr in series if any((st.get(sr[0]) or 0) > 0 for st in pts)]
    # Loss can legitimately be 0 everywhere: still draw it (that IS the evidence) if any value was recorded.
    if not present:
        present = [sr for sr in series if any(st.get(sr[0]) is not None for st in pts)] if limit is not None else []
    if not pts or not present:
        return None
    users = [st["users"] for st in pts]
    fig, (ax,) = _new_fig(w_in, h_in)
    data_max = 0.0
    for key, lbl, clr, div in present:
        ys = np.array([(st.get(key) / div) if st.get(key) is not None else np.nan for st in pts], dtype=float)
        data_max = max(data_max, _amax(ys))
        ax.plot(users, ys, color=clr, lw=1.5, zorder=3, label=lbl)
        face = ["white" if st["refine"] else clr for st in pts]
        ax.scatter(users, ys, s=16, facecolors=face, edgecolors=clr, linewidths=1.0, zorder=4)
    top = _cap_limit_line(ax, limit, data_max, limit_label)
    _cap_marks(ax, good, bad)
    ax.set_ylim(0, top if top > 0 else 1.0)
    _cap_xlim(ax, users)
    ax.xaxis.set_major_formatter(_cap_user_fmt(max(users)))
    if fmt is not None:
        ax.yaxis.set_major_formatter(fmt)
    _ylabel(ax, ylab)
    _xlabel(ax, "Simulated users")
    _legend_top(ax)
    return _fig_png(fig)


def _chart_cap_moment(run: Dict[str, Any], s: Dict[str, Any], moment: Optional[Dict[str, Any]], w_in: float = FULL_W_IN, h_in: float = 3.2) -> Optional[ChartImg]:
    S = _TS(run.get("samples"))
    if S.n == 0:
        return None
    panels = []
    if S.has("tx_bps") or S.has("rx_bps"):
        panels.append("tp")
    if S.has("lat_avg_us"):
        panels.append("lat")
    if S.has("drop_pct") or s["max_loss_pct"] is not None:
        panels.append("loss")
    if not panels:
        return None
    fig, axes = _new_fig(w_in, h_in if len(panels) == 3 else (2.6 if len(panels) == 2 else 1.9), nrows=len(panels),
                         height_ratios=[1.3, 1.0, 1.0][: len(panels)])
    x, (tx, rx, lat, loss) = S.xy(["tx_bps", "rx_bps", "lat_avg_us", "drop_pct"])
    kw = _line_kw(len(x))
    mx = (moment["elapsed"] / S.tdiv) if moment else None
    for ax, kind in zip(axes, panels):
        S.bands(ax, labels=(kind == panels[0]))
        if kind == "tp":
            div, unit = _bps_unit(max(_amax(S.col("tx_bps")), _amax(S.col("rx_bps"))))
            ax.plot(x, tx / div, color=C_BLUE, lw=2.4, label="Sent (TX)", zorder=3, **kw)
            ax.plot(x, rx / div, color=C_ORANGE, lw=0.95, label="Received (RX)", zorder=4, **kw)
            ax.set_ylim(0, max(max(_amax(S.col("tx_bps")), _amax(S.col("rx_bps"))) / div * 1.15, 1e-6))
            _ylabel(ax, f"Throughput ({unit})")
        elif kind == "lat":
            lm = lat / 1000.0
            ax.plot(x, lm, color=C_TEAL, lw=1.5, label="Average latency", zorder=3, **kw)
            top = _cap_limit_line(ax, s["max_latency_ms"], _amax(S.col("lat_avg_us")) / 1000.0, "Latency limit")
            ax.set_ylim(0, top)
            _ylabel(ax, "Latency (ms)")
        else:
            ax.plot(x, loss, color=C_ORANGE, lw=1.5, label="Packet loss (cumulative %)", zorder=3, **kw)
            top = _cap_limit_line(ax, s["max_loss_pct"], _amax(S.col("drop_pct")), "Loss limit")
            ax.set_ylim(0, top)
            ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _p: f"{v:.3g}%"))
            _ylabel(ax, "Loss (%)")
        if mx is not None:
            ax.axvline(mx, color=C_BAD, lw=1.3, zorder=5)
        _legend_top(ax)
    if mx is not None:
        axes[0].annotate(f"first limit crossed: {moment['elapsed']:.0f} s", xy=(mx, 1.0), xycoords=blended_transform_factory(axes[0].transData, axes[0].transAxes),
                         xytext=(4, -10), textcoords="offset points", fontsize=6.8, color=C_BAD, ha="left", va="top", zorder=7,
                         bbox=dict(boxstyle="round,pad=0.2", fc="white", ec="none", alpha=0.85))
    _xlim(axes[-1], x)
    _xlabel(axes[-1], S.xlabel + " within the step")
    return _fig_png(fig)


def generate_capacity_report_pdf(state: Dict[str, Any], runs: Dict[Any, Any]) -> bytes:
    """Breaking-point finder report: plain-English verdict first, then limits, capacity curves, the moment it broke,
    the step table and next steps. Everything is computed from the finder state and the step runs' measured samples."""
    state = state if isinstance(state, dict) else {}
    runs = runs if isinstance(runs, dict) else {}
    s = _cap_settings(state)
    steps = _cap_steps(state, runs, s)
    st = _styles()
    buf = io.BytesIO()

    outcome = str(state.get("outcome") or ("running" if state.get("running") else "unknown"))
    ok_steps = [x for x in steps if x["ok"] and x["users"]]
    bad_steps = [x for x in steps if not x["ok"]]
    good_users = _int(state.get("max_good_users")) or (max(x["users"] for x in ok_steps) if ok_steps else 0) or None
    bad_users = _int(state.get("first_bad_users")) or None
    if bad_users is None and bad_steps:
        cand = [x["users"] for x in bad_steps if x["users"] and (good_users is None or x["users"] > good_users)]
        bad_users = min(cand) if cand else (bad_steps[0]["users"] or None)
    good_step = max((x for x in ok_steps if x["users"] == good_users), key=lambda x: x["step"], default=None) if good_users else None
    bad_step = next((x for x in bad_steps if x["users"] == bad_users and x["run"]), None) or next((x for x in bad_steps if x["users"] == bad_users), None)
    if bad_step is None and bad_steps:
        bad_step = bad_steps[0]
    tested_max = max((x["users"] for x in steps), default=0)

    # Test path: state.path, else the first step run's topology snapshot
    path = state.get("path") if isinstance(state.get("path"), dict) else {}
    if not path:
        for x in steps:
            topo = ((x["run"] or {}).get("config") or {}).get("topology_snapshot") or {}
            if isinstance(topo, dict) and (topo.get("active_mode_code") or topo.get("active_mode_label")):
                path = {"code": topo.get("active_mode_code"), "label": topo.get("active_mode_label")}
                break
    loopback = "loopback" in str(path.get("code") or "").lower() or "loopback" in str(path.get("label") or "").lower()
    first_run = next((x["run"] for x in steps if x["run"]), None) or {}
    dut = first_run.get("dut_name") or (first_run.get("config") or {}).get("dut_name") or "the gateway"

    started = _f(state.get("started_at"))
    started_dt = datetime.datetime.fromtimestamp(started) if started else datetime.datetime.now()
    ended = _f(state.get("ended_at"))
    elapsed_txt = _fmt_duration(ended - started) if (started and ended and ended > started) else "-"

    # ---------------- headline -------------------------------------------------
    if outcome == "limit_found" and good_users and bad_users:
        headline = f"Handled {good_users:,} users cleanly — broke at {bad_users:,}"
    elif outcome == "limit_found" and bad_users:
        headline = f"Already outside the limits at {bad_users:,} users (the first step)"
    elif outcome == "no_limit_found":
        headline = f"No breaking point found up to {tested_max or s['max_users']:,} users"
    elif outcome == "cancelled":
        headline = f"Stopped by operator after {len(steps)} step{'s' if len(steps) != 1 else ''}"
    elif outcome == "error":
        headline = f"Stopped by an error after {len(steps)} step{'s' if len(steps) != 1 else ''}"
    elif outcome == "running":
        headline = f"Test still running: {len(steps)} step{'s' if len(steps) != 1 else ''} completed so far"
    else:
        headline = "Breaking-point test: no result recorded"
    head_accent = C_BAD if outcome == "limit_found" else (C_GOOD if outcome == "no_limit_found" else "#64748B")

    # ---------------- event framing (when the finder was run in event mode) -----
    event = ((state.get("settings") or {}).get("event")) if isinstance((state.get("settings") or {}).get("event"), dict) else None
    event_lines: List[str] = []
    if event and _int(event.get("attendees")):
        att = _int(event.get("attendees"))
        pct = lambda u: (u / att * 100.0) if (u and att) else 0.0  # noqa: E731
        on = float(event.get("online_pct") or 0) / 100.0
        mbps = float(event.get("mbps_per_user") or 0)
        cpp = float(event.get("conns_per_user") or 0)
        need_bps = att * on * mbps * 1e6
        need_conns = att * on * cpp
        if outcome == "limit_found" and good_users and bad_users:
            headline = f"Handled {good_users:,} attendees ({pct(good_users):.0f}% of your event) — broke at {bad_users:,} ({pct(bad_users):.0f}%)"
        elif outcome == "limit_found" and bad_users:
            headline = f"Broke at {bad_users:,} attendees — {pct(bad_users):.0f}% of your event"
        elif outcome == "no_limit_found":
            headline = f"Handled {tested_max:,} attendees ({pct(tested_max):.0f}% of your event) with no breaking point"
        event_lines.append(
            f"<b>Your event:</b> {att:,} attendees, {on * 100:.0f}% online at once, {mbps:g} Mbps per online person and {cpp:g} open connections per phone "
            f"— at full size that is about <b>{_fmt_bps(need_bps)}</b> and <b>{need_conns:,.0f} open connections</b> through the network.")
        if outcome == "no_limit_found" and tested_max >= att:
            event_lines.append(f"<b>Verdict: the network carried your full event</b> and kept going to {pct(tested_max):.0f}% of it without breaking.")
        elif outcome == "limit_found" and good_users and good_users >= att:
            event_lines.append(f"<b>Verdict: the network can carry your full event</b>, with headroom: it stayed clean up to {pct(good_users):.0f}% "
                               f"and broke at {pct(bad_users or 0):.0f}% of your expected crowd.")
        elif outcome == "limit_found" and bad_users:
            event_lines.append(f"<b>Verdict: this setup would NOT carry your full event.</b> Quality broke at about {pct(bad_users):.0f}% of your expected crowd "
                               f"({bad_users:,} attendees)" + (f"; the last clean step was {pct(good_users):.0f}% ({good_users:,})." if good_users else "."))

    # ---------------- plain-English "what happened" ---------------------------
    moment = _cap_break_moment(bad_step["run"], s) if bad_step else None
    likely = _cap_likely_causes(good_step, bad_step, s) if bad_step else []
    what: List[str] = []
    lim_txt = []
    if s["max_loss_pct"] is not None:
        lim_txt.append(f"loss at most {s['max_loss_pct']:g}%")
    if s["max_latency_ms"] is not None:
        lim_txt.append(f"average latency at most {s['max_latency_ms']:g} ms")
    if s["min_rx_ratio"] is not None:
        lim_txt.append(f"at least {s['min_rx_ratio'] * 100:g}% of traffic delivered")
    lim_join = ", ".join(lim_txt) if lim_txt else "the configured limits"
    if bad_step is not None and outcome in ("limit_found", "cancelled", "error", "running", "unknown"):
        if good_users:
            what.append(f"The network carried <b>{good_users:,} simulated users</b> within all limits ({_esc(lim_join)}).")
        crossed = [c for c in bad_step["causes"] if c in _CAUSE_TEXT]
        if moment:
            first_kind = moment["crossed"][0][0]
            ph = f", during the {_phase_label(moment['phase']).lower()} phase" if moment["phase"] else ""
            what.append(f"At <b>{bad_step['users']:,} users</b> the first limit crossed was <b>{_CAUSE_TEXT.get(first_kind, first_kind)}</b> "
                        f"({_esc(moment['crossed'][0][1])}), <b>{moment['elapsed']:.0f} seconds</b> into that step{ph}.")
            sm = moment["sample"]
            bits = []
            if _f(sm.get("rx_bps")) is not None:
                bits.append(f"receiving {_fmt_bps(_f(sm.get('rx_bps')))}")
            if _f(sm.get("active_flows")):
                bits.append(f"{_f(sm.get('active_flows')):,.0f} open connections")
            if _f(sm.get("cps")):
                bits.append(f"{_f(sm.get('cps')):,.0f} new connections per second")
            if bits:
                what.append("At that moment the network was " + ", ".join(bits[:-1]) + (" and " if len(bits) > 1 else "") + bits[-1] + ".")
        elif crossed:
            what.append(f"At <b>{bad_step['users']:,} users</b> the step failed on {', '.join(_CAUSE_TEXT[c] for c in crossed)}"
                        + (f" ({_esc(bad_step['reason'])})" if bad_step["reason"] else "")
                        + ("; no single second crossed a limit on its own, the step's overall average did." if bad_step["run"] and (bad_step["run"].get("samples")) else "."))
        elif bad_step["reason"]:
            what.append(f"At <b>{bad_step['users']:,} users</b> the step did not pass: {_esc(bad_step['reason'])}.")
        if likely:
            what.append("Likely cause: " + _esc(likely[0]) + "." + (" Also consistent with " + _esc(likely[1]) + "." if len(likely) > 1 else ""))
        elif crossed and "error" not in crossed:
            what.append("Likely cause: unclear from these measurements — see the evidence below.")
    elif outcome == "no_limit_found":
        best = max((x["avg_rx_bps"] or 0) for x in steps) if steps else 0
        what.append(f"All {len(steps)} steps stayed within the limits ({_esc(lim_join)}), up to <b>{tested_max:,} simulated users</b>.")
        if best:
            what.append(f"The highest average received throughput was <b>{_fmt_bps(best)}</b>.")
        what.append("The breaking point is above the tested range: raise the maximum users or the traffic rate to find it.")
    if outcome == "cancelled":
        what.append(f"The operator stopped the test after {len(steps)} step{'s' if len(steps) != 1 else ''}"
                    + (f"; the highest clean step was {good_users:,} users." if good_users else "."))
    if outcome == "error":
        msg = str(state.get("message") or "")
        what.append("The test stopped because of an error" + (f": {_esc(msg)}" if msg else "") + ".")
    if not steps:
        what = ["No steps were recorded, so there is nothing to analyse yet."]
    what = event_lines + what
    if loopback:
        what.append(f"<b>Important:</b> traffic ran over the internal loopback test path, not through {_esc(dut)}, so "
                    + ("this limit belongs to the test server/loopback, not the firewall." if bad_step is not None else "these results describe the test server/loopback, not the firewall."))

    # ---------------- document ---------------------------------------------------
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=16 * mm, rightMargin=16 * mm, topMargin=30 * mm, bottomMargin=20 * mm,
                            title="Codeblue Network Breaking-Point Report", author="Codeblue IT Services")
    story: List[Any] = []

    # Cover
    story.append(Spacer(1, 55 * mm))
    head_tbl = Table([[Paragraph(
        f"<font name='Helvetica-Bold' size='7' color='#64748B'>RESULT</font><br/>"
        f"<font name='Helvetica-Bold' size='17' color='#0F1D31'>{_esc(headline)}</font>",
        ParagraphStyle("caphead", parent=_SS["Normal"], leading=21))]], colWidths=[178 * mm])
    head_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F8FAFC")), ("BOX", (0, 0), (-1, -1), 0.8, BORDER),
        ("LINEBEFORE", (0, 0), (0, -1), 4, colors.HexColor(head_accent)),
        ("TOPPADDING", (0, 0), (-1, -1), 9), ("BOTTOMPADDING", (0, 0), (-1, -1), 11), ("LEFTPADDING", (0, 0), (-1, -1), 12),
    ]))
    story.append(head_tbl)
    story.append(Spacer(1, 4 * mm))
    best_rx = max(((x["avg_rx_bps"] or 0), x["users"]) for x in steps) if steps else (0, 0)
    peak_conn = max((x["peak_active_flows"] or 0) for x in steps) if steps else 0
    conn_recorded = any(x["peak_active_flows"] is not None for x in steps)
    story.append(_kpi_card_row([
        {"label": "Max clean users", "value": f"{good_users:,}" if good_users else "None", "sub": "All limits met", "accent": C_GOOD},
        {"label": "Broke at", "value": f"{bad_users:,}" if bad_users else "Not reached", "sub": ", ".join(_CAUSE_TEXT.get(c, c) for c in (bad_step or {}).get("causes", [])) or "-", "accent": C_BAD if bad_users else "#64748B"},
        {"label": "Max received", "value": _fmt_bps(best_rx[0]) if best_rx[0] else "N/A", "sub": f"at {best_rx[1]:,} users" if best_rx[0] else "", "accent": "#1769D2"},
        {"label": "Peak open conns", "value": f"{peak_conn:,.0f}" if conn_recorded else "N/A", "sub": f"{len(steps)} step{'s' if len(steps) != 1 else ''} run", "accent": "#85C6FF"},
    ], value_size=13.5))
    story.append(Spacer(1, 4 * mm))
    plan = f"{s['start_users']:,} to {s['max_users']:,} users in {s['step_users']:,}-user steps, {s['step_sec']} s steady each" if s["max_users"] else "Plan not recorded"
    rate = (f"{s['per_user_kbps']:g} kbps per user" if s["per_user_kbps"] else (f"target {s['target_gbps']:g} Gbps" if s["target_gbps"] else "target not recorded"))
    fields = [("TEST DATE", started_dt.strftime("%d %B %Y, %H:%M")), ("TOTAL TIME", elapsed_txt),
              ("STEP PLAN", plan), ("TRAFFIC RATE", rate),
              ("PASS LIMITS", lim_join), ("TEST PATH", str(path.get("label") or path.get("code") or "Not recorded"))]
    cells = [[[Paragraph(_esc(k), st["meta_lbl"]), Paragraph(_esc(v), st["meta_val"])] for k, v in fields[i:i + 2]] for i in range(0, len(fields), 2)]
    meta = Table(cells, colWidths=[89 * mm, 89 * mm])
    meta.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 6), ("TOPPADDING", (0, 0), (-1, -1), 2),
                              ("BOTTOMPADDING", (0, 0), (-1, -1), 5), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story.append(meta)
    story.append(Spacer(1, 3 * mm))
    if loopback:
        story.append(_callout_box("TEST PATH: INTERNAL LOOPBACK",
                                  f"The traffic did not go through {dut}. The limit found is the test server's / loopback path's, not the firewall's. "
                                  "Cable two test ports through the gateway and run the finder again to measure the gateway itself.", tone="warn"))
    else:
        story.append(_callout_box("HOW THIS TEST WORKS",
                                  "The finder runs one normal test per step with more simulated users each time. A step passes only when every limit above is met; "
                                  "the first step that fails is the breaking point. Each step is also saved as its own run in Test History.", tone="info"))
    story.append(PageBreak())

    # What happened + limits
    story.append(Paragraph("What happened", st["h1"]))
    story.append(Paragraph("Plain-English summary of what broke, and when", st["sub"]))
    tone = "fail" if outcome == "limit_found" else ("pass" if outcome == "no_limit_found" else "info")
    story.append(_callout_box(headline.upper(), " ".join(what), tone=tone, body_is_markup=True))

    story.append(Paragraph("Limits found", st["h2"]))
    lim_rows = [["Measure", "Result"]]
    lim_rows.append(["Maximum users within all limits", f"{good_users:,}" if good_users else "None of the steps passed"])
    lim_rows.append(["First users count that failed", f"{bad_users:,}" if bad_users else "Not reached"])
    peak_rx_1s = max(((x["max_rx_bps"] or 0) for x in steps), default=0)
    lim_rows.append(["Maximum throughput reached (received)", (f"{_fmt_bps(best_rx[0])} average at {best_rx[1]:,} users" if best_rx[0] else "N/A")
                     + (f"  (1-second peak {_fmt_bps(peak_rx_1s)})" if peak_rx_1s > (best_rx[0] or 0) else "")])
    lim_rows.append(["Peak open connections", f"{peak_conn:,.0f}" if conn_recorded else "Not recorded"])
    pcps = max(((x["peak_cps"] or 0) for x in steps), default=0)
    lim_rows.append(["Peak new connections per second", f"{pcps:,.0f}" if any(x["peak_cps"] is not None for x in steps) else "Not recorded"])
    gwb = (bad_step or {}).get("peak_gw_cpu_pct")
    lim_rows.append(["Gateway CPU at the break", f"{gwb:.0f}%" if gwb is not None else "Not recorded (UniFi telemetry not connected)"])
    story.append(_styled_table(lim_rows, [72, 106], font_size=7.8, pad=3.4))

    if good_step or bad_step:
        story.append(Paragraph("Last clean step vs first failing step", st["h2"]))

        def _v(x: Optional[Dict[str, Any]], key: str, fmt: Any) -> str:
            if not x or x.get(key) is None:
                return "-"
            return fmt(x[key])

        def _deliv(x: Optional[Dict[str, Any]]) -> str:
            if not x or not x.get("avg_tx_bps"):
                return "-"
            return f"{(x.get('avg_rx_bps') or 0) / x['avg_tx_bps'] * 100:.1f}%"

        cmp_rows = [["Measure", "Limit", f"Last clean ({good_step['users']:,} users)" if good_step else "Last clean", f"First failing ({bad_step['users']:,} users)" if bad_step else "First failing"],
                    ["Received throughput", "-", _v(good_step, "avg_rx_bps", _fmt_bps), _v(bad_step, "avg_rx_bps", _fmt_bps)],
                    ["Delivered (RX / TX)", f"min {s['min_rx_ratio'] * 100:g}%" if s["min_rx_ratio"] is not None else "-", _deliv(good_step), _deliv(bad_step)],
                    ["Packet loss", f"max {s['max_loss_pct']:g}%" if s["max_loss_pct"] is not None else "-", _v(good_step, "drop_pct", lambda v: f"{v:.4f}%"), _v(bad_step, "drop_pct", lambda v: f"{v:.4f}%")],
                    ["Average latency", f"max {s['max_latency_ms']:g} ms" if s["max_latency_ms"] is not None else "-", _v(good_step, "lat_avg_us", _fmt_us), _v(bad_step, "lat_avg_us", _fmt_us)],
                    ["P99 latency", "-", _v(good_step, "p99_lat_us", _fmt_us), _v(bad_step, "p99_lat_us", _fmt_us)],
                    ["Peak open connections", "-", _v(good_step, "peak_active_flows", lambda v: f"{v:,.0f}"), _v(bad_step, "peak_active_flows", lambda v: f"{v:,.0f}")],
                    ["Peak new connections/s", "-", _v(good_step, "peak_cps", lambda v: f"{v:,.0f}"), _v(bad_step, "peak_cps", lambda v: f"{v:,.0f}")],
                    ["Gateway CPU (peak)", "-", _v(good_step, "peak_gw_cpu_pct", lambda v: f"{v:.0f}%"), _v(bad_step, "peak_gw_cpu_pct", lambda v: f"{v:.0f}%")]]
        story.append(_styled_table(cmp_rows, [46, 30, 51, 51], font_size=7.8, pad=3.2))

    # Capacity curves
    lat_fmt = FuncFormatter(lambda v, _p: f"{v:g}")
    c_tp = _chart_cap_throughput(steps, good_users, bad_users)
    c_lat = _chart_cap_metric(steps, good_users, bad_users, [("lat_avg_us", "Average", C_BLUE, 1000.0), ("p99_lat_us", "P99", C_ORANGE, 1000.0)],
                              "Latency (ms)", s["max_latency_ms"], "Avg limit", lat_fmt)
    c_loss = _chart_cap_metric(steps, good_users, bad_users, [("drop_pct", "Packet loss", C_ORANGE, 1.0)], "Loss (%)", s["max_loss_pct"], "Limit",
                               FuncFormatter(lambda v, _p: f"{v:.3g}%"))
    c_conn = _chart_cap_metric(steps, good_users, bad_users, [("peak_active_flows", "Peak open connections", C_BLUE, 1.0), ("peak_cps", "Peak new conns/s", C_VIOLET, 1.0)],
                               "Count", None, "", _count_fmt)
    cards = [(t, c, cap) for t, c, cap in [
        ("Received throughput vs target", c_tp, "Average per step; orange point = step that crossed a limit"),
        ("Latency per step", c_lat, "Average and P99; hollow points = refine steps"),
        ("Packet loss per step", c_loss, "Counter-derived loss over each step"),
        ("Connections per step", c_conn, "Peak open connections and new connections per second"),
    ] if c]
    if len({x["users"] for x in steps if x["users"]}) < 2:
        cards = []
        if steps:
            story.append(Paragraph("Capacity curves", st["h2"]))
            story.append(_callout_box("ONLY ONE USER COUNT TESTED", "Capacity curves need at least two steps with different user counts; see the step table" + (" and the per-second view below." if bad_step and bad_step["run"] else "."), tone="muted"))
    if cards:
        _section(story, st, "Capacity curves", "How each measure changed as users were added (green line = max clean, red line = break)",
                 None, need_mm=95)
        for i in range(0, len(cards), 2):
            pair = cards[i:i + 2]
            left = _chart_card(pair[0][0], pair[0][1], width_mm=HALF_CARD_MM, caption=pair[0][2])
            right = _chart_card(pair[1][0], pair[1][1], width_mm=HALF_CARD_MM, caption=pair[1][2]) if len(pair) > 1 else ""
            story.append(_side_by_side(left, right))
            story.append(Spacer(1, 3 * mm))

    # The moment it broke
    if bad_step and bad_step["run"]:
        mom = _chart_cap_moment(bad_step["run"], s, moment)
        if mom:
            cap = (f"Step {bad_step['step']} ({bad_step['users']:,} users, run #{bad_step.get('run_id')}). Red line = first second a limit was crossed ({moment['elapsed']:.0f} s)."
                   if moment else f"Step {bad_step['step']} ({bad_step['users']:,} users, run #{bad_step.get('run_id')}). No single second crossed a limit; the step average did.")
            _section(story, st, "The moment it broke", "Second-by-second view of the first failing step",
                     _chart_card("Throughput, latency and loss during the failing step", mom, caption=cap), need_mm=105)
    elif bad_step:
        story.append(CondPageBreak(30 * mm))
        story.append(Paragraph("The moment it broke", st["h2"]))
        story.append(_callout_box("NO PER-SECOND DATA FOR THE FAILING STEP", "The failing step has no recorded samples, so the exact second it broke cannot be shown.", tone="muted"))

    # Step table
    if steps:
        _section(story, st, "Step-by-step results", "Every step the finder ran, in order", None, need_mm=50)
        rows = [["Step", "Users", "Target", "Received", "Loss", "Avg lat.", "P99", "Conns", "CPS", "GW CPU", "Result"]]
        for x in steps:
            res = "Within limits" if x["ok"] else ("Failed: " + (x["reason"] or ", ".join(_CAUSE_TEXT.get(c, c) for c in x["causes"]) or "limit crossed"))
            step_lbl = f"{x['step']}{' (refine)' if x['refine'] else ''}" + (f" (#{x.get('run_id')})" if x.get("run_id") is not None else "")
            rows.append([step_lbl, f"{x['users']:,}", _fmt_bps(x["target_bps"]) if x["target_bps"] else "-",
                         _fmt_bps(x["avg_rx_bps"]) if x["avg_rx_bps"] is not None else "-",
                         f"{x['drop_pct']:.3f}%" if x["drop_pct"] is not None else "-",
                         _fmt_us(x["lat_avg_us"]) if x["lat_avg_us"] else "-", _fmt_us(x["p99_lat_us"]) if x["p99_lat_us"] else "-",
                         f"{x['peak_active_flows']:,.0f}" if x["peak_active_flows"] is not None else "-",
                         f"{x['peak_cps']:,.0f}" if x["peak_cps"] is not None else "-",
                         f"{x['peak_gw_cpu_pct']:.0f}%" if x["peak_gw_cpu_pct"] is not None else "-", res])
        tbl = _styled_table(rows, [15, 14, 16, 17, 13, 13, 13, 13, 13, 12, 39], font_size=6.9, pad=2.6, hpad=3.0)
        style = []
        for ri, x in enumerate(steps, start=1):
            if not x["ok"]:
                style.append(("BACKGROUND", (0, ri), (-1, ri), colors.HexColor("#FEF2F2")))
            elif x["users"] == good_users:
                style.append(("BACKGROUND", (0, ri), (-1, ri), colors.HexColor("#ECFDF5")))
        if style:
            tbl.setStyle(TableStyle(style))
        story.append(tbl)
        story.append(Paragraph("Green row = highest step within limits; red rows = steps that crossed a limit. Refine steps are extra in-between steps run after the first failure.", st["note"]))

    # Next steps
    nxt = []
    if loopback:
        nxt.append(f"Cable two test ports through {_esc(dut)} and run the finder again — this run measured the loopback path, not the gateway.")
    joined = " ".join(likely)
    if "bandwidth ceiling" in joined:
        nxt.append("Check link speeds and negotiation on every hop: the limit lines up with a link or bandwidth ceiling, not with user count.")
    if "gateway CPU" in joined:
        nxt.append("Review CPU-heavy gateway features (IPS/IDS, deep packet inspection, traffic identification) and re-test with them toggled to see which one costs the most.")
    if "session limit" in joined:
        nxt.append("Check the gateway's connection-table size and session timeouts; long idle timeouts fill the table at high user counts.")
    if "queuing" in joined:
        nxt.append("Check queueing/QoS and buffer settings: latency rose before throughput stopped growing, which points at queue build-up.")
    if outcome == "limit_found" and good_users and bad_users and (bad_users - good_users) > max(1000, 0.05 * bad_users) and not any(x["refine"] for x in steps):
        nxt.append(f"Run again between {good_users:,} and {bad_users:,} users with smaller steps to pin the limit down more precisely.")
    if outcome == "no_limit_found":
        nxt.append("Raise the maximum users or the traffic rate per step; nothing broke within the tested range.")
    if outcome == "cancelled":
        nxt.append("Let the finder run to completion to find the limit.")
    if steps and all(x["peak_gw_cpu_pct"] is None for x in steps):
        nxt.append("Connect the read-only UniFi Network API so gateway CPU is recorded with each step (it makes the cause much clearer).")
    # Keep the closing section (and its footnote) together so the footnote never lands alone on a new page
    closing: List[Any] = []
    if nxt:
        closing.append(Paragraph("Recommended next steps", st["h2"]))
        for i, line in enumerate(nxt, 1):
            closing.append(Paragraph(line, st["bullet"], bulletText=f"{i}."))
    closing.append(Paragraph("The likely cause is inferred from simple rules over the measured numbers (throughput plateau, latency rise, connection plateau, gateway CPU); "
                             "treat it as a lead to investigate, not a diagnosis.", st["note"]))
    story.append(KeepTogether(closing))

    label = "BREAKING-POINT TEST"
    doc.build(story, canvasmaker=lambda *a, **kw: _ReportNumberedCanvas(
        *a, run_label=label, footer_left="CODEBLUE IT SERVICES  |  NETWORK BREAKING-POINT REPORT",
        cover_lines=("NETWORK", "BREAKING-POINT"), cover_line3="REPORT", banner_title="NETWORK BREAKING-POINT REPORT", **kw))
    buf.seek(0)
    return buf.getvalue()

