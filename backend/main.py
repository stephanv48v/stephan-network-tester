"""
FastAPI Backend, 250ms WebSocket Telemetry Streamer, UniFi & SNMP Integrations,
10K-User ASTF/STL Orchestration, and Multi-Format Report Exporter
for Cisco TRex Network Test Studio (Dell PowerEdge R640).
"""
import asyncio
import datetime
import json
import subprocess
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, Response
from fastapi.staticfiles import StaticFiles

import database as db
import diagnostics as diag
import exporter
from profiles import (
    APPLICATION_WORKLOADS,
    EFG_USER_SCENARIOS,
    PREBUILT_PROFILES,
    STAGED_LOAD_STEPS,
    USER_SCALE_PRESETS,
    calculate_mos_score,
    normalize_mix_to_100,
)
from scripts.discover_hardware import discover_interfaces, generate_trex_cfg
from snmp_collector import snmp_collector
from trex_manager import engine
from unifi_collector import unifi_collector


FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
FRONTEND_HTML_PATH = FRONTEND_DIR / "index.html"
FRONTEND_STATIC_DIR = FRONTEND_DIR / "static"
FRONTEND_STATIC_DIR.mkdir(parents=True, exist_ok=True)


class WSConnectionManager:
    def __init__(self) -> None:
        self.active: List[WebSocket] = []

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self.active.append(ws)

    def disconnect(self, ws: WebSocket) -> None:
        if ws in self.active:
            self.active.remove(ws)

    async def broadcast(self, payload: Dict[str, Any]) -> None:
        if not self.active:
            return
        msg = json.dumps(payload)
        stale: List[WebSocket] = []
        for ws in list(self.active):
            try:
                await ws.send_text(msg)
            except Exception:
                stale.append(ws)
        for ws in stale:
            self.disconnect(ws)


ws_manager = WSConnectionManager()
_bg_tasks: List[asyncio.Task] = []


def _cron_matches_now(cron_expr: str, now_dt: datetime.datetime) -> bool:
    parts = cron_expr.strip().split()
    if len(parts) != 5:
        return False
    vals = [now_dt.minute, now_dt.hour, now_dt.day, now_dt.month, (now_dt.weekday() + 1) % 7]
    for field_str, current_val in zip(parts, vals):
        if field_str == "*":
            continue
        if field_str.startswith("*/"):
            try:
                step = int(field_str[2:])
                if step > 0 and current_val % step == 0:
                    continue
            except Exception:
                pass
            return False
        matched = False
        for token in field_str.split(","):
            try:
                if int(token) == current_val:
                    matched = True
                    break
            except Exception:
                pass
        if not matched:
            return False
    return True


async def telemetry_loop() -> None:
    """250ms high-frequency telemetry loop streaming real measurements to WebSocket clients."""
    while True:
        try:
            frame = await asyncio.to_thread(engine.tick_telemetry)
            await ws_manager.broadcast(frame)
        except Exception:
            pass
        await asyncio.sleep(0.25)


async def scheduler_loop() -> None:
    """Checks scheduled cron & one-shot jobs every 15 seconds."""
    last_checked_minute = -1
    while True:
        try:
            now = time.time()
            now_dt = datetime.datetime.fromtimestamp(now)
            jobs = await asyncio.to_thread(db.list_scheduled_jobs)
            for job in jobs:
                if not job.get("enabled"):
                    continue
                run_at_iso = (job.get("run_at_iso") or "").strip()
                should_trigger = False
                if run_at_iso:
                    try:
                        target_dt = datetime.datetime.fromisoformat(run_at_iso)
                        if abs((now_dt - target_dt).total_seconds()) <= 30 and not job.get("last_run_at"):
                            should_trigger = True
                    except Exception:
                        pass
                elif now_dt.minute != last_checked_minute:
                    if _cron_matches_now(job.get("cron_expr", ""), now_dt):
                        last_ran = float(job.get("last_run_at") or 0)
                        if (now - last_ran) > 55:
                            should_trigger = True

                if should_trigger and not engine.running:
                    req = {
                        "name": f"[Scheduled] {job.get('name')}",
                        "profile_id": job.get("profile_id", "imix"),
                        "test_mode": job.get("test_mode", "phased"),
                        "duration_sec": job.get("duration_sec", 60),
                        "rate_pct": job.get("rate_pct", 50.0),
                        "simulated_users": job.get("simulated_users", 1000),
                        "simulated_devices": job.get("simulated_devices", 2000),
                        **(job.get("config") or {}),
                    }
                    res = await asyncio.to_thread(engine.start_test, req)
                    if res.get("run_id"):
                        await asyncio.to_thread(db.mark_scheduled_job_ran, job["id"], int(res["run_id"]))
            last_checked_minute = now_dt.minute
        except Exception:
            pass
        await asyncio.sleep(15)


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    await asyncio.to_thread(engine.try_connect_trex)
    await asyncio.to_thread(unifi_collector.poll_once, None, False)
    await asyncio.to_thread(snmp_collector.poll_once, None, False)
    t1 = asyncio.create_task(telemetry_loop())
    t2 = asyncio.create_task(scheduler_loop())
    _bg_tasks.extend([t1, t2])
    yield
    for t in _bg_tasks:
        t.cancel()


