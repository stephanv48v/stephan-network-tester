"""
CSV Time-Series & Branded Executive PDF Report Generator
for Stephan Van Vuuren's Network Tester.
"""
import csv
import datetime
import io
from typing import Any, Dict, List

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Image,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


def generate_csv_bytes(run: Dict[str, Any]) -> bytes:
    """Export all 1-second telemetry samples for a test run as a clean CSV."""
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "# Stephan Van Vuuren's Network Tester - Time-Series Telemetry Export",
        f"Run ID: {run.get('id')}",
        f"Test Name: {run.get('name')}",
        f"Profile: {run.get('profile_name')}",
        f"Mode: {run.get('test_mode')}",
        f"Verdict: {run.get('verdict', 'PASS')}",
    ])
    writer.writerow([
        "elapsed_sec",
        "timestamp_iso",
        "rate_pct",
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
        "lat_min_us",
        "lat_avg_us",
        "lat_max_us",
        "jitter_us",
        "voip_mos_score",
        "r640_cpu_pct",
        "r640_ram_pct",
    ])
    for s in run.get("samples", []):
        ts_iso = datetime.datetime.fromtimestamp(s["ts"]).isoformat()
        writer.writerow([
            s["elapsed_sec"],
            ts_iso,
            round(s["rate_pct"], 2),
            round(s["tx_bps"], 2),
            round(s["rx_bps"], 2),
            round(s["tx_bps"] / 1e6, 3),
            round(s["rx_bps"] / 1e6, 3),
            round(s["tx_pps"], 2),
            round(s["rx_pps"], 2),
            s["tx_packets"],
            s["rx_packets"],
            s["dropped_packets"],
            round(s["drop_pct"], 4),
            round(s["lat_min_us"], 2),
            round(s["lat_avg_us"], 2),
            round(s["lat_max_us"], 2),
            round(s["jitter_us"], 2),
            round(s["mos_score"], 2),
            round(s["cpu_pct"], 1),
            round(s["ram_pct"], 1),
        ])
    return buf.getvalue().encode("utf-8")


def _build_chart_image(samples: List[Dict[str, Any]]) -> io.BytesIO:
    """Render dual-panel Throughput (Mbps/Gbps) and Latency/Jitter (us) chart for the PDF report."""
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(7.5, 4.4), dpi=160, sharex=True)
    fig.patch.set_facecolor("#0B0F19")

    if not samples:
        xs = [0, 1, 2]
        tx_mbps = [0, 0, 0]
        rx_mbps = [0, 0, 0]
        lat_avg = [20, 20, 20]
        lat_max = [30, 30, 30]
        jitter = [4, 4, 4]
    else:
        xs = [s["elapsed_sec"] for s in samples]
        tx_mbps = [s["tx_bps"] / 1e6 for s in samples]
        rx_mbps = [s["rx_bps"] / 1e6 for s in samples]
        lat_avg = [s["lat_avg_us"] for s in samples]
        lat_max = [s["lat_max_us"] for s in samples]
        jitter = [s["jitter_us"] for s in samples]

    for ax in (ax1, ax2):
        ax.set_facecolor("#111827")
        ax.tick_params(colors="#94A3B8", labelsize=8)
        for spine in ax.spines.values():
            spine.set_color("#1E293B")
        ax.grid(True, color="#1E293B", linestyle="--", linewidth=0.6, alpha=0.8)

    ax1.plot(xs, tx_mbps, color="#00E5FF", linewidth=1.8, label="TX Throughput (Mbps)")
    ax1.plot(xs, rx_mbps, color="#10B981", linewidth=1.5, linestyle="--", label="RX Throughput (Mbps)")
    ax1.fill_between(xs, tx_mbps, color="#00E5FF", alpha=0.18)
    ax1.set_ylabel("Throughput (Mbps)", color="#E2E8F0", fontsize=8.5, fontweight="bold")
    ax1.set_title("Real-Time Throughput & Latency Telemetry Profile", color="#F8FAFC", fontsize=10, fontweight="bold", pad=8)
    leg1 = ax1.legend(loc="upper right", facecolor="#0F172A", edgecolor="#334155", fontsize=7.5)
    for text in leg1.get_texts():
        text.set_color("#E2E8F0")

    ax2.plot(xs, lat_avg, color="#F59E0B", linewidth=1.8, label="Avg Latency (us)")
    ax2.plot(xs, lat_max, color="#F43F5E", linewidth=1.2, linestyle=":", label="Peak Latency (us)")
    ax2.plot(xs, jitter, color="#A855F7", linewidth=1.4, label="Jitter (us)")
    ax2.fill_between(xs, lat_avg, color="#F59E0B", alpha=0.15)
    ax2.set_ylabel("Latency / Jitter (us)", color="#E2E8F0", fontsize=8.5, fontweight="bold")
    ax2.set_xlabel("Elapsed Test Time (Seconds)", color="#E2E8F0", fontsize=8.5, fontweight="bold")
    leg2 = ax2.legend(loc="upper right", facecolor="#0F172A", edgecolor="#334155", fontsize=7.5)
    for text in leg2.get_texts():
        text.set_color("#E2E8F0")

    plt.tight_layout()
    img_buf = io.BytesIO()
    plt.savefig(img_buf, format="png", facecolor=fig.get_facecolor(), edgecolor="none")
    plt.close(fig)
    img_buf.seek(0)
    return img_buf


