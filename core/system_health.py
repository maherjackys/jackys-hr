"""
System health metrics — psutil when available, graceful degradation otherwise.

Public API:
    get_health(force=False)   → dict   (in-process cached 10 s)
    health_color(pct)         → 'green' | 'yellow' | 'red' | 'gray'
    uptime_str(seconds)       → str    (e.g. "2d 4h 17m")
"""
from __future__ import annotations

import datetime
import logging
import sys
import time

logger = logging.getLogger(__name__)

_APP_START = time.monotonic()
_CACHE_TTL = 10.0          # seconds between psutil polls
_last_snap: dict  = {}
_last_ts: float   = 0.0


def get_health(force: bool = False) -> dict:
    """Return a health snapshot dict.  In-process cached for 10 s."""
    global _last_snap, _last_ts
    now = time.monotonic()
    if not force and _last_snap and (now - _last_ts) < _CACHE_TTL:
        return _last_snap

    snap: dict = {
        "timestamp":        datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "uptime_seconds":   int(now - _APP_START),
        "python_version":   f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        "streamlit_version": _st_version(),
        "psutil_available": False,
        # CPU / RAM / Disk (filled by psutil)
        "cpu_percent":      None,
        "ram_used_gb":      None,
        "ram_total_gb":     None,
        "ram_percent":      None,
        "disk_used_gb":     None,
        "disk_total_gb":    None,
        "disk_percent":     None,
        # DB
        "db_latency_ms":    None,
        "db_error":         None,
    }

    # ── psutil (optional) ──────────────────────────────────────────────────────
    try:
        import psutil  # type: ignore
        snap["psutil_available"] = True
        snap["cpu_percent"]  = psutil.cpu_percent(interval=0.1)
        vm = psutil.virtual_memory()
        snap["ram_used_gb"]  = round(vm.used  / 1e9, 2)
        snap["ram_total_gb"] = round(vm.total / 1e9, 2)
        snap["ram_percent"]  = round(vm.percent, 1)
        try:
            du = psutil.disk_usage("/")
        except Exception:
            du = psutil.disk_usage("C:\\")
        snap["disk_used_gb"]  = round(du.used  / 1e9, 2)
        snap["disk_total_gb"] = round(du.total / 1e9, 2)
        snap["disk_percent"]  = round(du.percent, 1)
    except ImportError:
        pass  # not installed — caller will show warning
    except Exception as exc:
        logger.warning("system_health.psutil: %s", exc)

    # ── DB latency ─────────────────────────────────────────────────────────────
    try:
        from core.db_logger import _get_client
        t0 = time.monotonic()
        c  = _get_client()
        if c:
            c.table("app_settings").select("key").limit(1).execute()
            snap["db_latency_ms"] = round((time.monotonic() - t0) * 1000, 1)
        else:
            snap["db_error"] = "Client not initialized — check SUPABASE_URL/KEY secrets."
    except Exception as exc:
        snap["db_error"] = str(exc)[:150]

    _last_snap = snap
    _last_ts   = now
    return snap


def health_color(percent: float | None) -> str:
    """Return a semantic color name based on usage percentage."""
    if percent is None:
        return "gray"
    if percent < 70:
        return "green"
    if percent < 90:
        return "yellow"
    return "red"


def uptime_str(seconds: int) -> str:
    """Format seconds as '2d 4h 17m'."""
    d = seconds // 86400
    h = (seconds % 86400) // 3600
    m = (seconds % 3600) // 60
    parts = []
    if d:
        parts.append(f"{d}d")
    if h:
        parts.append(f"{h}h")
    parts.append(f"{m}m")
    return " ".join(parts) or "< 1m"


def _st_version() -> str:
    try:
        import streamlit
        return streamlit.__version__
    except Exception:
        return "unknown"
