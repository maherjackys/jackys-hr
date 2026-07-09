"""System Health tab — render_system_health_tab()"""
from __future__ import annotations
import streamlit as st


_COLOR_EMOJI = {"green": "🟢", "yellow": "🟡", "red": "🔴", "gray": "⚫"}
_COLOR_CSS   = {
    "green":  "adm-badge-green",
    "yellow": "adm-badge-yellow",
    "red":    "adm-badge-red",
    "gray":   "adm-badge-gray",
}


def _pct_bar(pct: float | None, label: str, color: str) -> None:
    """Render a labeled metric with a progress bar and color badge."""
    if pct is None:
        st.caption(f"{label}: N/A")
        return
    badge_cls = _COLOR_CSS.get(color, "adm-badge-gray")
    emoji     = _COLOR_EMOJI.get(color, "⚫")
    st.markdown(
        f'<div style="margin:.4rem 0">'
        f'{emoji} **{label}** &nbsp; '
        f'<span class="adm-badge {badge_cls}">{pct:.1f}%</span>'
        f'</div>',
        unsafe_allow_html=True,
    )
    st.progress(min(pct / 100.0, 1.0))


def render_system_health_tab() -> None:
    from core.rbac import has_permission
    from core.system_health import get_health, health_color, uptime_str

    if not has_permission("system.health"):
        st.error("🚫 Permission denied: system.health required.")
        return

    st.subheader("💻 System Health")

    _col_ref, _col_ts = st.columns([1, 4])
    with _col_ref:
        _refresh = st.button("🔄 Refresh", type="primary", key="health_refresh")
    with _col_ts:
        st.caption("Metrics are cached for 10 seconds between refreshes.")

    snap = get_health(force=_refresh)

    # ── Uptime + versions ─────────────────────────────────────────────────────
    st.markdown("#### Runtime")
    _r1, _r2, _r3 = st.columns(3)
    _r1.metric("Uptime",           uptime_str(snap["uptime_seconds"]))
    _r2.metric("Python",           snap["python_version"])
    _r3.metric("Streamlit",        snap["streamlit_version"])

    st.divider()

    # ── psutil metrics ────────────────────────────────────────────────────────
    if not snap["psutil_available"]:
        st.warning(
            "**psutil** is not installed — CPU, RAM and disk metrics unavailable.  \n"
            "Install it with: `pip install psutil`  \n"
            "Add `psutil>=5.9` to `requirements.txt` for persistent installation."
        )
    else:
        st.markdown("#### CPU / Memory / Disk")
        _m1, _m2, _m3 = st.columns(3)

        with _m1:
            _cpu_c = health_color(snap["cpu_percent"])
            _pct_bar(snap["cpu_percent"], "CPU Usage", _cpu_c)
            if snap["cpu_percent"] is not None:
                st.caption(f"{snap['cpu_percent']:.1f}% utilization")

        with _m2:
            _ram_c = health_color(snap["ram_percent"])
            _pct_bar(snap["ram_percent"], "RAM Usage", _ram_c)
            if snap["ram_used_gb"] is not None:
                st.caption(
                    f"{snap['ram_used_gb']} GB / {snap['ram_total_gb']} GB"
                )

        with _m3:
            _disk_c = health_color(snap["disk_percent"])
            _pct_bar(snap["disk_percent"], "Disk Usage", _disk_c)
            if snap["disk_used_gb"] is not None:
                st.caption(
                    f"{snap['disk_used_gb']} GB / {snap['disk_total_gb']} GB"
                )

        # Alerts
        if snap.get("disk_percent", 0) and snap["disk_percent"] > 90:
            st.error("⚠️ **Disk usage exceeds 90%.** Consider cleaning up indexes or old documents.")
        if snap.get("ram_percent", 0) and snap["ram_percent"] > 85:
            st.warning("⚠️ **RAM usage above 85%.** High memory pressure may affect performance.")

    st.divider()

    # ── Database ──────────────────────────────────────────────────────────────
    st.markdown("#### Database")
    _db_c1, _db_c2 = st.columns(2)

    with _db_c1:
        if snap["db_error"]:
            st.error(f"🔴 **Database Unreachable**  \n`{snap['db_error']}`")
        elif snap["db_latency_ms"] is not None:
            _lat = snap["db_latency_ms"]
            _lat_color = "green" if _lat < 200 else ("yellow" if _lat < 800 else "red")
            _lat_emoji = _COLOR_EMOJI[_lat_color]
            st.markdown(
                f"{_lat_emoji} **Latency** &nbsp; "
                f'<span class="adm-badge {_COLOR_CSS[_lat_color]}">{_lat:.0f} ms</span>',
                unsafe_allow_html=True,
            )
            if _lat > 800:
                st.warning("High database latency. Check Supabase status.")
        else:
            st.info("Database status unknown.")

    with _db_c2:
        st.metric("Connection", "✅ Online" if not snap["db_error"] else "❌ Offline")

    st.divider()

    # ── Raw snapshot ──────────────────────────────────────────────────────────
    with st.expander("🔍 Raw Snapshot"):
        st.json(snap)

    st.caption(f"Snapshot taken at: {snap['timestamp']}")