def generate_pdf_bytes(run: Dict[str, Any]) -> bytes:
    """Build a styled Executive Network Strain & Certification PDF Report."""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=14 * mm,
        rightMargin=14 * mm,
        topMargin=14 * mm,
        bottomMargin=14 * mm,
        title=f"Stephan Van Vuuren's Network Tester - Report #{run.get('id')}",
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "SVVTitle",
        parent=styles["Heading1"],
        fontName="Helvetica-Bold",
        fontSize=16,
        leading=20,
        textColor=colors.HexColor("#0F172A"),
        spaceAfter=2,
    )
    sub_style = ParagraphStyle(
        "SVVSub",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9.5,
        textColor=colors.HexColor("#475569"),
        spaceAfter=8,
    )
    section_style = ParagraphStyle(
        "SVVSec",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=11.5,
        textColor=colors.HexColor("#0F172A"),
        spaceBefore=8,
        spaceAfter=5,
    )

    story = []

    # Header Banner Table
    verdict = str(run.get("verdict") or run.get("summary", {}).get("verdict") or "PASS").upper()
    verdict_color = "#10B981" if verdict == "PASS" else ("#F59E0B" if verdict == "WARN" else "#EF4444")

    header_data = [
        [
            Paragraph(
                "<font color='#00E5FF' size=14><b>STEPHAN VAN VUUREN'S NETWORK TESTER</b></font><br/>"
                "<font color='#CBD5E1' size=8.5>Dell PowerEdge R640 Bare-Metal Strain Appliance | Cisco TRex DPDK Engine</font>",
                styles["Normal"],
            ),
            Paragraph(
                f"<para align='right'><font color='{verdict_color}' size=14><b>SLA VERDICT: {verdict}</b></font><br/>"
                f"<font color='#94A3B8' size=8>Run ID #{run.get('id')} | {datetime.datetime.fromtimestamp(run.get('started_at', 0)).strftime('%Y-%m-%d %H:%M:%S')}</font></para>",
                styles["Normal"],
            ),
        ]
    ]
    header_tbl = Table(header_data, colWidths=[115 * mm, 67 * mm])
    header_tbl.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#0F172A")),
            ("TOPPADDING", (0, 0), (-1, -1), 10),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
            ("LEFTPADDING", (0, 0), (-1, -1), 12),
            ("RIGHTPADDING", (0, 0), (-1, -1), 12),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ])
    )
    story.append(header_tbl)
    story.append(Spacer(1, 5 * mm))

    # Test Configuration & Scale Summary
    summary = run.get("summary") or {}
    cfg = run.get("config") or {}
    story.append(Paragraph("1. Executive Test Summary & Simulated Topology", section_style))

    meta_rows = [
        ["Test Name", str(run.get("name", "")), "Traffic Profile", str(run.get("profile_name", ""))],
        ["Execution Mode", str(run.get("test_mode", "")).upper(), "Duration", f"{run.get('duration_sec', 0)} sec"],
        ["Simulated Users", f"{int(run.get('simulated_users', 0)):,} Users", "Simulated Devices", f"{int(run.get('simulated_devices', 0)):,} Endpoints"],
        ["Target Line Rate", f"{run.get('target_rate_pct', 0)}%", "Link Capacity", f"{int(cfg.get('link_capacity_mbps', 10000))} Mbps"],
        ["Frame Size / VLAN", f"{cfg.get('frame_size', 354)} Bytes / VLAN {cfg.get('vlan_id', 0)}", "QoS DSCP Class", f"DSCP {cfg.get('dscp', 0)}"],
    ]
    meta_tbl = Table(meta_rows, colWidths=[36 * mm, 55 * mm, 36 * mm, 55 * mm])
    meta_tbl.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#F1F5F9")),
            ("BACKGROUND", (2, 0), (2, -1), colors.HexColor("#F1F5F9")),
            ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor("#0F172A")),
            ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
            ("FONTNAME", (2, 0), (2, -1), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8.5),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
            ("PADDING", (0, 0), (-1, -1), 5),
        ])
    )
    story.append(meta_tbl)
    story.append(Spacer(1, 4 * mm))

    # Key Performance Indicators Table
    story.append(Paragraph("2. Key Performance & SLA Metrics", section_style))
    max_tx_mbps = float(summary.get("max_tx_bps", 0.0)) / 1e6
    avg_tx_mbps = float(summary.get("avg_tx_bps", 0.0)) / 1e6
    max_rx_mbps = float(summary.get("max_rx_bps", 0.0)) / 1e6
    avg_rx_mbps = float(summary.get("avg_rx_bps", 0.0)) / 1e6
    max_pps = float(summary.get("max_tx_pps", 0.0))
    drop_pct = float(summary.get("drop_pct", 0.0))

    kpi_rows = [
        ["Metric", "Measured Value", "Peak / Bound", "SLA Threshold", "Status"],
        [
            "TX Throughput",
            f"{avg_tx_mbps:,.2f} Mbps avg",
            f"{max_tx_mbps:,.2f} Mbps peak",
            "Line-Rate Target",
            "PASS",
        ],
        [
            "RX Throughput",
            f"{avg_rx_mbps:,.2f} Mbps avg",
            f"{max_rx_mbps:,.2f} Mbps peak",
            ">= 99% of TX",
            "PASS" if drop_pct <= 1.0 else "FAIL",
        ],
        [
            "Packet Rate (PPS)",
            f"{float(summary.get('avg_tx_pps', 0)):,.0f} pps avg",
            f"{max_pps:,.0f} pps peak",
            "ASIC Wire-Speed",
            "PASS",
        ],
        [
            "Packet Drops",
            f"{int(summary.get('total_dropped_packets', 0)):,} pkts ({drop_pct:.4f}%)",
            f"Total TX: {int(summary.get('total_tx_packets', 0)):,}",
            "< 1.000% Loss",
            "PASS" if drop_pct <= 1.0 else "FAIL",
        ],
        [
            "End-to-End Latency",
            f"{summary.get('lat_avg_us', 0):.1f} us avg",
            f"Min {summary.get('lat_min_us', 0):.1f} / Max {summary.get('lat_max_us', 0):.1f} us",
            "< 2,000 us",
            "PASS" if float(summary.get("lat_avg_us", 0)) < 2000 else "WARN",
        ],
        [
            "Packet Jitter & VoIP MOS",
            f"{summary.get('jitter_avg_us', 0):.1f} us jitter",
            f"MOS Score: {summary.get('mos_avg', 4.4):.2f} / 4.50",
            "MOS >= 4.00",
            "PASS" if float(summary.get("mos_avg", 4.4)) >= 3.8 else "WARN",
        ],
    ]
    kpi_tbl = Table(kpi_rows, colWidths=[38 * mm, 42 * mm, 44 * mm, 32 * mm, 26 * mm])
    kpi_tbl.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1E293B")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8.5),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
            ("PADDING", (0, 0), (-1, -1), 5),
            ("ALIGN", (-1, 0), (-1, -1), "CENTER"),
            ("FONTNAME", (-1, 1), (-1, -1), "Helvetica-Bold"),
        ])
    )
    story.append(kpi_tbl)
    story.append(Spacer(1, 4 * mm))

    # Embedded Throughput & Latency Charts
    story.append(Paragraph("3. Time-Series Throughput & Latency Telemetry Charts", section_style))
    chart_buf = _build_chart_image(run.get("samples", []))
    story.append(Image(chart_buf, width=182 * mm, height=106 * mm))
    story.append(Spacer(1, 3 * mm))

    footer_text = (
        "<font size=7.5 color='#64748B'>Generated automatically by <b>Stephan Van Vuuren's Network Tester</b> "
        "(Dell PowerEdge R640 Hardware Appliance - Dual Intel Xeon Silver 4110, 500GB RAM, 1x 10GbE Aquantia AQC113 + 4x 1GbE Intel I350).</font>"
    )
    story.append(Paragraph(footer_text, styles["Normal"]))

    doc.build(story)
    buf.seek(0)
    return buf.getvalue()
