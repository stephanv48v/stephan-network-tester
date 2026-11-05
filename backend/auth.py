"""
Single-admin login for the Network Test Studio web UI.

- One admin password, hashed with PBKDF2-HMAC-SHA256 (random 16-byte salt, 240k iterations),
  stored in appliance_settings under "auth_admin".
- Stateless signed session cookie ("nts_session"): base64url(JSON {u, exp}) + "." + base64url(HMAC-SHA256),
  keyed by a random 32-byte secret in appliance_settings "auth_session_secret". Changing the password
  rotates the secret, which invalidates every existing session.
- Per-client-IP brute-force limiter: 5 failed attempts within 10 minutes -> 429 for the rest of that window.

Owner reset (run on the appliance):
    sudo /opt/stephan-network-tester/venv/bin/python /opt/stephan-network-tester/backend/auth.py --reset
clears the admin password so the next browser visit shows the "Create admin password" screen.
"""
import base64
import hashlib
import hmac
import json
import os
import secrets
import sys
import threading
import time
from typing import Any, Dict, Mapping, Optional, Tuple

# Allow `python backend/auth.py --reset` to import the sibling database module.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import database as db  # noqa: E402

COOKIE_NAME = "nts_session"
SESSION_MAX_AGE_SEC = 30 * 24 * 3600
ADMIN_USERNAME = "admin"
PBKDF2_ITERATIONS = 240_000
MIN_PASSWORD_LEN = 8
MAX_PASSWORD_LEN = 1024
MAX_FAILURES = 5
FAILURE_WINDOW_SEC = 600

SETTING_ADMIN = "auth_admin"
SETTING_SECRET = "auth_session_secret"

# Paths reachable without a session (everything else needs one).
PUBLIC_EXACT_PATHS = {
    "/login",
    "/favicon.ico",
    "/api/auth/status",
    "/api/auth/setup",
    "/api/auth/login",
    "/api/auth/logout",
}
PUBLIC_PREFIXES = ("/static/",)

# Settings are re-read at most this often so an out-of-process `--reset` takes effect without a restart.
_STATE_TTL_SEC = 5.0

_state_lock = threading.Lock()
_state_cache: Dict[str, Any] = {"loaded_at": 0.0, "admin": None, "secret": None}
_write_lock = threading.Lock()
_fail_lock = threading.Lock()
_failures: Dict[str, Tuple[float, int]] = {}  # ip -> (window_start, failed_count)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _b64e(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64d(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _hash_password(password: str, salt: bytes, iterations: int) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)


def _invalidate_cache() -> None:
    with _state_lock:
        _state_cache["loaded_at"] = 0.0


def _load_state() -> Tuple[Optional[Dict[str, Any]], bytes]:
    """Returns (admin_record_or_None, session_secret), creating the secret once if missing."""
    now = time.monotonic()
    with _state_lock:
        if _state_cache["secret"] is not None and now - _state_cache["loaded_at"] < _STATE_TTL_SEC:
            return _state_cache["admin"], _state_cache["secret"]
    admin = db.get_setting(SETTING_ADMIN, None)
    if not (isinstance(admin, dict) and admin.get("hash") and admin.get("salt")):
        admin = None
    secret_hex = db.get_setting(SETTING_SECRET, None)
    if not secret_hex:
        with _write_lock:
            secret_hex = db.get_setting(SETTING_SECRET, None)
            if not secret_hex:
                secret_hex = secrets.token_hex(32)
                db.set_setting(SETTING_SECRET, secret_hex)
    secret = bytes.fromhex(secret_hex)
    with _state_lock:
        _state_cache.update({"loaded_at": now, "admin": admin, "secret": secret})
    return admin, secret


def _rotate_secret() -> None:
    db.set_setting(SETTING_SECRET, secrets.token_hex(32))


def password_problem(password: Any) -> Optional[str]:
    """Returns a human-readable reason the password is unacceptable, or None if it is fine."""
    if not isinstance(password, str) or len(password) < MIN_PASSWORD_LEN:
        return f"Password must be at least {MIN_PASSWORD_LEN} characters"
    if len(password) > MAX_PASSWORD_LEN:
        return f"Password must be at most {MAX_PASSWORD_LEN} characters"
    return None


# ---------------------------------------------------------------------------
# Password management
# ---------------------------------------------------------------------------
def is_password_set() -> bool:
    admin, _ = _load_state()
    return admin is not None


def _store_password(password: str) -> None:
    salt = secrets.token_bytes(16)
    record = {
        "salt": salt.hex(),
        "hash": _hash_password(password, salt, PBKDF2_ITERATIONS).hex(),
        "iterations": PBKDF2_ITERATIONS,
        "updated_at": time.time(),
    }
    _rotate_secret()  # kill every session issued under the previous password
    db.set_setting(SETTING_ADMIN, record)
    _invalidate_cache()


def setup_password(password: str) -> bool:
    """Sets the first admin password. Returns False if one is already set (race-safe within the process)."""
    with _write_lock:
        _invalidate_cache()
        if is_password_set():
            return False
        _store_password(password)
        return True


