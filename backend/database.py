"""
SQLite Database Layer, Non-Destructive Schema Migrations, Encrypted Credential Vault,
and Audit Logger for Cisco TRex Network Test Studio (Dell PowerEdge R640).
Preserves all existing test_runs, telemetry_samples, scheduled_jobs, and appliance_settings.
"""
import base64
import hashlib
import json
import os
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from cryptography.fernet import Fernet
    FERNET_AVAILABLE = True
except Exception:
    FERNET_AVAILABLE = False

# STEPHAN_DATA_DIR lets local/dev runs keep their DB elsewhere; the appliance uses the default.
DB_DIR = Path(os.environ.get("STEPHAN_DATA_DIR") or "/opt/stephan-network-tester/data")
if not DB_DIR.exists():
    try:
        DB_DIR.mkdir(parents=True, exist_ok=True)
    except Exception:
        DB_DIR = Path(__file__).resolve().parent

DB_PATH = DB_DIR / "network_tester.db"
KEY_PATH = DB_DIR / ".secret.key"
_lock = threading.Lock()


def _get_fernet() -> Optional[Any]:
    if not FERNET_AVAILABLE:
        return None
    try:
        if not KEY_PATH.exists():
            key = Fernet.generate_key()
            # Create atomically with 0600 (no world-readable window, no clobbering by a concurrent creator)
            try:
                fd = os.open(str(KEY_PATH), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            except FileExistsError:
                fd = None
            if fd is not None:
                with os.fdopen(fd, "wb") as fh:
                    fh.write(key)
        return Fernet(KEY_PATH.read_bytes().strip())
    except Exception:
        # Deterministic machine-local fallback key derived from machine-id
        mid = "stephan-r640-local-vault"
        if Path("/etc/machine-id").exists():
            mid = Path("/etc/machine-id").read_text().strip()
        derived = base64.urlsafe_b64encode(hashlib.sha256(mid.encode()).digest())
        return Fernet(derived)


def encrypt_secret(plain: str) -> str:
    if not plain:
        return ""
    f = _get_fernet()
    if f is None:
        return "b64:" + base64.b64encode(plain.encode("utf-8")).decode("ascii")
    return "enc:" + f.encrypt(plain.encode("utf-8")).decode("ascii")


def decrypt_secret(token: str) -> str:
    if not token:
        return ""
    try:
        if token.startswith("enc:"):
            f = _get_fernet()
            if f is not None:
                return f.decrypt(token[4:].encode("ascii")).decode("utf-8")
        if token.startswith("b64:"):
            return base64.b64decode(token[4:].encode("ascii")).decode("utf-8")
        return token
    except Exception:
        return ""


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False, timeout=20.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    return conn


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, col_def: str) -> None:
    cols = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in cols:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_def}")


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
                    verdict TEXT DEFAULT 'RECORDED'
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
                CREATE INDEX IF NOT EXISTS idx_samples_ts ON telemetry_samples(ts);

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

                CREATE TABLE IF NOT EXISTS custom_profiles (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    short_name TEXT NOT NULL,
                    category TEXT NOT NULL DEFAULT 'Custom Enterprise Mix',
                    description TEXT,
                    avg_frame_size INTEGER NOT NULL DEFAULT 512,
                    default_rate_pct REAL NOT NULL DEFAULT 25.0,
                    target_gbps REAL NOT NULL DEFAULT 2.5,
                    default_users INTEGER NOT NULL DEFAULT 1000,
                    default_devices INTEGER NOT NULL DEFAULT 2500,
                    tcp_pct INTEGER NOT NULL DEFAULT 80,
                    udp_pct INTEGER NOT NULL DEFAULT 20,
                    dscp INTEGER NOT NULL DEFAULT 0,
                    vlan_id INTEGER NOT NULL DEFAULT 0,
                    traffic_engine TEXT NOT NULL DEFAULT 'trex_stl',
                    protocol_mix_json TEXT NOT NULL,
                    streams_json TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS unifi_samples (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts REAL NOT NULL,
                    run_id INTEGER,
                    controller_host TEXT,
                    site_name TEXT,
                    gw_name TEXT,
                    gw_model TEXT,
                    gw_online INTEGER,
                    gw_cpu_pct REAL,
                    gw_mem_pct REAL,
                    wan_rx_bps REAL,
                    wan_tx_bps REAL,
                    wan_latency_ms REAL,
                    active_sessions INTEGER,
                    switches_online INTEGER,
                    switches_total INTEGER,
                    aps_online INTEGER,
                    aps_total INTEGER,
                    active_clients INTEGER,
                    summary_json TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_unifi_samples_ts ON unifi_samples(ts);
                CREATE INDEX IF NOT EXISTS idx_unifi_samples_run ON unifi_samples(run_id);

                CREATE TABLE IF NOT EXISTS snmp_samples (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts REAL NOT NULL,
                    run_id INTEGER,
                    host TEXT NOT NULL,
                    if_index INTEGER NOT NULL,
                    if_name TEXT,
                    oper_status TEXT,
                    speed_mbps INTEGER,
                    in_bps REAL,
                    out_bps REAL,
                    in_pps REAL,
                    out_pps REAL,
                    in_errors INTEGER,
                    out_errors INTEGER,
                    in_discards INTEGER,
                    out_discards INTEGER
                );

                CREATE INDEX IF NOT EXISTS idx_snmp_samples_ts ON snmp_samples(ts);
                CREATE INDEX IF NOT EXISTS idx_snmp_samples_run ON snmp_samples(run_id);

                CREATE TABLE IF NOT EXISTS audit_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts REAL NOT NULL,
                    actor TEXT NOT NULL,
                    category TEXT NOT NULL,
                    action TEXT NOT NULL,
                    target TEXT,
                    details TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_audit_ts ON audit_logs(ts DESC);

                CREATE TABLE IF NOT EXISTS user_accounts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    display_name TEXT NOT NULL,
                    role TEXT NOT NULL DEFAULT 'Lab Administrator',
                    email TEXT,
                    active INTEGER NOT NULL DEFAULT 1,
                    created_at REAL NOT NULL
                );
                """
            )

            # Additive non-destructive migrations on existing tables
            _ensure_column(conn, "test_runs", "traffic_engine", "TEXT DEFAULT 'trex_stl'")
            _ensure_column(conn, "test_runs", "thresholds_json", "TEXT")
            _ensure_column(conn, "test_runs", "operator_name", "TEXT DEFAULT 'Stephan Van Vuuren'")
            _ensure_column(conn, "test_runs", "client_name", "TEXT DEFAULT ''")
            _ensure_column(conn, "test_runs", "dut_name", "TEXT DEFAULT 'UniFi Enterprise Fortress Gateway'")

            _ensure_column(conn, "telemetry_samples", "p95_lat_us", "REAL DEFAULT 0.0")
            _ensure_column(conn, "telemetry_samples", "p99_lat_us", "REAL DEFAULT 0.0")
            _ensure_column(conn, "telemetry_samples", "active_flows", "INTEGER DEFAULT 0")
            _ensure_column(conn, "telemetry_samples", "established_sessions", "INTEGER DEFAULT 0")
            _ensure_column(conn, "telemetry_samples", "emulated_clients", "INTEGER DEFAULT 0")
            _ensure_column(conn, "telemetry_samples", "tcp_connects", "INTEGER DEFAULT 0")
            _ensure_column(conn, "telemetry_samples", "tcp_closed", "INTEGER DEFAULT 0")
            _ensure_column(conn, "telemetry_samples", "tcp_drops", "INTEGER DEFAULT 0")
            _ensure_column(conn, "telemetry_samples", "tcp_retransmits", "INTEGER DEFAULT 0")
            _ensure_column(conn, "telemetry_samples", "phase_name", "TEXT DEFAULT 'steady'")
            _ensure_column(conn, "telemetry_samples", "cps", "REAL DEFAULT 0.0")
            _ensure_column(conn, "telemetry_samples", "target_bps", "REAL DEFAULT 0.0")
            _ensure_column(conn, "telemetry_samples", "telemetry_source", "TEXT DEFAULT 'Cisco TRex ASTF'")
            _ensure_column(conn, "telemetry_samples", "unifi_gw_cpu", "REAL")
            _ensure_column(conn, "telemetry_samples", "unifi_gw_mem", "REAL")
            _ensure_column(conn, "telemetry_samples", "unifi_wan_rx_bps", "REAL")
            _ensure_column(conn, "telemetry_samples", "unifi_wan_tx_bps", "REAL")
            _ensure_column(conn, "telemetry_samples", "snmp_in_bps", "REAL")
            _ensure_column(conn, "telemetry_samples", "snmp_out_bps", "REAL")

            # Seed default operator account if empty
            cnt = conn.execute("SELECT COUNT(*) FROM user_accounts").fetchone()[0]
            if cnt == 0:
                conn.execute(
                    """
                    INSERT INTO user_accounts (username, display_name, role, email, active, created_at)
                    VALUES ('stephan.vanvuuren', 'Stephan Van Vuuren', 'Lab Administrator', 'stephan@lab.local', 1, ?)
                    """,
                    (time.time(),),
                )

            # Clean up any orphaned 'running' runs from prior service restarts
            conn.execute(
                "UPDATE test_runs SET status = 'interrupted', verdict = 'INTERRUPTED', ended_at = ? WHERE status = 'running' AND ended_at IS NULL",
                (time.time(),),
            )
            conn.commit()
        finally:
            conn.close()


def log_audit(
    category: str,
    action: str,
    target: str = "",
    details: str = "",
    actor: str = "Stephan Van Vuuren",
) -> None:
    with _lock:
        conn = get_conn()
        try:
            conn.execute(
                """
                INSERT INTO audit_logs (ts, actor, category, action, target, details)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (time.time(), actor, category, action, target, details[:1000]),
            )
            conn.commit()
        except Exception:
            pass
        finally:
            conn.close()


