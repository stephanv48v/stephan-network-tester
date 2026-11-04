"""
SQLite Database Layer for Stephan Van Vuuren's Network Tester
Stores test runs, 1-second time-series telemetry samples, scheduled cron jobs, and appliance settings.
"""
import json
import os
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

DB_DIR = Path("/opt/stephan-network-tester/data")
if not DB_DIR.exists():
    try:
        DB_DIR.mkdir(parents=True, exist_ok=True)
    except Exception:
        DB_DIR = Path(__file__).resolve().parent

DB_PATH = DB_DIR / "network_tester.db"
_lock = threading.Lock()


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False, timeout=15.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    return conn


def init_db() -> None:
    with _lock:
        conn = get_conn()
        try:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS test_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    profile_id TEXT NOT NULL,
                    profile_name TEXT NOT NULL,
                    test_mode TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'running',
                    started_at REAL NOT NULL,
                    ended_at REAL,
                    duration_sec INTEGER DEFAULT 0,
                    target_rate_pct REAL DEFAULT 25.0,
                    simulated_users INTEGER DEFAULT 100,
                    simulated_devices INTEGER DEFAULT 250,
                    config_json TEXT,
                    summary_json TEXT,
                    verdict TEXT DEFAULT 'PASS'
                );

                CREATE TABLE IF NOT EXISTS telemetry_samples (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id INTEGER NOT NULL,
                    ts REAL NOT NULL,
                    elapsed_sec INTEGER NOT NULL,
                    rate_pct REAL NOT NULL,
                    tx_bps REAL NOT NULL,
                    rx_bps REAL NOT NULL,
                    tx_pps REAL NOT NULL,
                    rx_pps REAL NOT NULL,
                    tx_packets INTEGER NOT NULL,
                    rx_packets INTEGER NOT NULL,
                    dropped_packets INTEGER NOT NULL,
                    drop_pct REAL NOT NULL,
                    lat_min_us REAL NOT NULL,
                    lat_avg_us REAL NOT NULL,
                    lat_max_us REAL NOT NULL,
                    jitter_us REAL NOT NULL,
                    mos_score REAL NOT NULL,
                    cpu_pct REAL NOT NULL,
                    ram_pct REAL NOT NULL,
                    FOREIGN KEY(run_id) REFERENCES test_runs(id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_samples_run_id ON telemetry_samples(run_id);

                CREATE TABLE IF NOT EXISTS scheduled_jobs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    cron_expr TEXT NOT NULL,
                    run_at_iso TEXT,
                    profile_id TEXT NOT NULL,
                    test_mode TEXT NOT NULL DEFAULT 'timed',
                    duration_sec INTEGER NOT NULL DEFAULT 60,
                    rate_pct REAL NOT NULL DEFAULT 50.0,
                    simulated_users INTEGER NOT NULL DEFAULT 500,
                    simulated_devices INTEGER NOT NULL DEFAULT 1200,
                    config_json TEXT,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    last_run_at REAL,
                    last_run_id INTEGER,
                    created_at REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS appliance_settings (
                    key TEXT PRIMARY KEY,
                    value_json TEXT NOT NULL,
                    updated_at REAL NOT NULL
                );
                """
            )
            conn.commit()
        finally:
            conn.close()


def create_test_run(
    name: str,
    profile_id: str,
    profile_name: str,
    test_mode: str,
    duration_sec: int,
    target_rate_pct: float,
    simulated_users: int,
    simulated_devices: int,
    config: Dict[str, Any],
) -> int:
    with _lock:
        conn = get_conn()
        try:
            cur = conn.execute(
                """
                INSERT INTO test_runs (
                    name, profile_id, profile_name, test_mode, status,
                    started_at, duration_sec, target_rate_pct,
                    simulated_users, simulated_devices, config_json
                ) VALUES (?, ?, ?, ?, 'running', ?, ?, ?, ?, ?, ?)
                """,
                (
                    name,
                    profile_id,
                    profile_name,
                    test_mode,
                    time.time(),
                    duration_sec,
                    target_rate_pct,
                    simulated_users,
                    simulated_devices,
                    json.dumps(config),
                ),
            )
            conn.commit()
            return int(cur.lastrowid)
        finally:
            conn.close()


def insert_telemetry_sample(run_id: int, sample: Dict[str, Any]) -> None:
    with _lock:
        conn = get_conn()
        try:
            conn.execute(
                """
                INSERT INTO telemetry_samples (
                    run_id, ts, elapsed_sec, rate_pct,
                    tx_bps, rx_bps, tx_pps, rx_pps,
                    tx_packets, rx_packets, dropped_packets, drop_pct,
                    lat_min_us, lat_avg_us, lat_max_us, jitter_us, mos_score,
                    cpu_pct, ram_pct
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    sample.get("ts", time.time()),
                    int(sample.get("elapsed_sec", 0)),
                    float(sample.get("rate_pct", 0.0)),
                    float(sample.get("tx_bps", 0.0)),
                    float(sample.get("rx_bps", 0.0)),
                    float(sample.get("tx_pps", 0.0)),
                    float(sample.get("rx_pps", 0.0)),
                    int(sample.get("tx_packets", 0)),
                    int(sample.get("rx_packets", 0)),
                    int(sample.get("dropped_packets", 0)),
                    float(sample.get("drop_pct", 0.0)),
                    float(sample.get("lat_min_us", 0.0)),
                    float(sample.get("lat_avg_us", 0.0)),
                    float(sample.get("lat_max_us", 0.0)),
                    float(sample.get("jitter_us", 0.0)),
                    float(sample.get("mos_score", 4.4)),
                    float(sample.get("cpu_pct", 0.0)),
                    float(sample.get("ram_pct", 0.0)),
                ),
            )
            conn.commit()
        finally:
            conn.close()


def finalize_test_run(run_id: int, status: str = "completed") -> Optional[Dict[str, Any]]:
    with _lock:
        conn = get_conn()
        try:
            ended_at = time.time()
            row = conn.execute("SELECT * FROM test_runs WHERE id = ?", (run_id,)).fetchone()
            if not row:
                return None

            samples = conn.execute(
                "SELECT * FROM telemetry_samples WHERE run_id = ? ORDER BY elapsed_sec ASC",
                (run_id,),
            ).fetchall()

            if samples:
                max_tx_bps = max(s["tx_bps"] for s in samples)
                avg_tx_bps = sum(s["tx_bps"] for s in samples) / len(samples)
                max_rx_bps = max(s["rx_bps"] for s in samples)
                avg_rx_bps = sum(s["rx_bps"] for s in samples) / len(samples)
                max_tx_pps = max(s["tx_pps"] for s in samples)
                avg_tx_pps = sum(s["tx_pps"] for s in samples) / len(samples)
                total_tx_pkts = samples[-1]["tx_packets"]
                total_rx_pkts = samples[-1]["rx_packets"]
                total_drops = samples[-1]["dropped_packets"]
                overall_drop_pct = samples[-1]["drop_pct"]
                min_lat = min(s["lat_min_us"] for s in samples)
                avg_lat = sum(s["lat_avg_us"] for s in samples) / len(samples)
                max_lat = max(s["lat_max_us"] for s in samples)
                avg_jitter = sum(s["jitter_us"] for s in samples) / len(samples)
                avg_mos = sum(s["mos_score"] for s in samples) / len(samples)
            else:
                max_tx_bps = avg_tx_bps = max_rx_bps = avg_rx_bps = 0.0
                max_tx_pps = avg_tx_pps = 0.0
                total_tx_pkts = total_rx_pkts = total_drops = 0
                overall_drop_pct = 0.0
                min_lat = avg_lat = max_lat = avg_jitter = 0.0
                avg_mos = 4.4

            # Verdict Pass/Fail criteria: < 1.0% frame loss and < 2000us avg latency
            verdict = "PASS"
            if overall_drop_pct > 1.0 or avg_lat > 5000.0:
                verdict = "FAIL"
            elif overall_drop_pct > 0.1 or avg_lat > 1500.0:
                verdict = "WARN"

            actual_duration = max(1, int(ended_at - float(row["started_at"])))
            summary = {
                "sample_count": len(samples),
                "actual_duration_sec": actual_duration,
                "max_tx_bps": round(max_tx_bps, 2),
                "avg_tx_bps": round(avg_tx_bps, 2),
                "max_rx_bps": round(max_rx_bps, 2),
                "avg_rx_bps": round(avg_rx_bps, 2),
                "max_tx_pps": round(max_tx_pps, 2),
                "avg_tx_pps": round(avg_tx_pps, 2),
                "total_tx_packets": total_tx_pkts,
                "total_rx_packets": total_rx_pkts,
                "total_dropped_packets": total_drops,
                "drop_pct": round(overall_drop_pct, 4),
                "lat_min_us": round(min_lat, 2),
                "lat_avg_us": round(avg_lat, 2),
                "lat_max_us": round(max_lat, 2),
                "jitter_avg_us": round(avg_jitter, 2),
                "mos_avg": round(avg_mos, 2),
                "verdict": verdict,
            }

            conn.execute(
                """
                UPDATE test_runs
                SET status = ?, ended_at = ?, duration_sec = ?, summary_json = ?, verdict = ?
                WHERE id = ?
                """,
                (status, ended_at, actual_duration, json.dumps(summary), verdict, run_id),
            )
            conn.commit()
            return summary
        finally:
            conn.close()


def list_test_runs(limit: int = 50) -> List[Dict[str, Any]]:
    with _lock:
        conn = get_conn()
        try:
            rows = conn.execute(
                "SELECT * FROM test_runs ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
            result = []
            for r in rows:
                d = dict(r)
                d["config"] = json.loads(d.pop("config_json") or "{}")
                d["summary"] = json.loads(d.pop("summary_json") or "{}")
                result.append(d)
            return result
        finally:
            conn.close()


def get_test_run(run_id: int, include_samples: bool = True) -> Optional[Dict[str, Any]]:
    with _lock:
        conn = get_conn()
        try:
            row = conn.execute("SELECT * FROM test_runs WHERE id = ?", (run_id,)).fetchone()
            if not row:
                return None
            d = dict(row)
            d["config"] = json.loads(d.pop("config_json") or "{}")
            d["summary"] = json.loads(d.pop("summary_json") or "{}")
            if include_samples:
                s_rows = conn.execute(
                    "SELECT * FROM telemetry_samples WHERE run_id = ? ORDER BY elapsed_sec ASC",
                    (run_id,),
                ).fetchall()
                d["samples"] = [dict(s) for s in s_rows]
            return d
        finally:
            conn.close()


def delete_test_run(run_id: int) -> bool:
    with _lock:
        conn = get_conn()
        try:
            conn.execute("DELETE FROM telemetry_samples WHERE run_id = ?", (run_id,))
            cur = conn.execute("DELETE FROM test_runs WHERE id = ?", (run_id,))
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()


def create_scheduled_job(job: Dict[str, Any]) -> int:
    with _lock:
        conn = get_conn()
        try:
            cur = conn.execute(
                """
                INSERT INTO scheduled_jobs (
                    name, cron_expr, run_at_iso, profile_id, test_mode,
                    duration_sec, rate_pct, simulated_users, simulated_devices,
                    config_json, enabled, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job.get("name", "Scheduled Network Strain Test"),
                    job.get("cron_expr", "0 2 * * *"),
                    job.get("run_at_iso", ""),
                    job.get("profile_id", "imix"),
                    job.get("test_mode", "timed"),
                    int(job.get("duration_sec", 60)),
                    float(job.get("rate_pct", 50.0)),
                    int(job.get("simulated_users", 500)),
                    int(job.get("simulated_devices", 1200)),
                    json.dumps(job.get("config", {})),
                    1 if job.get("enabled", True) else 0,
                    time.time(),
                ),
            )
            conn.commit()
            return int(cur.lastrowid)
        finally:
            conn.close()


def list_scheduled_jobs() -> List[Dict[str, Any]]:
    with _lock:
        conn = get_conn()
        try:
            rows = conn.execute("SELECT * FROM scheduled_jobs ORDER BY id DESC").fetchall()
            out = []
            for r in rows:
                d = dict(r)
                d["config"] = json.loads(d.pop("config_json") or "{}")
                d["enabled"] = bool(d["enabled"])
                out.append(d)
            return out
        finally:
            conn.close()


def delete_scheduled_job(job_id: int) -> bool:
    with _lock:
        conn = get_conn()
        try:
            cur = conn.execute("DELETE FROM scheduled_jobs WHERE id = ?", (job_id,))
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()


def mark_scheduled_job_ran(job_id: int, run_id: int) -> None:
    with _lock:
        conn = get_conn()
        try:
            conn.execute(
                "UPDATE scheduled_jobs SET last_run_at = ?, last_run_id = ? WHERE id = ?",
                (time.time(), run_id, job_id),
            )
            conn.commit()
        finally:
            conn.close()


def get_setting(key: str, default: Any = None) -> Any:
    with _lock:
        conn = get_conn()
        try:
            row = conn.execute(
                "SELECT value_json FROM appliance_settings WHERE key = ?", (key,)
            ).fetchone()
            if not row:
                return default
            return json.loads(row["value_json"])
        finally:
            conn.close()


def set_setting(key: str, value: Any) -> None:
    with _lock:
        conn = get_conn()
        try:
            conn.execute(
                """
                INSERT INTO appliance_settings (key, value_json, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET value_json = excluded.value_json, updated_at = excluded.updated_at
                """,
                (key, json.dumps(value), time.time()),
            )
            conn.commit()
        finally:
            conn.close()
