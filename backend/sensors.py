"""
R640 hardware sensors: CPU/NVMe/NIC temperatures from the Linux kernel (psutil) and
inlet/exhaust temperature, fan speeds and power draw from the iDRAC via IPMI (ipmitool).

IPMI reads take ~1 s, so a background thread refreshes everything every 15 s and
callers just read the cached snapshot (never blocks the 250 ms telemetry loop).
Anything that can't be read is simply left out — no made-up values.
"""
import re
import shutil
import subprocess
import threading
import time
from typing import Any, Dict, List, Optional

try:
    import psutil
except Exception:  # pragma: no cover
    psutil = None  # type: ignore

REFRESH_SEC = 15.0

_lock = threading.Lock()
_snapshot: Dict[str, Any] = {"available": False, "updated_at": None}
_thread: Optional[threading.Thread] = None


def _num(text: str) -> Optional[float]:
    m = re.search(r"(-?\d+(?:\.\d+)?)", text or "")
    return float(m.group(1)) if m else None


def _read_kernel_temps(out: Dict[str, Any]) -> None:
    if psutil is None or not hasattr(psutil, "sensors_temperatures"):
        return
    try:
        temps = psutil.sensors_temperatures() or {}
    except Exception:
        return
    cpus: List[Dict[str, Any]] = []
    for entry in temps.get("coretemp", []):
        if str(entry.label).lower().startswith("package"):
            cpus.append({"label": f"CPU {len(cpus) + 1}", "c": round(float(entry.current), 1),
                         "high": entry.high, "critical": entry.critical})
    if cpus:
        out["cpu_packages"] = cpus
        out["cpu_max_c"] = max(c["c"] for c in cpus)
    nvme = [float(e.current) for e in temps.get("nvme", []) if str(e.label).lower() == "composite"]
    if nvme:
        out["nvme_c"] = round(max(nvme), 1)
    nic = []
    for name, entries in temps.items():
        if name.startswith(("en", "eth", "i350", "ixgbe", "i40e", "mlx")):
            vals = [float(e.current) for e in entries if e.current and 0 < e.current < 150]
            if vals:
                nic.append({"name": name, "c": round(max(vals), 1)})
    if nic:
        out["nics"] = nic
    pch = temps.get("pch_lewisburg") or []
    if pch:
        out["chipset_c"] = round(float(pch[0].current), 1)


def _ipmi(args: List[str]) -> str:
    try:
        res = subprocess.run(["ipmitool", *args], capture_output=True, text=True, timeout=8)
        return res.stdout if res.returncode == 0 else ""
    except Exception:
        return ""


def _read_ipmi(out: Dict[str, Any]) -> None:
    if not shutil.which("ipmitool"):
        return
    # e.g. "Inlet Temp       | 05h | ok  |  7.1 | 22 degrees C"
    for line in _ipmi(["sdr", "type", "temperature"]).splitlines():
        parts = [p.strip() for p in line.split("|")]
        if len(parts) < 5 or "degrees" not in parts[4]:
            continue
        name, val = parts[0].lower(), _num(parts[4])
        if val is None:
            continue
        if "inlet" in name:
            out["inlet_c"] = val
        elif "exhaust" in name:
            out["exhaust_c"] = val
    fans = []
    for line in _ipmi(["sdr", "type", "fan"]).splitlines():
        parts = [p.strip() for p in line.split("|")]
        if len(parts) >= 5 and "RPM" in parts[4]:
            rpm = _num(parts[4])
            if rpm is not None:
                fans.append({"name": parts[0], "rpm": int(rpm)})
    if fans:
        out["fans"] = fans
        out["fan_avg_rpm"] = int(sum(f["rpm"] for f in fans) / len(fans))
    for line in _ipmi(["sdr", "type", "current"]).splitlines():
        parts = [p.strip() for p in line.split("|")]
        if len(parts) >= 5 and "pwr consumption" in parts[0].lower() and "Watts" in parts[4]:
            out["power_w"] = _num(parts[4])
            break


def refresh() -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    _read_kernel_temps(out)
    _read_ipmi(out)
    out["available"] = any(k in out for k in ("cpu_max_c", "inlet_c", "exhaust_c", "nvme_c"))
    out["updated_at"] = time.time()
    with _lock:
        _snapshot.clear()
        _snapshot.update(out)
    return out


def latest() -> Dict[str, Any]:
    with _lock:
        return dict(_snapshot)


def start_background() -> None:
    global _thread
    if _thread and _thread.is_alive():
        return

    def _loop() -> None:
        while True:
            try:
                refresh()
            except Exception:
                pass
            time.sleep(REFRESH_SEC)

    _thread = threading.Thread(target=_loop, daemon=True, name="hw-sensors")
    _thread.start()