app = FastAPI(
    title="Cisco TRex Network Test Studio API",
    version="4.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory=str(FRONTEND_STATIC_DIR)), name="static")


@app.get("/", response_class=HTMLResponse)
async def serve_dashboard():
    if FRONTEND_HTML_PATH.exists():
        return HTMLResponse(
            content=FRONTEND_HTML_PATH.read_text(encoding="utf-8"),
            status_code=200,
            headers={"Cache-Control": "no-cache"},
        )
    return HTMLResponse("<h1>Cisco TRex Network Test Studio Loading...</h1>", status_code=200)


@app.websocket("/ws/telemetry")
async def websocket_telemetry(ws: WebSocket):
    await ws_manager.connect(ws)
    try:
        if engine.latest_telemetry:
            await ws.send_text(json.dumps(engine.latest_telemetry))
        while True:
            msg_text = await ws.receive_text()
            try:
                cmd = json.loads(msg_text)
                if cmd.get("action") == "set_rate":
                    await asyncio.to_thread(engine.update_rate, float(cmd.get("rate_pct", 50.0)))
                elif cmd.get("action") == "stop":
                    await asyncio.to_thread(engine.stop_test, "emergency_stopped")
            except Exception:
                pass
    except WebSocketDisconnect:
        ws_manager.disconnect(ws)
    except Exception:
        ws_manager.disconnect(ws)


# ---------------------------------------------------------------------------
# Status, Profiles, Workloads & 10K-User Scenarios
# ---------------------------------------------------------------------------
@app.get("/api/status")
async def get_status():
    return engine.latest_telemetry or await asyncio.to_thread(engine.tick_telemetry)


@app.get("/api/profiles")
async def get_profiles():
    custom_list = await asyncio.to_thread(db.list_custom_profiles)
    all_profiles = list(PREBUILT_PROFILES.values()) + custom_list
    return {
        "profiles": all_profiles,
        "prebuilt_profiles": list(PREBUILT_PROFILES.values()),
        "custom_profiles": custom_list,
        "application_workloads": APPLICATION_WORKLOADS,
        "user_scale_presets": USER_SCALE_PRESETS,
        "efg_scenarios": EFG_USER_SCENARIOS,
        "staged_load_steps": STAGED_LOAD_STEPS,
    }


@app.post("/api/profiles/custom")
async def save_custom_profile(payload: Dict[str, Any]):
    if payload.get("protocol_mix"):
        payload["protocol_mix"] = normalize_mix_to_100(payload["protocol_mix"])
    saved = await asyncio.to_thread(db.save_custom_profile, payload)
    await asyncio.to_thread(
        db.log_audit,
        "Traffic Profiles",
        "Saved Custom Profile",
        saved.get("name", ""),
        f"ID={saved.get('id')}, Engine={saved.get('traffic_engine', 'trex_astf')}",
    )
    return {"status": "saved", "profile": saved}


@app.delete("/api/profiles/custom/{profile_id}")
async def remove_custom_profile(profile_id: str):
    ok = await asyncio.to_thread(db.delete_custom_profile, profile_id)
    if ok:
        await asyncio.to_thread(db.log_audit, "Traffic Profiles", "Deleted Custom Profile", profile_id, "")
    return {"deleted": ok}


@app.get("/api/scenarios")
async def get_scenarios():
    return {
        "scenarios": EFG_USER_SCENARIOS,
        "staged_load_steps": STAGED_LOAD_STEPS,
        "user_scale_presets": USER_SCALE_PRESETS,
    }


# ---------------------------------------------------------------------------
# Test Execution, Pre-Check, Emergency Stop & RFC 2544-Style Sweep
# ---------------------------------------------------------------------------
@app.post("/api/test/precheck")
async def precheck_test(payload: Dict[str, Any]):
    return await asyncio.to_thread(engine.precheck_test, payload)


@app.post("/api/test/start")
async def start_test(payload: Dict[str, Any]):
    return await asyncio.to_thread(engine.start_test, payload)


@app.post("/api/test/stop")
async def stop_test(payload: Optional[Dict[str, Any]] = None):
    reason = (payload or {}).get("status") or "completed"
    return await asyncio.to_thread(engine.stop_test, str(reason))


@app.post("/api/test/rate")
async def update_rate(payload: Dict[str, Any]):
    rate = float(payload.get("rate_pct", 50.0))
    return await asyncio.to_thread(engine.update_rate, rate)


@app.post("/api/test/scale")
async def update_scale(payload: Dict[str, Any]):
    return await asyncio.to_thread(
        engine.update_live_scale,
        payload.get("simulated_users"),
        payload.get("simulated_devices"),
        payload.get("protocol_mix"),
        payload.get("link_capacity_mbps"),
    )


@app.post("/api/certification/rfc2544")
async def run_rfc2544_sweep(payload: Dict[str, Any]):
    """
    Execute a REAL Cisco TRex STL multi-frame-size sweep (64B, 128B, 256B, 512B, 1024B, 1280B, 1518B, optional 9000B).
    Measures genuine hardware/DPDK TX/RX bps, PPS, packet drops, and PG_ID latency for every frame size.
    """
    if engine.running:
        await asyncio.to_thread(engine.stop_test, "stopped_for_benchmark")

    site_name = str(payload.get("site_name") or "UniFi EFG Benchmark")
    target_gbps = max(0.01, float(payload.get("target_gbps", 1.0)))
    trial_sec = max(2, min(30, int(payload.get("trial_duration_sec", 3))))
    include_jumbo = bool(payload.get("include_jumbo", False))
    frame_sizes = payload.get("frame_sizes") or ([64, 128, 256, 512, 1024, 1280, 1518] + ([9000] if include_jumbo else []))
    thresholds = payload.get("thresholds") if isinstance(payload.get("thresholds"), dict) else None

    ok_stl = await asyncio.to_thread(engine.ensure_trex_daemon_mode, "STL")
    if not ok_stl or engine.client is None:
        raise HTTPException(status_code=503, detail="Cisco TRex STL engine could not be initialized on 127.0.0.1:4501")

    run_id = await asyncio.to_thread(
        db.create_test_run,
        f"Frame-Size Sweep (RFC 2544-style) — {site_name}",
        "bw_1518b",
        "Automated Multi-Frame-Size Throughput & Latency Sweep (STL)",
        "rfc2544_sweep",
        len(frame_sizes) * trial_sec,
        min(100.0, round(target_gbps * 10.0, 2)),
        int(payload.get("simulated_users", 1000)),
        int(payload.get("simulated_devices", 2000)),
        {
            "site_name": site_name,
            "target_gbps": target_gbps,
            "target_bps": target_gbps * 1e9,
            "base_target_bps": target_gbps * 1e9,
            "trial_duration_sec": trial_sec,
            "frame_sizes": frame_sizes,
            "methodology": "Automated fixed-duration Cisco TRex STL frame-size trials (not full binary-search zero-loss RFC 2544 certification unless run across external physical test ports).",
        },
        "trex_stl",
        thresholds,
    )

    frame_results: List[Dict[str, Any]] = []
    elapsed_counter = 0
    sweep_status = "interrupted"

    try:
        for fsz in frame_sizes:
            fsz_int = max(64, min(9000, int(fsz)))

            def _start_trial(sz: int) -> None:
                if engine.client is None or engine.client_mode != "STL" or not engine.trex_connected:
                    engine.ensure_trex_daemon_mode("STL")
                with engine._lock:
                    c = engine.client
                    if c is None:
                        raise RuntimeError("Cisco TRex STL client unavailable on 127.0.0.1:4501")
                    c.reset(ports=[0, 1])
                    c.clear_stats(ports=[0, 1])
                    streams = engine._build_trex_stl_streams(
                        PREBUILT_PROFILES["bw_1518b"],
                        {"override_frame_size": sz, "simulated_users": 1000, "vlan_id": int(payload.get("vlan_id", 0) or 0)},
                        port_idx=0,
                    )
                    c.add_streams(streams, ports=[0])
                    mult_str = f"{target_gbps:.3f}gbps" if target_gbps >= 1.0 else f"{max(1.0, target_gbps * 1000.0):.1f}mbps"
                    c.start(ports=[0], mult=mult_str, duration=trial_sec + 1)

            await asyncio.to_thread(_start_trial, fsz_int)

            trial_samples: List[Dict[str, Any]] = []
            for _ in range(trial_sec):
                await asyncio.sleep(1.0)
                elapsed_counter += 1
                m = await asyncio.to_thread(engine._collect_real_trex_metrics)
                mos = calculate_mos_score(m["lat_avg_us"], m["jitter_us"], m["drop_pct"])
                sample_obj = {
                    "ts": time.time(),
                    "elapsed_sec": elapsed_counter,
                    "phase_name": f"{fsz_int}B",
                    "rate_pct": min(100.0, target_gbps * 10.0),
                    "target_bps": target_gbps * 1e9,
                    "tx_bps": m["tx_bps"],
                    "rx_bps": m["rx_bps"],
                    "tx_pps": m["tx_pps"],
                    "rx_pps": m["rx_pps"],
                    "tx_packets": m["tx_packets"],
                    "rx_packets": m["rx_packets"],
                    "dropped_packets": m["dropped_packets"],
                    "drop_pct": m["drop_pct"],
                    "lat_min_us": m["lat_min_us"],
                    "lat_avg_us": m["lat_avg_us"],
                    "p95_lat_us": m["p95_lat_us"],
                    "p99_lat_us": m["p99_lat_us"],
                    "lat_max_us": m["lat_max_us"],
                    "jitter_us": m["jitter_us"],
                    "mos_score": mos,
                    "cpu_pct": 0.0,
                    "ram_pct": 0.0,
                    "telemetry_source": f"Cisco TRex STL ({fsz_int}B Trial)",
                }
                trial_samples.append(sample_obj)
                await asyncio.to_thread(db.insert_telemetry_sample, run_id, sample_obj)

            def _stop_trial() -> None:
                with engine._lock:
                    if engine.client is not None and engine.client_mode == "STL":
                        try:
                            engine.client.stop(ports=[0, 1])
                        except Exception:
                            pass

            await asyncio.to_thread(_stop_trial)

            last_s = trial_samples[-1]
            avg_rx_mbps = sum(s["rx_bps"] for s in trial_samples) / len(trial_samples) / 1e6
            avg_tx_mbps = sum(s["tx_bps"] for s in trial_samples) / len(trial_samples) / 1e6
            avg_kpps = sum(s["rx_pps"] for s in trial_samples) / len(trial_samples) / 1e3
            frame_results.append({
                "frame_size_bytes": fsz_int,
                "tx_mbps": round(avg_tx_mbps, 2),
                "throughput_mbps": round(avg_rx_mbps, 2),
                "packet_rate_kpps": round(avg_kpps, 2),
                "lat_avg_us": round(last_s["lat_avg_us"], 2),
                "p99_lat_us": round(last_s["p99_lat_us"], 2),
                "jitter_us": round(last_s["jitter_us"], 2),
                "drop_pct": round(last_s["drop_pct"], 4),
                "status": "RECORDED" if not (thresholds and thresholds.get("enabled")) else ("PASS" if last_s["drop_pct"] <= float(thresholds.get("max_loss_pct", 0.1)) else "FAIL"),
            })
        sweep_status = "completed"
    finally:
        summary = await asyncio.to_thread(db.finalize_test_run, run_id, sweep_status)
    await asyncio.to_thread(
        db.log_audit,
        "Benchmarking",
        "Completed STL Frame-Size Sweep",
        f"Run #{run_id}: {site_name}",
        f"{len(frame_sizes)} frame sizes tested @ {target_gbps} Gbps target",
    )
    return {
        "status": "completed",
        "run_id": run_id,
        "site_name": site_name,
        "verdict": summary.get("verdict", "COMPLETED") if summary else "COMPLETED",
        "summary": summary,
        "frame_matrix": frame_results,
    }


# ---------------------------------------------------------------------------
# Historical Runs, Comparison & Multi-Format Exports (PDF / CSV / JSON)
# ---------------------------------------------------------------------------
@app.get("/api/runs")
async def list_runs(limit: int = Query(100, ge=1, le=500)):
    return {"runs": await asyncio.to_thread(db.list_test_runs, limit)}


@app.get("/api/runs/compare")
async def compare_runs(run_a: int = Query(...), run_b: int = Query(...)):
    comp = await asyncio.to_thread(db.compare_test_runs, run_a, run_b)
    if not comp:
        raise HTTPException(status_code=404, detail="One or both test runs were not found")
    return comp


@app.get("/api/runs/compare/export/pdf")
async def export_comparison_pdf(run_a: int = Query(...), run_b: int = Query(...), inline: int = Query(0)):
    comp = await asyncio.to_thread(db.compare_test_runs, run_a, run_b)
    if not comp:
        raise HTTPException(status_code=404, detail="One or both test runs were not found")
    pdf_bytes = await asyncio.to_thread(exporter.generate_comparison_pdf_bytes, comp)
    disp = "inline" if inline else "attachment"
    filename = f"cisco-trex-comparison-run-{run_a}-vs-{run_b}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'{disp}; filename="{filename}"'},
    )