def change_password(new_password: str) -> None:
    with _write_lock:
        _store_password(new_password)


def verify_password(password: Any) -> bool:
    admin, _ = _load_state()
    if admin is None or not isinstance(password, str) or len(password) > MAX_PASSWORD_LEN:
        return False
    try:
        salt = bytes.fromhex(admin["salt"])
        expected = bytes.fromhex(admin["hash"])
        iterations = int(admin.get("iterations") or PBKDF2_ITERATIONS)
    except Exception:
        return False
    return hmac.compare_digest(_hash_password(password, salt, iterations), expected)


def reset_admin() -> bool:
    """Clears the admin password (and rotates the session secret). Returns True if a password was set."""
    with _write_lock:
        had = isinstance(db.get_setting(SETTING_ADMIN, None), dict)
        db.set_setting(SETTING_ADMIN, None)
        _rotate_secret()
        _invalidate_cache()
        return had


# ---------------------------------------------------------------------------
# Session tokens & cookies
# ---------------------------------------------------------------------------
def create_session_token(username: str = ADMIN_USERNAME) -> str:
    _, secret = _load_state()
    payload = _b64e(json.dumps({"u": username, "exp": int(time.time()) + SESSION_MAX_AGE_SEC}, separators=(",", ":")).encode())
    sig = _b64e(hmac.new(secret, payload.encode("ascii"), hashlib.sha256).digest())
    return f"{payload}.{sig}"


def validate_session_token(token: Optional[str]) -> Optional[str]:
    """Returns the username for a valid, unexpired token (while a password is set), else None."""
    if not token or len(token) > 512 or "." not in token:
        return None
    admin, secret = _load_state()
    if admin is None:
        return None
    payload, _, sig = token.partition(".")
    expected = _b64e(hmac.new(secret, payload.encode("ascii", "ignore"), hashlib.sha256).digest())
    if not hmac.compare_digest(sig.encode("ascii", "ignore"), expected.encode("ascii")):
        return None
    try:
        data = json.loads(_b64d(payload))
        if int(data.get("exp", 0)) < time.time():
            return None
        return str(data.get("u") or "") or None
    except Exception:
        return None


def is_authenticated(cookies: Mapping[str, str]) -> bool:
    return validate_session_token(cookies.get(COOKIE_NAME)) is not None


def set_session_cookie(response: Any, token: str) -> None:
    # No Secure flag: the appliance is served over plain HTTP on the lab LAN.
    response.set_cookie(
        COOKIE_NAME, token, max_age=SESSION_MAX_AGE_SEC, path="/", httponly=True, samesite="lax"
    )


def clear_session_cookie(response: Any) -> None:
    response.delete_cookie(COOKIE_NAME, path="/", httponly=True, samesite="lax")


def is_public_path(path: str) -> bool:
    return path in PUBLIC_EXACT_PATHS or path.startswith(PUBLIC_PREFIXES)


def websocket_origin_ok(headers: Mapping[str, str]) -> bool:
    """Rejects cross-site WebSocket handshakes (browsers always send Origin; non-browser clients may omit it)."""
    origin = headers.get("origin")
    if not origin:
        return True
    host = (headers.get("host") or "").lower()
    return origin.lower().split("://", 1)[-1].rstrip("/") == host


# ---------------------------------------------------------------------------
# Brute-force limiter (per client IP, in-process)
# ---------------------------------------------------------------------------
def retry_after_seconds(ip: str) -> int:
    """>0 when this IP is locked out (5 failures in the current 10-minute window)."""
    now = time.time()
    with _fail_lock:
        start, count = _failures.get(ip, (0.0, 0))
        if now - start >= FAILURE_WINDOW_SEC:
            _failures.pop(ip, None)
            return 0
        if count >= MAX_FAILURES:
            return max(1, int(start + FAILURE_WINDOW_SEC - now))
        return 0


def record_failure(ip: str) -> None:
    now = time.time()
    with _fail_lock:
        if len(_failures) > 10000:  # bound memory: drop expired windows
            for k in [k for k, (s, _) in _failures.items() if now - s >= FAILURE_WINDOW_SEC]:
                _failures.pop(k, None)
        start, count = _failures.get(ip, (now, 0))
        if now - start >= FAILURE_WINDOW_SEC:
            start, count = now, 0
        _failures[ip] = (start, count + 1)


def clear_failures(ip: str) -> None:
    with _fail_lock:
        _failures.pop(ip, None)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _main(argv: list) -> int:
    if "--reset" not in argv:
        print("Usage: auth.py --reset   (clears the admin password; next visit shows the create-password screen)")
        return 2
    db.init_db()
    had = reset_admin()
    print(f"Database: {db.DB_PATH}")
    if had:
        print("Admin password cleared and all sessions invalidated.")
    else:
        print("No admin password was set; session secret rotated anyway.")
    print("Open the web UI to create a new admin password.")
    try:
        db.log_audit("Security", "Admin Password Reset (CLI)", "admin", "", actor="console")
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
