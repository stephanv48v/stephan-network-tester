"""
Breaking-point finder: runs a series of stateful (ASTF) tests with more and more
simulated users until quality breaks, then reports the highest user count that
still met the quality limits.

Each step is a normal test run (it appears in Test History and has its own PDF).
A step "passes" when, over that step:
  - packet loss    <= max_loss_pct
  - avg latency    <= max_latency_ms
  - received rate  >= min_rx_ratio x sent rate   (traffic actually got through)

Bandwidth can either stay fixed (target_gbps) or grow with the users
(per_user_kbps), so the test pushes both connection count and throughput.
After the first failing step it runs a few in-between steps to narrow the limit.
"""
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

import database as db

SETTING_KEY = "capacity_finder_last"
HISTORY_KEY = "capacity_finder_history"
HISTORY_MAX = 25


class CapacityFinder:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._cancel = threading.Event()
        self.state: Dict[str, Any] = {"running": False}

    # ------------------------------------------------------------------ public
    @property
    def running(self) -> bool:
        return bool(self.state.get("running"))

    def status(self) -> Dict[str, Any]:
        with self._lock:
            if self.state.get("running") or self.state.get("steps"):
                return dict(self.state)
        last = db.get_setting(SETTING_KEY, None)
        return last or {"running": False, "steps": []}

    def brief(self) -> Dict[str, Any]:
        """Small status for the live telemetry feed (no DB hit except the first time after a restart)."""
        st = self.state if self.state.get("steps") or self.state.get("running") else None
        if st is None:
            if not hasattr(self, "_cached_last"):
                self._cached_last = db.get_setting(SETTING_KEY, None) or {}
            st = self._cached_last
        if not st:
            return {}
        return {
            "id": st.get("id"), "running": bool(st.get("running")), "outcome": st.get("outcome"), "message": st.get("message"),
            "current_step": st.get("current_step"), "current_users": st.get("current_users"), "plan_len": len(st.get("plan") or []),
            "max_good_users": st.get("max_good_users"), "first_bad_users": st.get("first_bad_users"),
            "started_at": st.get("started_at"), "ended_at": st.get("ended_at"), "max_users": (st.get("settings") or {}).get("max_users"),
        }

    def history(self) -> List[Dict[str, Any]]:
        return db.get_setting(HISTORY_KEY, []) or []

    def get_result(self, result_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
        """A finished finder result: the latest, or the one whose id (start time) matches."""
        if result_id is None:
            st = self.status()
            return st if st.get("steps") else None
        for h in self.history():
            if int(h.get("id") or 0) == int(result_id):
                return h
        return None

    def start(self, engine: Any, cfg: Dict[str, Any]) -> Dict[str, Any]:
        from astf_builder import MAX_SIMULATED_USERS

        with self._lock:
            if self.state.get("running"):
                return {"status": "error", "error": "The breaking-point finder is already running."}

            def num(key: str, default: float, lo: float, hi: float) -> float:
                try:
                    v = float(cfg.get(key, default) if cfg.get(key) is not None else default)
                except (TypeError, ValueError):
                    v = default
                return max(lo, min(hi, v))

            # Event mode: describe the event, steps are % of the expected crowd
            ev_in = cfg.get("event") if isinstance(cfg.get("event"), dict) else None
            event = None
            if ev_in:
                def evn(key: str, default: float, lo: float, hi: float) -> float:
                    try:
                        return max(lo, min(hi, float(ev_in.get(key, default))))
                    except (TypeError, ValueError):
                        return default
                event = {
                    "attendees": int(evn("attendees", 10000, 100, MAX_SIMULATED_USERS)),
                    "online_pct": evn("online_pct", 70, 1, 100),
                    "mbps_per_user": evn("mbps_per_user", 1.0, 0.01, 100.0),
                    "conns_per_user": evn("conns_per_user", 8, 1, 200),
                }
                pcts = ev_in.get("steps_pct") or [25, 50, 75, 100, 125, 150, 175, 200]
                pcts = sorted({max(1, min(1000, int(p))) for p in pcts})
                event["steps_pct"] = pcts
                plan = sorted({max(1, min(MAX_SIMULATED_USERS, int(round(event["attendees"] * p / 100.0)))) for p in pcts})
                start_users, max_users = plan[0], plan[-1]
                step_users = plan[1] - plan[0] if len(plan) > 1 else plan[0]
                # Per attendee: bandwidth and open connections averaged over who is online
                cfg = {**cfg, "per_user_kbps": event["online_pct"] / 100.0 * event["mbps_per_user"] * 1000.0,
                       "profile_id": cfg.get("profile_id") or "event_crowd"}
            else:
                start_users = int(num("start_users", 10000, 1, MAX_SIMULATED_USERS))
                max_users = int(num("max_users", MAX_SIMULATED_USERS, start_users, MAX_SIMULATED_USERS))
                step_users = int(num("step_users", 10000, 1, MAX_SIMULATED_USERS))
                plan: List[int] = list(range(start_users, max_users + 1, step_users))
                if not plan or plan[-1] != max_users:
                    plan.append(max_users)
            if len(plan) > 40:
                return {"status": "error", "error": f"That is {len(plan)} steps — use a bigger step size (max 40 steps)."}

            per_user = cfg.get("per_user_kbps")
            settings = {
                "start_users": start_users,
                "max_users": max_users,
                "step_users": step_users,
                "step_sec": int(num("step_sec", 60, 15, 3600)),
                "target_gbps": num("target_gbps", 1.0, 0.01, 100.0),
                # When set, each step's bandwidth = users x per_user_kbps (so load grows with users)
                "per_user_kbps": num("per_user_kbps", 20.0, 1.0, 10000.0) if per_user is not None else None,
                "max_loss_pct": num("max_loss_pct", 0.5, 0.0, 100.0),
                "max_latency_ms": num("max_latency_ms", 50.0, 0.01, 10000.0),
                "min_rx_ratio": num("min_rx_ratio", 0.95, 0.0, 1.0),
                "refine_steps": int(num("refine_steps", 2, 0, 5)),
                "profile_id": str(cfg.get("profile_id") or "imix"),
                "label": str(cfg.get("label") or "Breaking-point test"),
                "event": event,
                # Open TCP connections to hold per simulated user (event mode: online share x connections per phone)
                "conns_per_user": (event["online_pct"] / 100.0 * event["conns_per_user"]) if event else None,
            }
            path = {}
            try:
                topo = (engine.get_hardware_snapshot() or {}).get("topology_assessment") or {}
                path = {"code": topo.get("active_mode_code"), "label": topo.get("active_mode_label")}
            except Exception:
                pass
            self._cancel.clear()
            now = time.time()
            self.state = {
                "id": int(now),
                "running": True,
                "started_at": now,
                "settings": settings,
                "plan": plan,
                "path": path,
                "current_step": 0,
                "current_users": None,
                "current_run_id": None,
                "steps": [],
                "max_good_users": None,
                "first_bad_users": None,
                "outcome": "running",
                "message": "Starting…",
            }
            self._thread = threading.Thread(target=self._run, args=(engine,), daemon=True, name="capacity-finder")
            self._thread.start()
            est_min = round((len(plan) + settings["refine_steps"]) * (settings["step_sec"] + 30) / 60)
            bw = (f"{settings['per_user_kbps']:.0f} kbps per user" if settings["per_user_kbps"]
                  else f"{settings['target_gbps']} Gbps")
            db.log_audit("Breaking-Point Finder", "Started", f"{start_users:,} → {max_users:,} users",
                         f"{len(plan)} steps × {settings['step_sec']}s @ {bw}")
            return {"status": "started", "steps": len(plan), "estimated_minutes": est_min, "id": self.state["id"]}

    def stop(self, engine: Any) -> Dict[str, Any]:
        if not self.running:
            return {"status": "idle"}
        self._cancel.set()
        try:
            if engine.running:
                engine.stop_test("stopped_by_operator")
        except Exception:
            pass
        return {"status": "stopping"}

    # ----------------------------------------------------------------- worker
    def _set(self, **kw: Any) -> None:
        with self._lock:
            self.state.update(kw)

    def _target_gbps(self, users: int) -> float:
        s = self.state["settings"]
        if s.get("per_user_kbps"):
            return max(0.01, users * float(s["per_user_kbps"]) / 1e6)
        return float(s["target_gbps"])

    def _run_step(self, engine: Any, idx: int, users: int, refine: bool = False) -> str:
        """Run one step. Returns 'ok', 'bad', 'cancel' or 'error'."""
        s = self.state["settings"]
        target = self._target_gbps(users)
        ev = s.get("event")
        pct = f" ({users / ev['attendees'] * 100:.0f}% of event)" if ev else ""
        label = f"{users:,} users{pct}" + (" (narrowing down)" if refine else "")
        hold = int(users * s["conns_per_user"]) if s.get("conns_per_user") else None
        self._set(current_step=idx, current_users=users, message=f"Step {idx}: {label} @ {target:.2f} Gbps")
        ramp = 15 if users <= 20000 else 30
        res = engine.start_test({
            "name": f"[Breaking point] step {idx}: {label}",
            "profile_id": s["profile_id"],
            "traffic_engine": "trex_astf",
            "test_mode": "phased",
            "simulated_users": users,
            "simulated_devices": users * 2,
            "target_gbps": target,
            "ramp_up_sec": ramp,
            "steady_sec": s["step_sec"],
            "ramp_down_sec": 5,
            "hold_concurrency": hold,
            "event": ev,
        })
        run_id = res.get("run_id")
        if not run_id:
            self._record(idx, users, None, None, False, res.get("error") or "Test could not start", target, refine, ["error"])
            return "error"
        self._set(current_run_id=run_id)

        # Wait for this step's run to finish (the engine stops it when its duration ends)
        deadline = time.time() + ramp + s["step_sec"] + 5 + 120
        while time.time() < deadline:
            if self._cancel.is_set():
                break
            if not engine.running or engine.active_run_id != run_id:
                break
            time.sleep(1.0)
        else:
            engine.stop_test("interrupted")
        if self._cancel.is_set():
            # Stop may have landed while this step was starting: make sure it isn't left running
            if engine.running and engine.active_run_id == run_id:
                engine.stop_test("stopped_by_operator")
            return "cancel"

        # The engine flips "running" off before it finishes saving the run summary,
        # so wait until the run is finalized in the database before judging it.
        run: Dict[str, Any] = {}
        save_deadline = time.time() + 60
        while time.time() < save_deadline:
            run = db.get_test_run(int(run_id), False) or {}
            if run.get("status") not in (None, "running") and (run.get("summary") or {}).get("sample_count") is not None:
                break
            time.sleep(0.5)
        summary = run.get("summary") or {}
        ok, reason, causes = self._evaluate(summary, s)
        self._record(idx, users, run_id, summary, ok, reason, target, refine, causes)
        time.sleep(3.0)  # let gateway state tables drain a little between steps
        return "ok" if ok else "bad"

    def _run(self, engine: Any) -> None:
        s = self.state["settings"]
        outcome = "completed"
        idx = 0
        try:
            good: Optional[int] = None
            bad: Optional[int] = None
            for users in self.state["plan"]:
                if self._cancel.is_set():
                    outcome = "cancelled"
                    break
                idx += 1
                r = self._run_step(engine, idx, users)
                if r == "cancel":
                    outcome = "cancelled"
                    break
                if r == "error":
                    outcome = "error"
                    break
                if r == "bad":
                    bad = users
                    self._set(first_bad_users=users)
                    break
                good = users
                self._set(max_good_users=users)

            # Narrow down between the last good and the first bad step
            if outcome == "completed" and bad is not None:
                lo = good if good is not None else 0
                for _ in range(int(s.get("refine_steps") or 0)):
                    mid = int(round((lo + bad) / 2 / 1000.0)) * 1000 if bad - lo >= 2000 else (lo + bad) // 2
                    if mid <= lo or mid >= bad or self._cancel.is_set():
                        break
                    idx += 1
                    r = self._run_step(engine, idx, mid, refine=True)
                    if r in ("cancel", "error"):
                        outcome = "cancelled" if r == "cancel" else outcome
                        break
                    if r == "ok":
                        lo = mid
                        self._set(max_good_users=mid)
                    else:
                        bad = mid
                        self._set(first_bad_users=mid)
        except Exception as e:  # never leave the finder stuck in "running"
            outcome = "error"
            self._set(message=f"Error: {e}")
        finally:
            with self._lock:
                st = self.state
                st["running"] = False
                st["ended_at"] = time.time()
                st["current_run_id"] = None
                if outcome == "completed" and st.get("first_bad_users") is None:
                    st["outcome"] = "no_limit_found"
                    st["message"] = (f"No breaking point up to {st['plan'][-1]:,} users — "
                                     f"everything stayed within limits.")
                elif outcome == "completed":
                    st["outcome"] = "limit_found"
                    good_u = st.get("max_good_users")
                    bad_step = next((x for x in reversed(st.get("steps") or []) if not x.get("ok")), {})
                    why = f" ({bad_step.get('reason')})" if bad_step.get("reason") else ""
                    st["message"] = (f"Handled {good_u:,} users cleanly; broke at {st['first_bad_users']:,} users{why}."
                                     if good_u else f"Quality was already outside the limits at {st['first_bad_users']:,} users{why}.")
                else:
                    st["outcome"] = outcome
                    if outcome == "cancelled":
                        st["message"] = "Stopped by operator."
                    elif not str(st.get("message", "")).startswith("Error"):
                        last = (st.get("steps") or [{}])[-1]
                        st["message"] = f"Stopped: {last.get('reason') or 'test error'}"
                final = dict(st)
            db.set_setting(SETTING_KEY, final)
            self._cached_last = final
            if final.get("steps"):
                hist = [h for h in (db.get_setting(HISTORY_KEY, []) or []) if h.get("id") != final.get("id")]
                db.set_setting(HISTORY_KEY, ([final] + hist)[:HISTORY_MAX])
            db.log_audit("Breaking-Point Finder", "Finished", final.get("outcome", ""), final.get("message", ""))

    @staticmethod
    def _evaluate(summary: Dict[str, Any], s: Dict[str, Any]) -> Tuple[bool, str, List[str]]:
        if not summary or not summary.get("sample_count"):
            return False, "No measurements were recorded for this step", ["no_traffic"]
        loss = float(summary.get("drop_pct") or 0.0)
        lat_ms = float(summary.get("lat_avg_us") or 0.0) / 1000.0
        tx = float(summary.get("avg_tx_bps") or 0.0)
        rx = float(summary.get("avg_rx_bps") or 0.0)
        problems, causes = [], []
        if loss > s["max_loss_pct"]:
            problems.append(f"packet loss {loss:.3f}% (limit {s['max_loss_pct']}%)")
            causes.append("loss")
        if lat_ms > s["max_latency_ms"]:
            problems.append(f"latency {lat_ms:.2f} ms (limit {s['max_latency_ms']} ms)")
            causes.append("latency")
        if tx > 0 and rx / tx < s["min_rx_ratio"]:
            problems.append(f"only {rx / tx * 100:.1f}% of traffic got through")
            causes.append("delivery")
        if tx <= 0:
            problems.append("no traffic was sent")
            causes.append("no_traffic")
        return (not problems), ("; ".join(problems) if problems else "within limits"), causes

    def _record(self, idx: int, users: int, run_id: Any, summary: Optional[Dict[str, Any]], ok: bool, reason: str,
                target_gbps: float = 0.0, refine: bool = False, causes: Optional[List[str]] = None) -> None:
        summary = summary or {}
        s = self.state.get("settings") or {}
        ev = s.get("event")
        with self._lock:
            self.state["steps"].append({
                "step": idx,
                "users": users,
                "pct_of_event": round(users / ev["attendees"] * 100.0, 1) if ev else None,
                "target_open_conns": int(users * s["conns_per_user"]) if s.get("conns_per_user") else None,
                "run_id": run_id,
                "ok": ok,
                "reason": reason,
                "refine": refine,
                "break_causes": causes or [],
                "target_bps": target_gbps * 1e9,
                "avg_tx_bps": summary.get("avg_tx_bps"),
                "avg_rx_bps": summary.get("avg_rx_bps"),
                "max_rx_bps": summary.get("max_rx_bps"),
                "drop_pct": summary.get("drop_pct"),
                "lat_avg_us": summary.get("lat_avg_us"),
                "p99_lat_us": summary.get("p99_lat_us"),
                "jitter_avg_us": summary.get("jitter_avg_us"),
                "peak_active_flows": summary.get("peak_active_flows"),
                "peak_cps": summary.get("peak_cps"),
                "peak_gw_cpu_pct": summary.get("peak_gw_cpu_pct"),
            })


capacity_finder = CapacityFinder()