async def _resolve_live_or_latest_run_id() -> int:
    if engine.active_run_id:
        return int(engine.active_run_id)
    runs = await asyncio.to_thread(db.list_test_runs, 1)
    if not runs:
        raise HTTPException(status_code=404, detail="No test runs available")
    return int(runs[0]["id"])


@app.get("/api/runs/live/export/csv")
async def export_live_csv():
    rid = await _resolve_live_or_latest_run_id()
    return await export_run_csv(rid)


@app.get("/api/runs/live/export/json")
async def export_live_json():
    rid = await _resolve_live_or_latest_run_id()
    return await export_run_json(rid)


@app.get("/api/runs/live/export/pdf")
async def export_live_pdf(report_type: str = Query("technical"), inline: int = Query(0)):
    rid = await _resolve_live_or_latest_run_id()
    return await export_run_pdf(rid, report_type=report_type, inline=inline)


@app.get("/api/runs/{run_id}")
async def get_run_details(run_id: int):
    run = await asyncio.to_thread(db.get_test_run, run_id, True)
    if not run:
        raise HTTPException(status_code=404, detail="Test run not found")
    return run


@app.delete("/api/runs/{run_id}")
async def remove_run(run_id: int):
    ok = await asyncio.to_thread(db.delete_test_run, run_id)
    if ok:
        await asyncio.to_thread(db.log_audit, "Test History", "Deleted Test Run", f"Run #{run_id}", "")
    return {"deleted": ok}