def list_audit_logs(limit: int = 200) -> List[Dict[str, Any]]:
    with _lock:
        conn = get_conn()
        try:
            rows = conn.execute(
                "SELECT * FROM audit_logs ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
            return [dict(r) for r in rows]
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
    traffic_engine: str = "trex_stl",
    thresholds: Optional[Dict[str, Any]] = None,
    operator_name: str = "Stephan Van Vuuren",
    client_name: str = "",
    dut_name: str = "UniFi Enterprise Fortress Gateway",
) -> int:
    with _lock:
        conn = get_conn()
        try:
            cur = conn.execute(
                """
                INSERT INTO test_runs (
                    name, profile_id, profile_name, test_mode, status,
                    started_at, duration_sec, target_rate_pct,
                    simulated_users, simulated_devices, config_json,
                    traffic_engine, thresholds_json, operator_name, client_name, dut_name, verdict
                ) VALUES (?, ?, ?, ?, 'running', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'RUNNING')
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
                    traffic_engine,
                    json.dumps(thresholds) if thresholds else None,
                    operator_name,
                    client_name,
                    dut_name,
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
                    cpu_pct, ram_pct,
                    p95_lat_us, p99_lat_us, active_flows, established_sessions, emulated_clients,
                    tcp_connects, tcp_closed, tcp_drops, tcp_retransmits, phase_name,
                    cps, target_bps, telemetry_source,
                    unifi_gw_cpu, unifi_gw_mem, unifi_wan_rx_bps, unifi_wan_tx_bps,
                    snmp_in_bps, snmp_out_bps
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    float(sample.get("ts", time.time())),
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
                    float(sample.get("lat_min_us", 0.0) or 0.0),
                    float(sample.get("lat_avg_us", 0.0) or 0.0),
                    float(sample.get("lat_max_us", 0.0) or 0.0),
                    float(sample.get("jitter_us", 0.0) or 0.0),
                    float(sample.get("mos_score", 0.0) or 0.0),
                    float(sample.get("cpu_pct", 0.0)),
                    float(sample.get("ram_pct", 0.0)),
                    float(sample.get("p95_lat_us", 0.0) or 0.0),
                    float(sample.get("p99_lat_us", 0.0) or 0.0),
                    int(sample.get("active_flows", 0) or 0),
                    int(sample.get("established_sessions", 0) or 0),
                    int(sample.get("emulated_clients", 0) or 0),
                    int(sample.get("tcp_connects", 0) or 0),
                    int(sample.get("tcp_closed", 0) or 0),
                    int(sample.get("tcp_drops", 0) or 0),
                    int(sample.get("tcp_retransmits", 0) or 0),
                    str(sample.get("phase_name", "steady")),
                    float(sample.get("cps", 0.0) or 0.0),
                    float(sample.get("target_bps", 0.0) or 0.0),
                    str(sample.get("telemetry_source", "Cisco TRex ASTF")),
                    sample.get("unifi_gw_cpu"),
                    sample.get("unifi_gw_mem"),
                    sample.get("unifi_wan_rx_bps"),
                    sample.get("unifi_wan_tx_bps"),
                    sample.get("snmp_in_bps"),
                    sample.get("snmp_out_bps"),
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

            thresholds_raw = row["thresholds_json"]
            thresholds = json.loads(thresholds_raw) if thresholds_raw else None

            if samples:
                max_tx_bps = max(float(s["tx_bps"]) for s in samples)
                avg_tx_bps = sum(float(s["tx_bps"]) for s in samples) / len(samples)
                max_rx_bps = max(float(s["rx_bps"]) for s in samples)
                avg_rx_bps = sum(float(s["rx_bps"]) for s in samples) / len(samples)
                max_tx_pps = max(float(s["tx_pps"]) for s in samples)
                avg_tx_pps = sum(float(s["tx_pps"]) for s in samples) / len(samples)
                total_tx_pkts = int(samples[-1]["tx_packets"])
                total_rx_pkts = int(samples[-1]["rx_packets"])
                total_drops = int(samples[-1]["dropped_packets"])
                overall_drop_pct = float(samples[-1]["drop_pct"])
                lat_vals = [float(s["lat_avg_us"]) for s in samples if float(s["lat_avg_us"] or 0) > 0]
                min_vals = [float(s["lat_min_us"]) for s in samples if float(s["lat_min_us"] or 0) > 0]
                max_vals = [float(s["lat_max_us"]) for s in samples if float(s["lat_max_us"] or 0) > 0]
                p95_vals = [float(s["p95_lat_us"] or 0) for s in samples if float(s["p95_lat_us"] or 0) > 0]
                p99_vals = [float(s["p99_lat_us"] or 0) for s in samples if float(s["p99_lat_us"] or 0) > 0]
                jit_vals = [float(s["jitter_us"]) for s in samples if float(s["jitter_us"] or 0) > 0]
                mos_vals = [float(s["mos_score"]) for s in samples if float(s["mos_score"] or 0) > 0]

                min_lat = min(min_vals) if min_vals else 0.0
                avg_lat = (sum(lat_vals) / len(lat_vals)) if lat_vals else 0.0
                max_lat = max(max_vals) if max_vals else 0.0
                p95_lat = (sum(p95_vals) / len(p95_vals)) if p95_vals else 0.0
                p99_lat = max(p99_vals) if p99_vals else 0.0
                avg_jitter = (sum(jit_vals) / len(jit_vals)) if jit_vals else 0.0
                avg_mos = (sum(mos_vals) / len(mos_vals)) if mos_vals else 0.0
                peak_flows = max(int(s["active_flows"] or 0) for s in samples)
                peak_est_sessions = max(int(s["established_sessions"] or 0) for s in samples)
                emulated_clients = max(int(s["emulated_clients"] or 0) for s in samples)
                cps_vals = [float(s["cps"] or 0) for s in samples]
                peak_cps = max(cps_vals) if cps_vals else 0.0
                avg_cps = (sum(cps_vals) / len(cps_vals)) if cps_vals else 0.0
                total_tcp_connects = max(int(s["tcp_connects"] or 0) for s in samples)
                total_tcp_drops = max(int(s["tcp_drops"] or 0) for s in samples)
                total_tcp_retransmits = max(int(s["tcp_retransmits"] or 0) for s in samples)
                gw_cpu_vals = [float(s["unifi_gw_cpu"]) for s in samples if s["unifi_gw_cpu"] is not None]
                gw_mem_vals = [float(s["unifi_gw_mem"]) for s in samples if s["unifi_gw_mem"] is not None]
                peak_gw_cpu = max(gw_cpu_vals) if gw_cpu_vals else None
                peak_gw_mem = max(gw_mem_vals) if gw_mem_vals else None
                telemetry_source = samples[-1]["telemetry_source"] or "Cisco TRex ASTF"
            else:
                max_tx_bps = avg_tx_bps = max_rx_bps = avg_rx_bps = 0.0
                max_tx_pps = avg_tx_pps = 0.0
                total_tx_pkts = total_rx_pkts = total_drops = 0
                overall_drop_pct = 0.0
                min_lat = avg_lat = max_lat = p95_lat = p99_lat = avg_jitter = avg_mos = 0.0
                peak_flows = peak_est_sessions = emulated_clients = 0
                peak_cps = avg_cps = 0.0
                total_tcp_connects = total_tcp_drops = total_tcp_retransmits = 0
                peak_gw_cpu = peak_gw_mem = None
                telemetry_source = "No samples recorded"

            # Strict threshold evaluation: Pass/Fail ONLY when explicit thresholds were configured
            threshold_checks = []
            thresholds_enabled = bool(isinstance(thresholds, dict) and thresholds.get("enabled"))
            if thresholds_enabled:
                def _thr(key: str) -> Optional[float]:
                    # Tolerate "" / non-numeric values from the UI instead of crashing finalize (run would stay 'running')
                    try:
                        v = thresholds.get(key)
                        return None if v is None or v == "" else float(v)
                    except (TypeError, ValueError):
                        return None

                def _check(metric: str, requirement: str, actual: str, ok: Optional[bool]) -> None:
                    # ok=None => threshold configured but the metric was not measured: never counts as PASS
                    threshold_checks.append({
                        "metric": metric,
                        "requirement": requirement,
                        "actual": actual if ok is not None else "Not measured",
                        "outcome": "NOT MEASURED" if ok is None else ("PASS" if ok else "FAIL"),
                    })

                req_mbps = _thr("min_rx_mbps")
                if req_mbps is not None:
                    actual_mbps = avg_rx_bps / 1e6
                    _check("Average RX Throughput", f">= {req_mbps:.2f} Mbps", f"{actual_mbps:.2f} Mbps",
                           (actual_mbps >= req_mbps) if samples else None)
                req_loss = _thr("max_loss_pct")
                if req_loss is not None:
                    _check("Packet Loss", f"<= {req_loss:.4f}%", f"{overall_drop_pct:.4f}%",
                           (overall_drop_pct <= req_loss) if total_tx_pkts > 0 else None)
                req_lat = _thr("max_avg_latency_us")
                if req_lat is not None:
                    _check("Average Latency", f"<= {req_lat:.1f} us", f"{avg_lat:.1f} us",
                           (avg_lat <= req_lat) if avg_lat > 0 else None)
                req_p99 = _thr("max_p99_latency_us")
                if req_p99 is not None:
                    _check("P99 Tail Latency", f"<= {req_p99:.1f} us", f"{p99_lat:.1f} us",
                           (p99_lat <= req_p99) if p99_lat > 0 else None)
                req_cpu = _thr("max_gw_cpu_pct")
                if req_cpu is not None:
                    _check("UniFi Gateway Peak CPU", f"<= {req_cpu:.1f}%",
                           f"{peak_gw_cpu:.1f}%" if peak_gw_cpu is not None else "",
                           (peak_gw_cpu <= req_cpu) if peak_gw_cpu is not None else None)
                outcomes = [c["outcome"] for c in threshold_checks]
                if not outcomes:
                    verdict = "COMPLETED"  # enabled but no usable threshold values: nothing was evaluated
                elif "FAIL" in outcomes:
                    verdict = "FAIL"
                elif "NOT MEASURED" in outcomes:
                    verdict = "INCONCLUSIVE"
                else:
                    verdict = "PASS"
            else:
                verdict = "COMPLETED"

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
                "p95_lat_us": round(p95_lat, 2),
                "p99_lat_us": round(p99_lat, 2),
                "jitter_avg_us": round(avg_jitter, 2),
                "mos_avg": round(avg_mos, 2),
                "peak_active_flows": peak_flows,
                "peak_established_sessions": peak_est_sessions,
                "emulated_client_ips": emulated_clients,
                "peak_cps": round(peak_cps, 2),
                "avg_cps": round(avg_cps, 2),
                "total_tcp_connects": total_tcp_connects,
                "total_tcp_drops": total_tcp_drops,
                "total_tcp_retransmits": total_tcp_retransmits,
                "peak_gw_cpu_pct": round(peak_gw_cpu, 1) if peak_gw_cpu is not None else None,
                "peak_gw_mem_pct": round(peak_gw_mem, 1) if peak_gw_mem is not None else None,
                "telemetry_source": telemetry_source,
                "thresholds_configured": bool(threshold_checks),
                "threshold_checks": threshold_checks,
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


def list_test_runs(limit: int = 100) -> List[Dict[str, Any]]:
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
                t_raw = d.pop("thresholds_json", None)
                d["thresholds"] = json.loads(t_raw) if t_raw else None
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
            t_raw = d.pop("thresholds_json", None)
            d["thresholds"] = json.loads(t_raw) if t_raw else None
            if include_samples:
                s_rows = conn.execute(
                    "SELECT * FROM telemetry_samples WHERE run_id = ? ORDER BY elapsed_sec ASC",
                    (run_id,),
                ).fetchall()
                d["samples"] = [dict(s) for s in s_rows]

                # Also fetch correlated UniFi & SNMP samples within the run window
                t_start = float(d["started_at"] or 0) - 5.0
                t_end = float(d["ended_at"] or time.time()) + 5.0
                u_rows = conn.execute(
                    "SELECT * FROM unifi_samples WHERE (run_id = ? OR (ts >= ? AND ts <= ?)) ORDER BY ts ASC",
                    (run_id, t_start, t_end),
                ).fetchall()
                unifi_list = []
                for ur in u_rows:
                    ud = dict(ur)
                    ud["summary"] = json.loads(ud.pop("summary_json") or "{}")
                    unifi_list.append(ud)
                d["unifi_samples"] = unifi_list

                sn_rows = conn.execute(
                    "SELECT * FROM snmp_samples WHERE (run_id = ? OR (ts >= ? AND ts <= ?)) ORDER BY ts ASC",
                    (run_id, t_start, t_end),
                ).fetchall()
                d["snmp_samples"] = [dict(sr) for sr in sn_rows]
            return d
        finally:
            conn.close()


def delete_test_run(run_id: int) -> bool:
    with _lock:
        conn = get_conn()
        try:
            conn.execute("DELETE FROM telemetry_samples WHERE run_id = ?", (run_id,))
            # Run-tagged UniFi/SNMP samples are exempt from the 7-day prune, so they would otherwise leak forever
            conn.execute("DELETE FROM unifi_samples WHERE run_id = ?", (run_id,))
            conn.execute("DELETE FROM snmp_samples WHERE run_id = ?", (run_id,))
            cur = conn.execute("DELETE FROM test_runs WHERE id = ?", (run_id,))
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()


def compare_test_runs(run_a_id: int, run_b_id: int) -> Optional[Dict[str, Any]]:
    run_a = get_test_run(run_a_id, include_samples=True)
    run_b = get_test_run(run_b_id, include_samples=True)
    if not run_a or not run_b:
        return None
    sa = run_a.get("summary") or {}
    sb = run_b.get("summary") or {}

    def _delta(va: Any, vb: Any) -> Dict[str, Any]:
        fa = float(va or 0.0)
        fb = float(vb or 0.0)
        diff = fb - fa
        pct = ((diff / fa) * 100.0) if abs(fa) > 1e-9 else None
        return {"run_a": round(fa, 4), "run_b": round(fb, 4), "delta": round(diff, 4), "delta_pct": round(pct, 2) if pct is not None else None}

    return {
        "run_a": run_a,
        "run_b": run_b,
        "deltas": {
            "avg_tx_mbps": _delta((sa.get("avg_tx_bps") or 0) / 1e6, (sb.get("avg_tx_bps") or 0) / 1e6),
            "avg_rx_mbps": _delta((sa.get("avg_rx_bps") or 0) / 1e6, (sb.get("avg_rx_bps") or 0) / 1e6),
            "max_rx_mbps": _delta((sa.get("max_rx_bps") or 0) / 1e6, (sb.get("max_rx_bps") or 0) / 1e6),
            "avg_tx_pps": _delta(sa.get("avg_tx_pps"), sb.get("avg_tx_pps")),
            "drop_pct": _delta(sa.get("drop_pct"), sb.get("drop_pct")),
            "lat_avg_us": _delta(sa.get("lat_avg_us"), sb.get("lat_avg_us")),
            "p99_lat_us": _delta(sa.get("p99_lat_us"), sb.get("p99_lat_us")),
            "jitter_avg_us": _delta(sa.get("jitter_avg_us"), sb.get("jitter_avg_us")),
            "peak_active_flows": _delta(sa.get("peak_active_flows"), sb.get("peak_active_flows")),
            "peak_established_sessions": _delta(sa.get("peak_established_sessions"), sb.get("peak_established_sessions")),
            "peak_cps": _delta(sa.get("peak_cps"), sb.get("peak_cps")),
            "peak_gw_cpu_pct": _delta(sa.get("peak_gw_cpu_pct"), sb.get("peak_gw_cpu_pct")),
        },
    }


# Custom Profiles CRUD
def save_custom_profile(prof: Dict[str, Any]) -> Dict[str, Any]:
    now = time.time()
    pid = prof.get("id") or f"custom_{int(now)}"
    with _lock:
        conn = get_conn()
        try:
            conn.execute(
                """
                INSERT INTO custom_profiles (
                    id, name, short_name, category, description,
                    avg_frame_size, default_rate_pct, target_gbps,
                    default_users, default_devices, tcp_pct, udp_pct,
                    dscp, vlan_id, traffic_engine,
                    protocol_mix_json, streams_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name=excluded.name,
                    short_name=excluded.short_name,
                    category=excluded.category,
                    description=excluded.description,
                    avg_frame_size=excluded.avg_frame_size,
                    default_rate_pct=excluded.default_rate_pct,
                    target_gbps=excluded.target_gbps,
                    default_users=excluded.default_users,
                    default_devices=excluded.default_devices,
                    tcp_pct=excluded.tcp_pct,
                    udp_pct=excluded.udp_pct,
                    dscp=excluded.dscp,
                    vlan_id=excluded.vlan_id,
                    traffic_engine=excluded.traffic_engine,
                    protocol_mix_json=excluded.protocol_mix_json,
                    streams_json=excluded.streams_json,
                    updated_at=excluded.updated_at
                """,
                (
                    pid,
                    prof.get("name", "Custom Enterprise Mix"),
                    prof.get("short_name", prof.get("name", "Custom Mix")[:22]),
                    prof.get("category", "Saved Custom Mix"),
                    prof.get("description", "User-defined synthetic enterprise workload profile."),
                    int(prof.get("avg_frame_size", 512)),
                    float(prof.get("default_rate_pct", 25.0)),
                    float(prof.get("target_gbps", 2.5)),
                    int(prof.get("default_users", 1000)),
                    int(prof.get("default_devices", 2500)),
                    int(prof.get("tcp_pct", 80)),
                    int(prof.get("udp_pct", 20)),
                    int(prof.get("dscp", 0)),
                    int(prof.get("vlan_id", 0)),
                    prof.get("traffic_engine", "trex_stl"),
                    json.dumps(prof.get("protocol_mix", {})),
                    json.dumps(prof.get("streams", [])),
                    now,
                    now,
                ),
            )
            conn.commit()
        finally:
            conn.close()
    prof["id"] = pid
    return prof


def list_custom_profiles() -> List[Dict[str, Any]]:
    with _lock:
        conn = get_conn()
        try:
            rows = conn.execute("SELECT * FROM custom_profiles ORDER BY updated_at DESC").fetchall()
            out = []
            for r in rows:
                d = dict(r)
                d["protocol_mix"] = json.loads(d.pop("protocol_mix_json") or "{}")
                d["streams"] = json.loads(d.pop("streams_json") or "[]")
                d["is_custom_saved"] = True
                out.append(d)
            return out
        finally:
            conn.close()


def delete_custom_profile(profile_id: str) -> bool:
    with _lock:
        conn = get_conn()
        try:
            cur = conn.execute("DELETE FROM custom_profiles WHERE id = ?", (profile_id,))
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()


# UniFi & SNMP Sample Persistence
def insert_unifi_sample(sample: Dict[str, Any], run_id: Optional[int] = None) -> None:
    with _lock:
        conn = get_conn()
        try:
            conn.execute(
                """
                INSERT INTO unifi_samples (
                    ts, run_id, controller_host, site_name, gw_name, gw_model,
                    gw_online, gw_cpu_pct, gw_mem_pct, wan_rx_bps, wan_tx_bps,
                    wan_latency_ms, active_sessions, switches_online, switches_total,
                    aps_online, aps_total, active_clients, summary_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    float(sample.get("ts", time.time())),
                    run_id,
                    sample.get("controller_host", ""),
                    sample.get("site_name", ""),
                    sample.get("gw_name", ""),
                    sample.get("gw_model", ""),
                    1 if sample.get("gw_online") else 0,
                    sample.get("gw_cpu_pct"),
                    sample.get("gw_mem_pct"),
                    sample.get("wan_rx_bps"),
                    sample.get("wan_tx_bps"),
                    sample.get("wan_latency_ms"),
                    sample.get("active_sessions"),
                    sample.get("switches_online"),
                    sample.get("switches_total"),
                    sample.get("aps_online"),
                    sample.get("aps_total"),
                    sample.get("active_clients"),
                    json.dumps(sample.get("summary", {})),
                ),
            )
            # Prune samples older than 7 days not tied to a test run
            cutoff = time.time() - 7 * 86400
            conn.execute("DELETE FROM unifi_samples WHERE run_id IS NULL AND ts < ?", (cutoff,))
            conn.commit()
        finally:
            conn.close()


def insert_snmp_samples(samples: List[Dict[str, Any]], run_id: Optional[int] = None) -> None:
    if not samples:
        return
    with _lock:
        conn = get_conn()
        try:
            now = time.time()
            for s in samples:
                conn.execute(
                    """
                    INSERT INTO snmp_samples (
                        ts, run_id, host, if_index, if_name, oper_status, speed_mbps,
                        in_bps, out_bps, in_pps, out_pps,
                        in_errors, out_errors, in_discards, out_discards
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        float(s.get("ts", now)),
                        run_id,
                        s.get("host", ""),
                        int(s.get("if_index", 0)),
                        s.get("if_name", ""),
                        s.get("oper_status", ""),
                        s.get("speed_mbps"),
                        s.get("in_bps"),
                        s.get("out_bps"),
                        s.get("in_pps"),
                        s.get("out_pps"),
                        s.get("in_errors"),
                        s.get("out_errors"),
                        s.get("in_discards"),
                        s.get("out_discards"),
                    ),
                )
            cutoff = now - 7 * 86400
            conn.execute("DELETE FROM snmp_samples WHERE run_id IS NULL AND ts < ?", (cutoff,))
            conn.commit()
        finally:
            conn.close()


# Scheduled Jobs
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
                    job.get("name", "Scheduled Network Benchmark"),
                    job.get("cron_expr", "0 2 * * *"),
                    job.get("run_at_iso", ""),
                    job.get("profile_id", "imix"),
                    job.get("test_mode", "timed"),
                    int(job.get("duration_sec", 60)),
                    float(job.get("rate_pct", 50.0)),
                    int(job.get("simulated_users", 1000)),
                    int(job.get("simulated_devices", 2500)),
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


# User Access Accounts
def list_users() -> List[Dict[str, Any]]:
    with _lock:
        conn = get_conn()
        try:
            rows = conn.execute("SELECT * FROM user_accounts ORDER BY id ASC").fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()


def add_user_account(user: Dict[str, Any]) -> int:
    with _lock:
        conn = get_conn()
        try:
            cur = conn.execute(
                """
                INSERT INTO user_accounts (username, display_name, role, email, active, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    user.get("username", "").strip(),
                    user.get("display_name", "").strip(),
                    user.get("role", "Operator"),
                    user.get("email", "").strip(),
                    1 if user.get("active", True) else 0,
                    time.time(),
                ),
            )
            conn.commit()
            return int(cur.lastrowid)
        finally:
            conn.close()


def delete_user_account(user_id: int) -> bool:
    with _lock:
        conn = get_conn()
        try:
            cur = conn.execute("DELETE FROM user_accounts WHERE id = ? AND id != 1", (user_id,))
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()


# Appliance Settings & Encrypted Secrets
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
