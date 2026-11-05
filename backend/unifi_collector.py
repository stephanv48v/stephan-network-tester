"""
Official UniFi Network API & Optional Site Manager Telemetry Collector
for Cisco TRex Network Test Studio.

Supports:
  1. Official Local UniFi Network Integration API v1 (/proxy/network/integration/v1/* via X-API-KEY)
  2. Local UniFi OS / Network Application Read-Only Telemetry (/proxy/network/api/s/<site>/stat/*)
  3. Optional Ubiquiti Site Manager API (https://api.ui.com/v1/* via X-API-Key)

Security & Integrity Guarantees:
  - All API keys and passwords are encrypted server-side (Fernet) and NEVER sent to the browser or logs.
  - Strictly read-only telemetry collection (never modifies UniFi settings or initiates controller speedtests).
  - Performs runtime version & capability detection; unavailable fields remain None ("Unavailable").
"""
import threading
import time
from typing import Any, Dict, List, Optional

import httpx

import database as db


def _safe_float(val: Any) -> Optional[float]:
    if val is None or val == "":
        return None
    try:
        return float(val)
    except Exception:
        return None


def _safe_int(val: Any) -> Optional[int]:
    if val is None or val == "":
        return None
    try:
        return int(float(val))
    except Exception:
        return None


class UniFiTelemetryCollector:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.latest_snapshot: Dict[str, Any] = {
            "configured": False,
            "connected": False,
            "status": "Not Configured",
            "last_polled_at": None,
            "last_error": None,
            "controller_version": None,
            "api_mode_detected": None,
            "site_id": None,
            "site_name": "Default",
            "sites": [],
            "gateways": [],
            "switches": [],
            "access_points": [],
            "other_devices": [],
            "clients": [],
            "wan_interfaces": [],
            "summary": {
                "gw_online": False,
                "gw_name": None,
                "gw_model": None,
                "gw_cpu_pct": None,
                "gw_mem_pct": None,
                "wan_rx_bps": None,
                "wan_tx_bps": None,
                "wan_latency_ms": None,
                "active_sessions": None,
                "switches_online": 0,
                "switches_total": 0,
                "aps_online": 0,
                "aps_total": 0,
                "active_clients": None,
            },
            "capabilities": {
                "gateway_cpu_mem": False,
                "wan_throughput": False,
                "switch_port_counters": False,
                "ap_radio_stats": False,
                "client_inventory": False,
            },
        }
        self._session_cookies: Optional[httpx.Cookies] = None
        self._last_poll_ts: float = 0.0

    def get_config_public(self) -> Dict[str, Any]:
        raw = db.get_setting("unifi_config", {}) or {}
        return {
            "enabled": bool(raw.get("enabled", False)),
            "host": raw.get("host", "10.20.30.1"),
            "port": int(raw.get("port", 443)),
            "verify_ssl": bool(raw.get("verify_ssl", False)),
            "auth_mode": raw.get("auth_mode", "api_key"),  # api_key | local_account | site_manager
            "username": raw.get("username", ""),
            "site_name": raw.get("site_name", "default"),
            "site_id": raw.get("site_id", ""),
            "poll_interval_sec": int(raw.get("poll_interval_sec", 5)),
            "site_manager_enabled": bool(raw.get("site_manager_enabled", False)),
            "has_api_key": bool(raw.get("api_key_enc")),
            "has_password": bool(raw.get("password_enc")),
            "has_site_manager_key": bool(raw.get("site_manager_key_enc")),
        }

    def save_config(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        existing = db.get_setting("unifi_config", {}) or {}
        updated = {
            "enabled": bool(payload.get("enabled", existing.get("enabled", True))),
            "host": str(payload.get("host", existing.get("host", "10.20.30.1"))).strip().replace("https://", "").replace("http://", "").rstrip("/"),
            "port": int(payload.get("port", existing.get("port", 443)) or 443),
            "verify_ssl": bool(payload.get("verify_ssl", existing.get("verify_ssl", False))),
            "auth_mode": str(payload.get("auth_mode", existing.get("auth_mode", "api_key"))),
            "username": str(payload.get("username", existing.get("username", ""))).strip(),
            "site_name": str(payload.get("site_name", existing.get("site_name", "default"))).strip() or "default",
            "site_id": str(payload.get("site_id", existing.get("site_id", ""))).strip(),
            "poll_interval_sec": max(3, min(120, int(payload.get("poll_interval_sec", existing.get("poll_interval_sec", 5)) or 5))),
            "site_manager_enabled": bool(payload.get("site_manager_enabled", existing.get("site_manager_enabled", False))),
            "api_key_enc": existing.get("api_key_enc", ""),
            "password_enc": existing.get("password_enc", ""),
            "site_manager_key_enc": existing.get("site_manager_key_enc", ""),
        }
        # Unauthenticated API: if the controller host/port changes, do not silently re-send the stored
        # API key / password to the new (possibly attacker-controlled) host. Require re-entry.
        if (updated["host"], updated["port"]) != (existing.get("host", updated["host"]), int(existing.get("port", updated["port"]) or 443)):
            updated["api_key_enc"] = ""
            updated["password_enc"] = ""
        if payload.get("api_key") and not str(payload["api_key"]).startswith("••"):
            updated["api_key_enc"] = db.encrypt_secret(str(payload["api_key"]).strip())
        if payload.get("password") and not str(payload["password"]).startswith("••"):
            updated["password_enc"] = db.encrypt_secret(str(payload["password"]))
        if payload.get("site_manager_key") and not str(payload["site_manager_key"]).startswith("••"):
            updated["site_manager_key_enc"] = db.encrypt_secret(str(payload["site_manager_key"]).strip())

        self._session_cookies = None
        db.set_setting("unifi_config", updated)
        db.log_audit("UniFi Integration", "Updated UniFi Controller Configuration", updated["host"], f"Auth mode: {updated['auth_mode']}, Poll: {updated['poll_interval_sec']}s")
        return self.get_config_public()

    def _base_url(self, cfg: Dict[str, Any]) -> str:
        host = cfg.get("host", "10.20.30.1")
        port = int(cfg.get("port", 443) or 443)
        if ":" in host:
            return f"https://{host}"
        return f"https://{host}" if port == 443 else f"https://{host}:{port}"

    def poll_once(self, active_run_id: Optional[int] = None, force: bool = False) -> Dict[str, Any]:
        cfg = db.get_setting("unifi_config", {}) or {}
        if not cfg or (not cfg.get("enabled") and not force):
            self.latest_snapshot["configured"] = bool(cfg.get("api_key_enc") or cfg.get("password_enc") or cfg.get("site_manager_key_enc"))
            return self.latest_snapshot

        now = time.time()
        interval = max(3, int(cfg.get("poll_interval_sec", 5)))
        if not force and (now - self._last_poll_ts) < interval:
            return self.latest_snapshot
        self._last_poll_ts = now

        auth_mode = cfg.get("auth_mode", "api_key")
        api_key = db.decrypt_secret(cfg.get("api_key_enc", ""))
        password = db.decrypt_secret(cfg.get("password_enc", ""))
        sm_key = db.decrypt_secret(cfg.get("site_manager_key_enc", ""))

        try:
            if auth_mode == "site_manager" or (cfg.get("site_manager_enabled") and sm_key and not api_key):
                snap = self._poll_site_manager(sm_key)
            else:
                snap = self._poll_local_controller(cfg, api_key, password)

            with self._lock:
                self.latest_snapshot = snap

            if snap.get("connected"):
                s = snap["summary"]
                db.insert_unifi_sample(
                    {
                        "ts": now,
                        "controller_host": cfg.get("host", ""),
                        "site_name": snap.get("site_name", "default"),
                        "gw_name": s.get("gw_name"),
                        "gw_model": s.get("gw_model"),
                        "gw_online": s.get("gw_online"),
                        "gw_cpu_pct": s.get("gw_cpu_pct"),
                        "gw_mem_pct": s.get("gw_mem_pct"),
                        "wan_rx_bps": s.get("wan_rx_bps"),
                        "wan_tx_bps": s.get("wan_tx_bps"),
                        "wan_latency_ms": s.get("wan_latency_ms"),
                        "active_sessions": s.get("active_sessions"),
                        "switches_online": s.get("switches_online"),
                        "switches_total": s.get("switches_total"),
                        "aps_online": s.get("aps_online"),
                        "aps_total": s.get("aps_total"),
                        "active_clients": s.get("active_clients"),
                        "summary": s,
                    },
                    run_id=active_run_id,
                )
            return snap
        except Exception as e:
            err_msg = str(e)
            with self._lock:
                self.latest_snapshot["configured"] = True
                self.latest_snapshot["connected"] = False
                self.latest_snapshot["status"] = "Connection Failed"
                self.latest_snapshot["last_polled_at"] = now
                self.latest_snapshot["last_error"] = err_msg[:240]
            return self.latest_snapshot

    def _poll_local_controller(self, cfg: Dict[str, Any], api_key: str, password: str) -> Dict[str, Any]:
        base = self._base_url(cfg)
        verify_ssl = bool(cfg.get("verify_ssl", False))
        headers: Dict[str, str] = {"Accept": "application/json"}
        if api_key:
            headers["X-API-KEY"] = api_key

        with httpx.Client(verify=verify_ssl, timeout=6.0, headers=headers, cookies=self._session_cookies) as client:
            # Step 1: If local_account mode is selected (or no API key), authenticate read-only session
            if not api_key and cfg.get("username") and password:
                if not self._session_cookies:
                    login_paths = ["/api/auth/login", "/api/login"]
                    logged_in = False
                    for lp in login_paths:
                        r_login = client.post(
                            base + lp,
                            json={"username": cfg["username"], "password": password, "rememberMe": True},
                        )
                        if r_login.status_code in (200, 204):
                            self._session_cookies = client.cookies
                            logged_in = True
                            break
                    if not logged_in:
                        raise RuntimeError(f"UniFi controller authentication rejected on {base}")

            # Step 2: Try Official Local UniFi Network Integration API v1 first if X-API-KEY provided
            v1_prefixes = ["/proxy/network/integration/v1", "/integration/v1"]
            v1_info = None
            v1_prefix_used = None
            if api_key:
                for pref in v1_prefixes:
                    try:
                        r_info = client.get(f"{base}{pref}/info")
                        if r_info.status_code == 200:
                            v1_info = r_info.json()
                            v1_prefix_used = pref
                            break
                    except Exception:
                        pass

            # Also check if rich stat endpoints (/proxy/network/api/s/<site>/stat/*) are accessible
            # (In UniFi OS 4.x / Network 8.x-9.x, X-API-KEY or session cookies often grant access to /proxy/network/api/s/<site>/stat/* too!)
            site_slug = cfg.get("site_name") or "default"
            stat_prefixes = [f"/proxy/network/api/s/{site_slug}", f"/api/s/{site_slug}"]
            rich_devices = None
            rich_health = None
            rich_clients = None
            rich_sysinfo = None

            for sp in stat_prefixes:
                try:
                    r_dev = client.get(f"{base}{sp}/stat/device")
                    if r_dev.status_code == 200 and "data" in r_dev.json():
                        rich_devices = r_dev.json().get("data", [])
                        r_hlth = client.get(f"{base}{sp}/stat/health")
                        if r_hlth.status_code == 200:
                            rich_health = r_hlth.json().get("data", [])
                        r_sta = client.get(f"{base}{sp}/stat/sta")
                        if r_sta.status_code == 200:
                            rich_clients = r_sta.json().get("data", [])
                        r_sys = client.get(f"{base}{sp}/stat/sysinfo")
                        if r_sys.status_code == 200:
                            sys_data = r_sys.json().get("data", [])
                            if sys_data:
                                rich_sysinfo = sys_data[0]
                        break
                except Exception:
                    pass

            if rich_devices is not None:
                return self._parse_rich_controller_data(
                    cfg=cfg,
                    devices=rich_devices,
                    health=rich_health or [],
                    clients=rich_clients or [],
                    sysinfo=rich_sysinfo or {},
                    v1_info=v1_info,
                )

            if v1_prefix_used and v1_info is not None:
                return self._poll_and_parse_v1_integration(client, base, v1_prefix_used, v1_info, cfg)

            # Session cookie may have expired: drop it so the next poll re-authenticates
            self._session_cookies = None
            raise RuntimeError(f"Could not reach UniFi Network API on {base} (check IP, port, or API key)")

    def _poll_and_parse_v1_integration(
        self,
        client: httpx.Client,
        base: str,
        pref: str,
        v1_info: Dict[str, Any],
        cfg: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Parse official UniFi Network Integration API v1 endpoints (/sites, /devices, /statistics/latest, /clients)."""
        r_sites = client.get(f"{base}{pref}/sites")
        sites_data = r_sites.json().get("data", []) if r_sites.status_code == 200 else []
        if not sites_data:
            raise RuntimeError("No sites returned by UniFi Integration API v1")

        chosen_site = sites_data[0]
        if cfg.get("site_id"):
            for s in sites_data:
                if s.get("id") == cfg["site_id"] or s.get("internalReference") == cfg["site_id"]:
                    chosen_site = s
                    break

        site_id = chosen_site.get("id")
        site_name = chosen_site.get("name") or chosen_site.get("internalReference") or "Default"

        r_devs = client.get(f"{base}{pref}/sites/{site_id}/devices?limit=200")
        devs_raw = r_devs.json().get("data", []) if r_devs.status_code == 200 else []

        r_cl = client.get(f"{base}{pref}/sites/{site_id}/clients?limit=500")
        clients_raw = r_cl.json().get("data", []) if r_cl.status_code == 200 else []

        gateways, switches, aps, others = [], [], [], []
        gw_cpu = gw_mem = wan_rx_bps = wan_tx_bps = None

        for d in devs_raw:
            did = d.get("id")
            model = str(d.get("model", ""))
            name = d.get("name") or model or "UniFi Device"
            state_str = str(d.get("state", "ONLINE")).upper()
            online = state_str in ("ONLINE", "CONNECTED", "1")
            features = [str(f).lower() for f in (d.get("features") or [])]

            # Probe /statistics/latest for gateways & switches
            stats_latest = {}
            if did and online:
                try:
                    rs = client.get(f"{base}{pref}/sites/{site_id}/devices/{did}/statistics/latest")
                    if rs.status_code == 200:
                        stats_latest = rs.json() or {}
                except Exception:
                    pass

            cpu_val = _safe_float(stats_latest.get("cpuUtilizationPct"))
            mem_val = _safe_float(stats_latest.get("memoryUtilizationPct"))
            up_sec = _safe_int(stats_latest.get("uptimeSec"))
            ul_bps = _safe_float((stats_latest.get("uplink") or {}).get("txRateBps"))
            dl_bps = _safe_float((stats_latest.get("uplink") or {}).get("rxRateBps"))

            item = {
                "id": did,
                "name": name,
                "model": model,
                "mac": d.get("macAddress"),
                "ip": d.get("ipAddress"),
                "firmware": d.get("firmwareVersion"),
                "online": online,
                "state": "Online" if online else state_str,
                "cpu_pct": cpu_val,
                "mem_pct": mem_val,
                "uptime_sec": up_sec,
                "uplink_rx_bps": dl_bps,
                "uplink_tx_bps": ul_bps,
                "ports": d.get("interfaces", {}).get("ports") if isinstance(d.get("interfaces"), dict) else None,
                "radios": d.get("interfaces", {}).get("radios") if isinstance(d.get("interfaces"), dict) else None,
            }

            is_gw = "gateway" in features or any(tag in model.upper() for tag in ("EFG", "UDM", "UXG", "USG", "UCG"))
            is_sw = "switching" in features or model.upper().startswith("US")
            is_ap = "accesspoint" in features or "wifi" in features or model.upper().startswith(("U6", "U7", "UAP", "UK"))

            if is_gw:
                gateways.append(item)
                if gw_cpu is None:
                    gw_cpu = cpu_val
                    gw_mem = mem_val
                    wan_rx_bps = dl_bps
                    wan_tx_bps = ul_bps
            elif is_sw:
                switches.append(item)
            elif is_ap:
                aps.append(item)
            else:
                others.append(item)

        parsed_clients = [
            {
                "id": c.get("id"),
                "name": c.get("name") or c.get("ipAddress") or c.get("macAddress"),
                "ip": c.get("ipAddress"),
                "mac": c.get("macAddress"),
                "type": c.get("type", "WIRED"),
                "connected_at": c.get("connectedAt"),
                "uplink_device_id": c.get("uplinkDeviceId"),
                "tx_bps": None,
                "rx_bps": None,
            }
            for c in clients_raw
        ]

        gw0 = gateways[0] if gateways else {}
        summary = {
            "gw_online": bool(gw0.get("online")) if gateways else False,
            "gw_name": gw0.get("name"),
            "gw_model": gw0.get("model"),
            "gw_ip": gw0.get("ip"),
            "gw_cpu_pct": gw_cpu,
            "gw_mem_pct": gw_mem,
            "gw_temp_c": None,  # the Integration API v1 doesn't expose temperatures
            "gw_uptime_sec": gw0.get("uptime_sec"),
            "gw_firmware": gw0.get("firmware"),
            "wan_rx_bps": wan_rx_bps,
            "wan_tx_bps": wan_tx_bps,
            "wan_latency_ms": None,
            "active_sessions": None,
            "switches_online": sum(1 for s in switches if s["online"]),
            "switches_total": len(switches),
            "aps_online": sum(1 for a in aps if a["online"]),
            "aps_total": len(aps),
            "active_clients": len(parsed_clients),
        }

        return {
            "configured": True,
            "connected": True,
            "status": "Connected (Integration API v1)",
            "last_polled_at": time.time(),
            "last_error": None,
            "controller_version": v1_info.get("applicationVersion", "UniFi Network API v1"),
            "api_mode_detected": "Official Integration API v1",
            "site_id": site_id,
            "site_name": site_name,
            "sites": [{"id": s.get("id"), "name": s.get("name") or s.get("internalReference")} for s in sites_data],
            "gateways": gateways,
            "switches": switches,
            "access_points": aps,
            "other_devices": others,
            "clients": parsed_clients[:250],
            "wan_interfaces": [],
            "summary": summary,
            "capabilities": {
                "gateway_cpu_mem": gw_cpu is not None,
                "wan_throughput": wan_rx_bps is not None,
                "switch_port_counters": False,
                "ap_radio_stats": any(a.get("radios") for a in aps),
                "client_inventory": True,
            },
        }

    def _parse_rich_controller_data(
        self,
        cfg: Dict[str, Any],
        devices: List[Dict[str, Any]],
        health: List[Dict[str, Any]],
        clients: List[Dict[str, Any]],
        sysinfo: Dict[str, Any],
        v1_info: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Parse rich UniFi Network telemetry (EFG CPU/RAM, WAN bps, Switch port_table, AP radio_table, Clients)."""
        gateways, switches, aps, others, wan_ifaces = [], [], [], [], []

        wan_health = next((h for h in health if h.get("subsystem") == "wan"), {})
        wan_rx_bps = _safe_float(wan_health.get("rx_bytes-r"))
        if wan_rx_bps is not None:
            wan_rx_bps *= 8.0
        wan_tx_bps = _safe_float(wan_health.get("tx_bytes-r"))
        if wan_tx_bps is not None:
            wan_tx_bps *= 8.0
        wan_lat = _safe_float(wan_health.get("latency"))

        for d in devices:
            dtype = str(d.get("type", "")).lower()
            model = str(d.get("model", ""))
            name = d.get("name") or model or d.get("mac", "UniFi Device")
            online = int(d.get("state", 0) or 0) == 1
            sys_stats = d.get("system-stats") or {}
            cpu_pct = _safe_float(sys_stats.get("cpu"))
            mem_pct = _safe_float(sys_stats.get("mem"))
            uptime = _safe_int(d.get("uptime"))
            num_sta = _safe_int(d.get("num_sta"))
            # Gateways/switches report e.g. "temperatures": [{"name": "CPU", "type": "cpu", "value": 52.0}, ...]
            temps_parsed = []
            for t in d.get("temperatures") or []:
                tv = _safe_float(t.get("value"))
                if tv is not None:
                    temps_parsed.append({"name": t.get("name") or t.get("type") or "Temp", "type": t.get("type"), "c": round(tv, 1)})
            if not temps_parsed and _safe_float(d.get("general_temperature")) is not None:
                temps_parsed.append({"name": "Device", "type": "board", "c": round(_safe_float(d.get("general_temperature")), 1)})
            cpu_temp = next((t["c"] for t in temps_parsed if str(t.get("type") or t["name"]).lower() == "cpu"), None)
            temp_c = cpu_temp if cpu_temp is not None else (max(t["c"] for t in temps_parsed) if temps_parsed else None)

            ports_parsed = []
            for p in d.get("port_table") or []:
                rx_r = _safe_float(p.get("rx_bytes-r"))
                tx_r = _safe_float(p.get("tx_bytes-r"))
                spd = _safe_int(p.get("speed"))
                rx_bps_p = (rx_r * 8.0) if rx_r is not None else None
                tx_bps_p = (tx_r * 8.0) if tx_r is not None else None
                util_pct = None
                if spd and spd > 0 and rx_bps_p is not None and tx_bps_p is not None:
                    util_pct = round((max(rx_bps_p, tx_bps_p) / (spd * 1_000_000.0)) * 100.0, 2)
                p_obj = {
                    "port_idx": p.get("port_idx"),
                    "name": p.get("name") or f"Port {p.get('port_idx')}",
                    "ifname": p.get("ifname"),
                    "up": bool(p.get("up")),
                    "speed_mbps": spd,
                    "full_duplex": p.get("full_duplex"),
                    "is_uplink": bool(p.get("is_uplink")),
                    "rx_bps": rx_bps_p,
                    "tx_bps": tx_bps_p,
                    "utilization_pct": util_pct,
                    "rx_packets": _safe_int(p.get("rx_packets")),
                    "tx_packets": _safe_int(p.get("tx_packets")),
                    "rx_errors": _safe_int(p.get("rx_errors")),
                    "tx_errors": _safe_int(p.get("tx_errors")),
                    "rx_dropped": _safe_int(p.get("rx_dropped")),
                    "tx_dropped": _safe_int(p.get("tx_dropped")),
                }
                ports_parsed.append(p_obj)
                if p.get("port_poe") is False and ("wan" in str(p.get("name", "")).lower() or p.get("is_uplink")) and dtype in ("ugw", "udm", "uxg"):
                    wan_ifaces.append(p_obj)

            radios_parsed = []
            for r in d.get("radio_table_stats") or d.get("radio_table") or []:
                radios_parsed.append({
                    "name": r.get("name"),
                    "radio": r.get("radio"),
                    "channel": r.get("channel"),
                    "cu_total_pct": _safe_int(r.get("cu_total")),
                    "num_sta": _safe_int(r.get("num_sta")),
                    "tx_power": r.get("tx_power"),
                })

            dev_obj = {
                "id": d.get("_id") or d.get("mac"),
                "name": name,
                "model": model,
                "type": dtype,
                "mac": d.get("mac"),
                "ip": d.get("ip"),
                "firmware": d.get("version"),
                "online": online,
                "state": "Online" if online else "Offline",
                "cpu_pct": cpu_pct,
                "mem_pct": mem_pct,
                "uptime_sec": uptime,
                "temperatures": temps_parsed,
                "temp_c": temp_c,
                "num_clients": num_sta,
                "rx_bps": (_safe_float(d.get("rx_bytes-r")) or 0.0) * 8.0 if d.get("rx_bytes-r") is not None else None,
                "tx_bps": (_safe_float(d.get("tx_bytes-r")) or 0.0) * 8.0 if d.get("tx_bytes-r") is not None else None,
                # (num_desktop is a desktop-client count, not firewall sessions - do not report it as sessions)
                "active_sessions": _safe_int(((d.get("stat") or {}).get("gw") or {}).get("num_sessions")),
                "ports": ports_parsed,
                "radios": radios_parsed,
            }

            if dtype in ("ugw", "udm", "uxg") or any(k in model.upper() for k in ("EFG", "UDM", "UXG", "USG", "UCG")):
                gateways.append(dev_obj)
            elif dtype in ("usw",) or model.upper().startswith("US"):
                switches.append(dev_obj)
            elif dtype in ("uap",) or model.upper().startswith(("U6", "U7", "UAP")):
                aps.append(dev_obj)
            else:
                others.append(dev_obj)

        dev_by_mac = {d.get("mac"): d.get("name") for d in (gateways + switches + aps + others) if d.get("mac")}
        clients_parsed = []
        for c in clients[:300]:
            assoc_mac = c.get("ap_mac") or c.get("sw_mac")
            rx_r = _safe_float(c.get("rx_bytes-r"))
            tx_r = _safe_float(c.get("tx_bytes-r"))
            clients_parsed.append({
                "id": c.get("_id") or c.get("mac"),
                "name": c.get("name") or c.get("hostname") or c.get("ip") or c.get("mac"),
                "ip": c.get("ip"),
                "mac": c.get("mac"),
                "type": "WIRED" if c.get("is_wired") else "WIRELESS",
                "associated_device": dev_by_mac.get(assoc_mac, assoc_mac or "Unknown"),
                "sw_port": c.get("sw_port"),
                "signal_dbm": _safe_int(c.get("signal")),
                "rx_bps": (rx_r * 8.0) if rx_r is not None else None,
                "tx_bps": (tx_r * 8.0) if tx_r is not None else None,
            })

        gw0 = gateways[0] if gateways else {}
        if wan_rx_bps is None and gw0:
            wan_rx_bps = gw0.get("rx_bps")
            wan_tx_bps = gw0.get("tx_bps")

        ver = (v1_info or {}).get("applicationVersion") or sysinfo.get("version") or "Detected"
        summary = {
            "gw_online": bool(gw0.get("online")) if gateways else False,
            "gw_name": gw0.get("name"),
            "gw_model": gw0.get("model"),
            "gw_ip": gw0.get("ip") or wan_health.get("wan_ip"),
            "gw_cpu_pct": gw0.get("cpu_pct"),
            "gw_mem_pct": gw0.get("mem_pct"),
            "gw_temp_c": gw0.get("temp_c"),
            "gw_temperatures": gw0.get("temperatures") or [],
            "gw_uptime_sec": gw0.get("uptime_sec"),
            "gw_firmware": gw0.get("firmware"),
            "wan_rx_bps": wan_rx_bps,
            "wan_tx_bps": wan_tx_bps,
            "wan_latency_ms": wan_lat,
            "active_sessions": gw0.get("active_sessions"),
            "switches_online": sum(1 for s in switches if s["online"]),
            "switches_total": len(switches),
            "aps_online": sum(1 for a in aps if a["online"]),
            "aps_total": len(aps),
            "active_clients": len(clients),
        }

        return {
            "configured": True,
            "connected": True,
            "status": "Connected",
            "last_polled_at": time.time(),
            "last_error": None,
            "controller_version": f"UniFi Network {ver}",
            "api_mode_detected": "UniFi OS Telemetry + Integration API" if v1_info else "UniFi OS Controller API",
            "site_id": cfg.get("site_name", "default"),
            "site_name": sysinfo.get("name") or cfg.get("site_name", "Default"),
            "sites": [{"id": cfg.get("site_name", "default"), "name": sysinfo.get("name") or "Default"}],
            "gateways": gateways,
            "switches": switches,
            "access_points": aps,
            "other_devices": others,
            "clients": clients_parsed,
            "wan_interfaces": wan_ifaces,
            "summary": summary,
            "capabilities": {
                "gateway_cpu_mem": summary["gw_cpu_pct"] is not None,
                "wan_throughput": wan_rx_bps is not None,
                "switch_port_counters": any(bool(s.get("ports")) for s in switches),
                "ap_radio_stats": any(bool(a.get("radios")) for a in aps),
                "client_inventory": True,
            },
        }

    def _poll_site_manager(self, sm_key: str) -> Dict[str, Any]:
        """Poll official Ubiquiti Site Manager Cloud API (https://api.ui.com/v1)."""
        if not sm_key:
            raise RuntimeError("Site Manager API key not configured")
        headers = {"X-API-Key": sm_key, "Accept": "application/json"}
        with httpx.Client(timeout=8.0, headers=headers) as client:
            r_hosts = client.get("https://api.ui.com/v1/hosts")
            if r_hosts.status_code != 200:
                raise RuntimeError(f"Site Manager API returned HTTP {r_hosts.status_code}")
            hosts_data = r_hosts.json().get("data", [])
            r_devs = client.get("https://api.ui.com/v1/devices")
            devs_groups = r_devs.json().get("data", []) if r_devs.status_code == 200 else []

        gateways, switches, aps, others = [], [], [], []
        for grp in devs_groups:
            for d in grp.get("devices", []):
                model = str(d.get("model", ""))
                short = str(d.get("shortname", ""))
                online = str(d.get("status", "")).lower() == "online"
                obj = {
                    "id": d.get("id") or d.get("mac"),
                    "name": d.get("name") or model,
                    "model": model,
                    "mac": d.get("mac"),
                    "ip": d.get("ip"),
                    "firmware": d.get("version"),
                    "online": online,
                    "state": "Online" if online else "Offline",
                    "cpu_pct": None,
                    "mem_pct": None,
                    "uptime_sec": None,
                    "ports": None,
                    "radios": None,
                }
                if d.get("isConsole") or any(k in (model + short).upper() for k in ("EFG", "UDM", "UXG", "UCG")):
                    gateways.append(obj)
                elif (model + short).upper().startswith("US"):
                    switches.append(obj)
                elif (model + short).upper().startswith(("U6", "U7", "UAP")):
                    aps.append(obj)
                else:
                    others.append(obj)

        gw0 = gateways[0] if gateways else {}
        summary = {
            "gw_online": bool(gw0.get("online")) if gateways else False,
            "gw_name": gw0.get("name"),
            "gw_model": gw0.get("model"),
            "gw_ip": gw0.get("ip"),
            "gw_cpu_pct": None,
            "gw_mem_pct": None,
            "wan_rx_bps": None,
            "wan_tx_bps": None,
            "wan_latency_ms": None,
            "active_sessions": None,
            "switches_online": sum(1 for s in switches if s["online"]),
            "switches_total": len(switches),
            "aps_online": sum(1 for a in aps if a["online"]),
            "aps_total": len(aps),
            "active_clients": None,
        }
        return {
            "configured": True,
            "connected": True,
            "status": f"Connected via Site Manager ({len(hosts_data)} Hosts)",
            "last_polled_at": time.time(),
            "last_error": None,
            "controller_version": "Ubiquiti Site Manager v1",
            "api_mode_detected": "Site Manager Cloud API (Inventory Mode)",
            "site_id": "cloud",
            "site_name": "Site Manager Cloud",
            "sites": [{"id": h.get("id"), "name": (h.get("reportedState") or {}).get("hostname", h.get("id"))} for h in hosts_data],
            "gateways": gateways,
            "switches": switches,
            "access_points": aps,
            "other_devices": others,
            "clients": [],
            "wan_interfaces": [],
            "summary": summary,
            "capabilities": {
                "gateway_cpu_mem": False,
                "wan_throughput": False,
                "switch_port_counters": False,
                "ap_radio_stats": False,
                "client_inventory": False,
            },
        }


unifi_collector = UniFiTelemetryCollector()
