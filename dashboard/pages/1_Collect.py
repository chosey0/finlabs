"""Collect page — submit on-demand collection jobs to the job server."""

# ruff: noqa: E402 -- imports follow the sys.path bootstrap below by design.
from __future__ import annotations

from _paths import ensure_repo_root_on_path

ensure_repo_root_on_path()

import streamlit as st

from dashboard.api_client import JobServerClient
from dashboard.config import base_url

st.title("Collect")
st.caption(f"Job server: {base_url()}")

client = JobServerClient()
server_up = client.health()
if server_up:
    st.success("Job server is reachable.")
else:
    st.error(
        "Job server is not reachable. Start the configured collection service. "
        "You can still browse the Chart and Fractal pages without it."
    )

with st.form("submit_job"):
    symbol = st.text_input("Symbol", value="NVDA").strip().upper()
    interval = st.selectbox("Interval", options=["1d", "1w", "1mo", "1m", "5m"], index=0)
    start = st.text_input("Start (YYYY-MM-DD or minute start)", value="2024-01-01")
    end = st.text_input("End (daily only, optional)", value="").strip()
    count = st.number_input("Count (minute intervals)", min_value=1, value=120, step=10)
    submitted = st.form_submit_button("Submit job", disabled=not server_up)

if submitted:
    payload = {
        "symbol": symbol,
        "interval": interval,
        "start": start,
        "end": end or None,
        "count": int(count),
    }
    try:
        job = client.submit(payload)
    except Exception as exc:  # noqa: BLE001 - surface any client/server error to the UI
        st.error(f"Failed to submit job: {exc}")
    else:
        st.session_state["last_job_id"] = job["id"]
        st.success(f"Submitted job {job['id']} (status: {job['status']}).")

last_job_id = st.session_state.get("last_job_id")
if last_job_id:
    st.subheader("Job status")
    if st.button("Refresh status"):
        st.rerun()
    try:
        job = client.get(last_job_id)
        st.json(job)
    except Exception as exc:  # noqa: BLE001
        st.warning(f"Could not fetch job {last_job_id}: {exc}")

st.subheader("Recent jobs")
try:
    jobs = client.list() if server_up else []
    if jobs:
        st.dataframe(
            [
                {k: j.get(k) for k in ("id", "symbol", "interval", "status", "market")}
                for j in jobs
            ],
            use_container_width=True,
        )
    else:
        st.caption("No jobs yet (job history is in-memory and resets on server restart).")
except Exception as exc:  # noqa: BLE001
    st.warning(f"Could not list jobs: {exc}")
