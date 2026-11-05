"""
Optional Read-Only SNMPv2c / SNMPv3 Interface Telemetry Collector (IF-MIB)
for Cisco TRex Network Test Studio.

Features:
  - Supports SNMPv2c and SNMPv3 (noAuthNoPriv, authNoPriv, authPriv with SHA/SHA-256 + AES).
  - Encrypts community strings and SNMPv3 passphrases server-side at rest (never exposed to UI).
  - Polls 64-bit high-capacity IF-MIB counters (ifHCInOctets, ifHCOutOctets, ifHCInUcastPkts, ifHCOutUcastPkts)
    with fallback to 32-bit counters when 64-bit counters are unsupported.
  - Correctly handles sysUpTime device reboots/counter resets and 32-bit / 64-bit counter wraparound.
"""
import re
import subprocess
import threading
import time
from typing import Any, Dict, List, Optional

import database as db

COUNTER64_MAX = 1 << 64
COUNTER32_MAX = 1 << 32


class SNMPTelemetryCollector:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._prev_state: Dict[str, Dict[str, Any]] = {}
        self._last_poll_ts: float = 0.0
        self.latest_snapshot: Dict[str, Any] = {
            "configured": False,
            "connected": False,
            "status": "Disabled",
            "last_polled_at": None,
            "last_error": None,
            "sys_name": None,
            "sys_descr": None,
            "uptime_ticks": None,
            "interfaces": [],
        }

    def get_config_public(self) -> Dict[str, Any]:
        raw = db.get_setting("snmp_config", {}) or {}
        return {
            "enabled": bool(raw.get("enabled", False)),
            "host": raw.get("host", "10.20.30.1"),
            "port": int(raw.get("port", 161)),
            "version": raw.get("version", "v3"),  # v2c | v3
            "security_level": raw.get("security_level", "authPriv"),  # noAuthNoPriv | authNoPriv | authPriv
            "username": raw.get("username", ""),
            "auth_protocol": raw.get("auth_protocol", "SHA"),  # MD5 | SHA | SHA-256
            "priv_protocol": raw.get("priv_protocol", "AES"),  # DES | AES
            "poll_interval_sec": int(raw.get("poll_interval_sec", 5)),
            "has_community": bool(raw.get("community_enc")),
            "has_auth_pass": bool(raw.get("auth_pass_enc")),
            "has_priv_pass": bool(raw.get("priv_pass_enc")),
        }

    def save_config(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        existing = db.get_setting("snmp_config", {}) or {}
        updated = {
            "enabled": bool(payload.get("enabled", existing.get("enabled", False))),
            "host": str(payload.get("host", existing.get("host", "10.20.30.1"))).strip(),
            "port": int(payload.get("port", existing.get("port", 161)) or 161),
            "version": str(payload.get("version", existing.get("version", "v3"))),
            "security_level": str(payload.get("security_level", existing.get("security_level", "authPriv"))),
            "username": str(payload.get("username", existing.get("username", ""))).strip(),
            "auth_protocol": str(payload.get("auth_protocol", existing.get("auth_protocol", "SHA"))),
            "priv_protocol": str(payload.get("priv_protocol", existing.get("priv_protocol", "AES"))),
            "poll_interval_sec": max(5, min(120, int(payload.get("poll_interval_sec", existing.get("poll_interval_sec", 5)) or 5))),
            "community_enc": existing.get("community_enc", ""),
            "auth_pass_enc": existing.get("auth_pass_enc", ""),
            "priv_pass_enc": existing.get("priv_pass_enc", ""),
        }
        if payload.get("community") and not str(payload["community"]).startswith("••"):
            updated["community_enc"] = db.encrypt_secret(str(payload["community"]).strip())
        if payload.get("auth_pass") and not str(payload["auth_pass"]).startswith("••"):
            updated["auth_pass_enc"] = db.encrypt_secret(str(payload["auth_pass"]))
        if payload.get("priv_pass") and not str(payload["priv_pass"]).startswith("••"):
            updated["priv_pass_enc"] = db.encrypt_secret(str(payload["priv_pass"]))

        self._prev_state.clear()
        db.set_setting("snmp_config", updated)
        db.log_audit("SNMP Integration", "Updated SNMP Monitoring Settings", updated["host"], f"Version: {updated['version']}, Enabled: {updated['enabled']}")
        return self.get_config_public()

    def _build_snmp_args(self, cfg: Dict[str, Any]) -> List[str]:
        target = f"{cfg.get('host', '10.20.30.1')}:{int(cfg.get('port', 161))}"
        ver = cfg.get("version", "v3")
        if ver == "v2c":
            comm = db.decrypt_secret(cfg.get("community_enc", "")) or "public"
            return ["-v2c", "-c", comm, "-t", "2", "-r", "1", "-Onq", target]
        # SNMPv3
        sec = cfg.get("security_level", "authPriv")
        user = cfg.get("username", "snmpuser")
        args = ["-v3", "-l", sec, "-u", user, "-t", "2", "-r", "1", "-Onq"]
        if sec in ("authNoPriv", "authPriv"):
            ap = cfg.get("auth_protocol", "SHA")
            apass = db.decrypt_secret(cfg.get("auth_pass_enc", ""))
            args.extend(["-a", ap, "-A", apass])
        if sec == "authPriv":
            pp = cfg.get("priv_protocol", "AES")
            ppass = db.decrypt_secret(cfg.get("priv_pass_enc", ""))
            args.extend(["-x", pp, "-X", ppass])
        args.append(target)
        return args

    @staticmethod
    def _counter_delta(curr: Optional[int], prev: Optional[int], is_64bit: bool) -> Optional[int]:
        if curr is None or prev is None:
            return None
        if curr >= prev:
            return curr - prev
        # Wraparound handling
        mod = COUNTER64_MAX if is_64bit else COUNTER32_MAX
        wrapped = (mod - prev) + curr
        # Sanity check: reject implausible giant jumps caused by silent counter resets
        if is_64bit and wrapped > (100_000_000_000 * 120):  # > 100 GB/s * 120s
            return None
        return wrapped

    def poll_once(self, active_run_id: Optional[int] = None, force: bool = False) -> Dict[str, Any]:
        cfg = db.get_setting("snmp_config", {}) or {}
        if not cfg or (not cfg.get("enabled") and not force):
            self.latest_snapshot["configured"] = bool(cfg.get("community_enc") or cfg.get("username"))
            return self.latest_snapshot

        now = time.time()
        interval = max(5, int(cfg.get("poll_interval_sec", 5)))
        if not force and (now - self._last_poll_ts) < interval:
            return self.latest_snapshot
        self._last_poll_ts = now

        host = cfg.get("host", "10.20.30.1")
        try:
            base_args = self._build_snmp_args(cfg)
            # 1. Fetch sysUpTime (.1.3.6.1.2.1.1.3.0) & sysName (.1.3.6.1.2.1.1.5.0) & sysDescr (.1.3.6.1.2.1.1.1.0)
            res_sys = subprocess.run(
                ["snmpget", *base_args, ".1.3.6.1.2.1.1.1.0", ".1.3.6.1.2.1.1.3.0", ".1.3.6.1.2.1.1.5.0"],
                capture_output=True,
                text=True,
                timeout=4,
            )
            if res_sys.returncode != 0:
                raise RuntimeError((res_sys.stderr or res_sys.stdout or "SNMP timeout / authentication error").strip())

            sys_descr = sys_name = None
            uptime_ticks = None
            for line in res_sys.stdout.splitlines():
                parts = line.strip().split(" ", 1)
                if len(parts) < 2:
                    continue
                oid, val = parts[0], parts[1].strip().strip('"')
                if oid.endswith(".1.1.0"):
                    sys_descr = val
                elif oid.endswith(".1.3.0"):
                    m = re.search(r"(\d+)", val)
                    if m:
                        uptime_ticks = int(m.group(1))
                elif oid.endswith(".1.5.0"):
                    sys_name = val

            # 2. Walk IF-MIB interface table + ifXTable (64-bit counters)
            oids_to_walk = [
                (".1.3.6.1.2.1.31.1.1.1.1", "ifName"),
                (".1.3.6.1.2.1.2.2.1.2", "ifDescr"),
                (".1.3.6.1.2.1.2.2.1.8", "ifOperStatus"),
                (".1.3.6.1.2.1.31.1.1.1.15", "ifHighSpeed"),
                (".1.3.6.1.2.1.31.1.1.1.6", "ifHCInOctets"),
                (".1.3.6.1.2.1.31.1.1.1.10", "ifHCOutOctets"),
                (".1.3.6.1.2.1.31.1.1.1.7", "ifHCInUcastPkts"),
                (".1.3.6.1.2.1.31.1.1.1.11", "ifHCOutUcastPkts"),
                (".1.3.6.1.2.1.2.2.1.10", "ifInOctets"),
                (".1.3.6.1.2.1.2.2.1.16", "ifOutOctets"),
                (".1.3.6.1.2.1.2.2.1.14", "ifInErrors"),
                (".1.3.6.1.2.1.2.2.1.20", "ifOutErrors"),
                (".1.3.6.1.2.1.2.2.1.13", "ifInDiscards"),
                (".1.3.6.1.2.1.2.2.1.19", "ifOutDiscards"),
            ]
            if_map: Dict[int, Dict[str, Any]] = {}
            for base_oid, field_name in oids_to_walk:
                w = subprocess.run(["snmpwalk", *base_args, base_oid], capture_output=True, text=True, timeout=5)
                if w.returncode != 0:
                    continue
                for line in w.stdout.splitlines():
                    if "No Such" in line or not line.strip():
                        continue
                    p = line.strip().split(" ", 1)
                    if len(p) != 2:
                        continue
                    oid_str, raw_val = p[0], p[1].strip().strip('"')
                    if not oid_str.startswith(base_oid + "."):
                        continue
                    try:
                        if_idx = int(oid_str.rsplit(".", 1)[1])
                    except Exception:
                        continue
                    entry = if_map.setdefault(if_idx, {"if_index": if_idx})
                    if field_name in ("ifName", "ifDescr"):
                        entry[field_name] = raw_val
                    elif field_name == "ifOperStatus":
                        entry[field_name] = "up" if ("1" in raw_val or "up" in raw_val.lower()) else "down"
                    else:
                        m_num = re.search(r"(\d+)", raw_val)
                        if m_num:
                            entry[field_name] = int(m_num.group(1))

            prev_host = self._prev_state.get(host)
            rebooted = bool(
                prev_host
                and uptime_ticks is not None
                and prev_host.get("uptime_ticks") is not None
                and uptime_ticks < prev_host["uptime_ticks"]
            )
            dt = (now - prev_host["ts"]) if (prev_host and not rebooted) else 0.0

            parsed_ifaces = []
            for idx in sorted(if_map.keys()):
                raw_if = if_map[idx]
                use_64 = "ifHCInOctets" in raw_if and "ifHCOutOctets" in raw_if
                in_oct = raw_if.get("ifHCInOctets") if use_64 else raw_if.get("ifInOctets")
                out_oct = raw_if.get("ifHCOutOctets") if use_64 else raw_if.get("ifOutOctets")
                in_pkts = raw_if.get("ifHCInUcastPkts")
                out_pkts = raw_if.get("ifHCOutUcastPkts")

                in_bps = out_bps = in_pps = out_pps = None
                if dt >= 0.5 and prev_host and idx in prev_host.get("ifaces", {}):
                    p_if = prev_host["ifaces"][idx]
                    d_in = self._counter_delta(in_oct, p_if.get("in_oct"), use_64)
                    d_out = self._counter_delta(out_oct, p_if.get("out_oct"), use_64)
                    d_in_p = self._counter_delta(in_pkts, p_if.get("in_pkts"), True)
                    d_out_p = self._counter_delta(out_pkts, p_if.get("out_pkts"), True)
                    if d_in is not None:
                        in_bps = round((d_in * 8.0) / dt, 2)
                    if d_out is not None:
                        out_bps = round((d_out * 8.0) / dt, 2)
                    if d_in_p is not None:
                        in_pps = round(d_in_p / dt, 2)
                    if d_out_p is not None:
                        out_pps = round(d_out_p / dt, 2)

                parsed_ifaces.append({
                    "ts": now,
                    "host": host,
                    "if_index": idx,
                    "if_name": raw_if.get("ifName") or raw_if.get("ifDescr") or f"if{idx}",
                    "oper_status": raw_if.get("ifOperStatus", "unknown"),
                    "speed_mbps": raw_if.get("ifHighSpeed"),
                    "counter_width": "64-bit HC" if use_64 else "32-bit",
                    "in_bps": in_bps,
                    "out_bps": out_bps,
                    "in_pps": in_pps,
                    "out_pps": out_pps,
                    "in_errors": raw_if.get("ifInErrors"),
                    "out_errors": raw_if.get("ifOutErrors"),
                    "in_discards": raw_if.get("ifInDiscards"),
                    "out_discards": raw_if.get("ifOutDiscards"),
                    "_raw_state": {"in_oct": in_oct, "out_oct": out_oct, "in_pkts": in_pkts, "out_pkts": out_pkts},
                })

            self._prev_state[host] = {
                "ts": now,
                "uptime_ticks": uptime_ticks,
                "ifaces": {item["if_index"]: item.pop("_raw_state") for item in parsed_ifaces},
            }

            db.insert_snmp_samples(parsed_ifaces, run_id=active_run_id)

            snap = {
                "configured": True,
                "connected": True,
                "status": "Connected",
                "last_polled_at": now,
                "last_error": None,
                "host": host,
                "sys_name": sys_name,
                "sys_descr": sys_descr,
                "uptime_ticks": uptime_ticks,
                "interfaces": parsed_ifaces,
            }
            with self._lock:
                self.latest_snapshot = snap
            return snap
        except Exception as e:
            with self._lock:
                self.latest_snapshot["configured"] = True
                self.latest_snapshot["connected"] = False
                self.latest_snapshot["status"] = "SNMP Unreachable"
                self.latest_snapshot["last_polled_at"] = now
                self.latest_snapshot["last_error"] = str(e)[:220]
            return self.latest_snapshot


snmp_collector = SNMPTelemetryCollector()