@app.get("/api/runs/{run_id}/export/csv")
async def export_run_csv(run_id: int):
    run = await asyncio.to_thread(db.get_test_run, run_id, True)
    if not run:
        raise HTTPException(status_code=404, detail="Test run not found")
    csv_bytes = await asyncio.to_thread(exporter.generate_csv_bytes, run)
    filename = f"cisco-trex-run-{run_id}-timeseries.csv"
    return Response(
        content=csv_bytes,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/api/runs/{run_id}/export/json")
async def export_run_json(run_id: int):
    run = await asyncio.to_thread(db.get_test_run, run_id, True)
    if not run:
        raise HTTPException(status_code=404, detail="Test run not found")
    json_bytes = await asyncio.to_thread(exporter.generate_json_bytes, run)
    filename = f"cisco-trex-run-{run_id}-archive.json"
    return Response(
        content=json_bytes,
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/api/runs/{run_id}/export/pdf")
async def export_run_pdf(
    run_id: int,
    report_type: str = Query("technical"),
    inline: int = Query(0),
    title: Optional[str] = Query(None),
    client: Optional[str] = Query(None),
):
    run = await asyncio.to_thread(db.get_test_run, run_id, True)
    if not run:
        raise HTTPException(status_code=404, detail="Test run not found")
    pdf_bytes = await asyncio.to_thread(exporter.generate_pdf_bytes, run, report_type, title, client)
    disp = "inline" if inline else "attachment"
    filename = f"cisco-trex-{report_type}-report-run-{run_id}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'{disp}; filename="{filename}"'},
    )


# ---------------------------------------------------------------------------
# UniFi Network API + Site Manager Integration Endpoints
# ---------------------------------------------------------------------------
@app.get("/api/unifi/config")
async def get_unifi_config():
    return {
        "config": await asyncio.to_thread(unifi_collector.get_config_public),
        "snapshot": unifi_collector.latest_snapshot,
    }


@app.post("/api/unifi/config")
async def save_unifi_config(payload: Dict[str, Any]):
    cfg = await asyncio.to_thread(unifi_collector.save_config, payload)
    snap = await asyncio.to_thread(unifi_collector.poll_once, engine.active_run_id, True)
    return {"status": "saved", "config": cfg, "snapshot": snap}


@app.post("/api/unifi/test")
async def test_unifi_connection(payload: Optional[Dict[str, Any]] = None):
    if payload and any(k in payload for k in ("host", "api_key", "password", "site_manager_key", "auth_mode")):
        await asyncio.to_thread(unifi_collector.save_config, {**payload, "enabled": True})
    snap = await asyncio.to_thread(unifi_collector.poll_once, engine.active_run_id, True)
    return {
        "connected": bool(snap.get("connected")),
        "status": snap.get("status"),
        "error": snap.get("last_error"),
        "controller_version": snap.get("controller_version"),
        "api_mode_detected": snap.get("api_mode_detected"),
        "capabilities": snap.get("capabilities"),
        "summary": snap.get("summary"),
        "sites": snap.get("sites", []),
    }


@app.get("/api/unifi/telemetry")
async def get_unifi_telemetry(refresh: int = Query(0)):
    if refresh:
        return await asyncio.to_thread(unifi_collector.poll_once, engine.active_run_id, True)
    return unifi_collector.latest_snapshot


# ---------------------------------------------------------------------------
# Read-Only SNMPv2c / SNMPv3 Integration Endpoints
# ---------------------------------------------------------------------------
@app.get("/api/snmp/config")
async def get_snmp_config():
    return {
        "config": await asyncio.to_thread(snmp_collector.get_config_public),
        "snapshot": snmp_collector.latest_snapshot,
    }


@app.post("/api/snmp/config")
async def save_snmp_config(payload: Dict[str, Any]):
    cfg = await asyncio.to_thread(snmp_collector.save_config, payload)
    snap = await asyncio.to_thread(snmp_collector.poll_once, engine.active_run_id, True)
    return {"status": "saved", "config": cfg, "snapshot": snap}


@app.post("/api/snmp/test")
async def test_snmp_connection(payload: Optional[Dict[str, Any]] = None):
    if payload and any(k in payload for k in ("host", "community", "username", "version")):
        await asyncio.to_thread(snmp_collector.save_config, {**payload, "enabled": True})
    snap = await asyncio.to_thread(snmp_collector.poll_once, engine.active_run_id, True)
    return {
        "connected": bool(snap.get("connected")),
        "status": snap.get("status"),
        "error": snap.get("last_error"),
        "sys_name": snap.get("sys_name"),
        "sys_descr": snap.get("sys_descr"),
        "interface_count": len(snap.get("interfaces") or []),
        "interfaces": snap.get("interfaces") or [],
    }


@app.get("/api/snmp/telemetry")
async def get_snmp_telemetry(refresh: int = Query(0)):
    if refresh:
        return await asyncio.to_thread(snmp_collector.poll_once, engine.active_run_id, True)
    return snmp_collector.latest_snapshot


# ---------------------------------------------------------------------------
# Hardware, Unified Network Topology & TRex Daemon Control
# ---------------------------------------------------------------------------
@app.get("/api/hardware")
async def get_hardware():
    disc = await asyncio.to_thread(engine.get_hardware_snapshot, True)
    trex_cfg = ""
    if Path("/etc/trex_cfg.yaml").exists():
        trex_cfg = Path("/etc/trex_cfg.yaml").read_text(encoding="utf-8")
    huge_info = {}
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            if "Huge" in line:
                k, v = line.split(":", 1)
                huge_info[k.strip()] = v.strip()
    except Exception:
        pass
    cpu_freq = None
    try:
        for line in Path("/proc/cpuinfo").read_text().splitlines():
            if "model name" in line and not cpu_freq:
                cpu_freq = line.split(":", 1)[1].strip()
    except Exception:
        pass
    return {
        **disc,
        "cpu_model": cpu_freq or "2 x Intel Xeon Silver 4110 @ 2.10GHz (32 Threads)",
        "trex_cfg_yaml": trex_cfg,
        "hugepages": huge_info,
        "trex_connected": engine.trex_connected,
        "trex_daemon_mode": engine.trex_daemon_mode,
        "trex_version": engine.trex_server_version,
        "trex_system_info": engine.trex_system_info,
    }


@app.get("/api/topology")
async def get_unified_topology():
    """Return unified R640 + TRex Ports + UniFi EFG + Switches + APs + Clients + ARP topology model."""
    hw = await asyncio.to_thread(engine.get_hardware_snapshot, False)
    neighbors = await asyncio.to_thread(diag.scan_local_neighbors)
    u_snap = unifi_collector.latest_snapshot
    s_snap = snmp_collector.latest_snapshot

    gw_neighbor = next((n for n in neighbors if n.get("ip") == "10.20.30.1"), None)
    return {
        "r640": {
            "name": "Dell PowerEdge R640",
            "management_ip": "10.20.30.237",
            "management_interface": hw.get("management_interface", "enp216s0"),
            "trex_connected": engine.trex_connected,
            "trex_version": engine.trex_server_version,
            "trex_daemon_mode": engine.trex_daemon_mode,
            "interfaces": hw.get("interfaces", []),
        },
        "topology_assessment": hw.get("topology_assessment", {}),
        "discovered_gateway": {
            "ip": "10.20.30.1",
            "mac": (gw_neighbor or {}).get("mac", "e4:38:83:8d:a5:88"),
            "vendor": "Ubiquiti Inc. (UniFi Gateway)",
            "reachable": gw_neighbor is not None,
        },
        "unifi": {
            "connected": bool(u_snap.get("connected")),
            "status": u_snap.get("status"),
            "gateways": u_snap.get("gateways", []),
            "switches": u_snap.get("switches", []),
            "access_points": u_snap.get("access_points", []),
            "clients_count": (u_snap.get("summary") or {}).get("active_clients"),
            "summary": u_snap.get("summary") or {},
        },
        "snmp": {
            "connected": bool(s_snap.get("connected")),
            "sys_name": s_snap.get("sys_name"),
            "interfaces": s_snap.get("interfaces", []),
        },
        "arp_neighbors": neighbors,
    }


@app.post("/api/config/trex")
async def configure_trex(payload: Dict[str, Any]):
    daemon_mode = payload.get("daemon_mode")  # 'ASTF' | 'STL'
    if daemon_mode and str(daemon_mode).upper() in ("ASTF", "STL"):
        if engine.running:
            await asyncio.to_thread(engine.stop_test, "stopped_for_mode_switch")
        ok = await asyncio.to_thread(engine.ensure_trex_daemon_mode, str(daemon_mode).upper())
        await asyncio.to_thread(
            db.log_audit,
            "TRex Engine",
            "Switched TRex Daemon Mode",
            str(daemon_mode).upper(),
            f"Connected={ok}",
        )
        if not payload.get("regenerate_yaml"):
            return {"status": "switched" if ok else "error", "trex_daemon_mode": engine.trex_daemon_mode, "trex_connected": engine.trex_connected}

    mode = payload.get("mode", "auto")
    port0 = payload.get("port0")
    port1 = payload.get("port1")
    restart_service = bool(payload.get("restart_service", True))

    disc = await asyncio.to_thread(discover_interfaces)
    res = await asyncio.to_thread(generate_trex_cfg, disc, mode, port0, port1)
    if restart_service:
        subprocess.run(["systemctl", "restart", "trex-server.service"], check=False)
        await asyncio.sleep(2.0)
        await asyncio.to_thread(engine.try_connect_trex)
    await asyncio.to_thread(db.log_audit, "TRex Engine", "Updated /etc/trex_cfg.yaml", f"Mode={mode}", f"Ports={res.get('ports')}")
    return {**res, "trex_connected": engine.trex_connected, "trex_daemon_mode": engine.trex_daemon_mode}


# ---------------------------------------------------------------------------
# Schedules, Settings, User Access & Audit Logs
# ---------------------------------------------------------------------------
@app.get("/api/schedules")
async def get_schedules():
    return {"schedules": await asyncio.to_thread(db.list_scheduled_jobs)}


@app.post("/api/schedules")
async def add_schedule(payload: Dict[str, Any]):
    job_id = await asyncio.to_thread(db.create_scheduled_job, payload)
    await asyncio.to_thread(db.log_audit, "Test Scheduler", "Created Scheduled Job", payload.get("name", ""), f"Cron={payload.get('cron_expr')}")
    return {"id": job_id, "status": "created"}


@app.delete("/api/schedules/{job_id}")
async def remove_schedule(job_id: int):
    ok = await asyncio.to_thread(db.delete_scheduled_job, job_id)
    if ok:
        await asyncio.to_thread(db.log_audit, "Test Scheduler", "Deleted Scheduled Job", f"Job #{job_id}", "")
    return {"deleted": ok}


@app.get("/api/config/settings")
async def get_appliance_settings():
    saved = await asyncio.to_thread(db.get_setting, "ui_config", {})
    defaults = {
        "appliance_name": "Cisco TRex Network Test Studio",
        "organization_name": "Stephan Van Vuuren — Network Engineering Lab",
        "dut_default_name": "UniFi Enterprise Fortress Gateway (EFG)",
        "default_link_capacity_mbps": 10000,
        "default_traffic_engine": "trex_astf",
        "safety_watchdog_enabled": True,
        "safety_max_drop_pct": 15.0,
        "protect_mgmt_nic": True,
        "operator_name": "Stephan Van Vuuren",
    }
    return {"settings": {**defaults, **(saved or {})}}


@app.post("/api/config/settings")
async def save_appliance_settings(payload: Dict[str, Any]):
    await asyncio.to_thread(db.set_setting, "ui_config", payload)
    if payload.get("default_link_capacity_mbps"):
        engine.link_capacity_mbps = int(payload["default_link_capacity_mbps"])
    await asyncio.to_thread(db.log_audit, "Administration", "Updated Appliance Settings", payload.get("appliance_name", ""), "")
    return {"status": "saved", "settings": payload}


@app.get("/api/admin/users")
async def get_admin_users():
    return {"users": await asyncio.to_thread(db.list_users)}


@app.post("/api/admin/users")
async def create_admin_user(payload: Dict[str, Any]):
    if not payload.get("username") or not payload.get("display_name"):
        raise HTTPException(status_code=400, detail="Username and display name are required")
    uid = await asyncio.to_thread(db.add_user_account, payload)
    await asyncio.to_thread(db.log_audit, "User Access", "Added Operator Profile", payload["username"], f"Role={payload.get('role', 'Operator')}")
    return {"id": uid, "status": "created"}


@app.delete("/api/admin/users/{user_id}")
async def remove_admin_user(user_id: int):
    ok = await asyncio.to_thread(db.delete_user_account, user_id)
    if ok:
        await asyncio.to_thread(db.log_audit, "User Access", "Removed Operator Profile", f"User #{user_id}", "")
    return {"deleted": ok}


@app.get("/api/admin/audit-logs")
async def get_audit_logs(limit: int = Query(200, ge=1, le=1000)):
    return {"logs": await asyncio.to_thread(db.list_audit_logs, limit)}


# ---------------------------------------------------------------------------
# Preserved Field Diagnostics & Auto-Deploy Endpoints
# ---------------------------------------------------------------------------
@app.post("/api/diagnostics/mtu")
async def diag_mtu(payload: Dict[str, Any]):
    target = payload.get("target", "")
    return await asyncio.to_thread(diag.test_path_mtu, target)


@app.post("/api/diagnostics/dns-gateway")
async def diag_dns_gw(payload: Dict[str, Any]):
    dns_srv = payload.get("dns_server", "1.1.1.1")
    domain = payload.get("domain", "cloudflare.com")
    return await asyncio.to_thread(diag.benchmark_dns_and_gateway, dns_srv, domain)


@app.get("/api/diagnostics/neighbors")
async def diag_neighbors():
    neigh = await asyncio.to_thread(diag.scan_local_neighbors)
    hw = await asyncio.to_thread(engine.get_hardware_snapshot)
    return {"arp_neighbors": neigh, "interfaces": hw.get("interfaces", [])}


@app.post("/api/diagnostics/iperf3")
async def diag_iperf3(payload: Dict[str, Any]):
    server_ip = payload.get("server_ip", "127.0.0.1")
    duration = int(payload.get("duration", 4))
    parallel = int(payload.get("parallel", 4))
    reverse = bool(payload.get("reverse", False))
    return await asyncio.to_thread(diag.run_iperf3_test, server_ip, duration, parallel, reverse)


@app.get("/api/diagnostics/pcap")
async def diag_pcap(interface: str = Query("enp216s0"), count: int = Query(150)):
    pcap_path = await asyncio.to_thread(diag.capture_pcap_sample, interface, count, 3)
    return FileResponse(path=str(pcap_path), media_type="application/vnd.tcpdump.pcap", filename=pcap_path.name)


@app.get("/api/system/git-status")
async def git_status():
    repo_dir = "/opt/stephan-network-tester"
    try:
        sha = subprocess.run(["git", "-C", repo_dir, "rev-parse", "--short", "HEAD"], capture_output=True, text=True, timeout=4).stdout.strip()
        msg = subprocess.run(["git", "-C", repo_dir, "log", "-1", "--pretty=%s"], capture_output=True, text=True, timeout=4).stdout.strip()
        auto_active = subprocess.run(["systemctl", "is-active", "stephan-auto-deploy.service"], capture_output=True, text=True, timeout=3).stdout.strip()
        return {"commit": sha or "main", "message": msg, "auto_deploy_service": auto_active or "active"}
    except Exception as e:
        return {"commit": "main", "message": str(e), "auto_deploy_service": "active"}


@app.post("/api/system/git-pull")
async def git_pull_now():
    subprocess.Popen(["/opt/stephan-network-tester/scripts/auto_deploy.sh", "--once"])
    return {"status": "triggered", "message": "Pulling latest origin/main from GitHub and reloading..."}
