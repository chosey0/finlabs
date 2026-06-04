"""Fractal page — the first research feature.

Follows the research-feature unit shape: parameter input -> run -> render -> save.
Reuses ``research.fractal`` (no fractal logic is reimplemented here) and reads the
warehouse directly.
"""

# ruff: noqa: E402 -- imports follow the sys.path bootstrap below by design.
from __future__ import annotations

from _paths import ensure_repo_root_on_path, warehouse_path

ensure_repo_root_on_path()

import re
from pathlib import Path

import streamlit as st

from dashboard.reader import WarehouseBusyError, list_available_series, with_lock_retry
from research.fractal import (
    FractalLabelConfig,
    load_fractal_candles_from_warehouse,
    plot_fractal_events,
    select_fractal_event_segments_from_warehouse,
)
from research.fractal.plot_command import EVENT_PLOTS_DIR

st.title("Fractal research")

wh = warehouse_path()
st.caption(f"Warehouse: {wh}")

if not wh.exists():
    st.info("No warehouse yet. Use the Collect page to fetch data first.")
    st.stop()

try:
    series = list_available_series(wh)
except WarehouseBusyError:
    st.warning("Warehouse is busy (collection in progress). Please retry shortly.")
    st.stop()

if not series:
    st.info("Warehouse has no candles yet. Use the Collect page to fetch data first.")
    st.stop()

# --- Parameters ---------------------------------------------------------------
labels = [f"{s['symbol']} · {s['market']} · {s['interval']}" for s in series]
choice = st.selectbox("Series", options=list(range(len(series))), format_func=lambda i: labels[i])
selected = series[choice]

col1, col2, col3 = st.columns(3)
with col1:
    window = st.number_input("Window (odd)", min_value=3, value=21, step=2)
with col2:
    short_ma = st.number_input("Short MA", min_value=1, value=20, step=1)
with col3:
    long_ma = st.number_input("Long MA", min_value=2, value=120, step=1)

limit = st.slider("Max candles", min_value=100, max_value=5000, value=600, step=100)
min_followthrough = st.number_input(
    "Min follow-through change %", min_value=0.0, value=5.0, step=0.5
)

if int(window) % 2 == 0:
    st.error("Window must be odd.")
    st.stop()

config = FractalLabelConfig(window=int(window), short_ma=int(short_ma), long_ma=int(long_ma))

# --- Run ----------------------------------------------------------------------
try:
    # Route warehouse reads through the lock-retry choke point so a mid-write
    # lock conflict surfaces as WarehouseBusyError instead of a raw duckdb.Error.
    candles = with_lock_retry(
        lambda: load_fractal_candles_from_warehouse(
            wh,
            market=selected["market"],
            symbol=selected["symbol"],
            interval=selected["interval"],
            limit=int(limit),
        )
    )
    selection = with_lock_retry(
        lambda: select_fractal_event_segments_from_warehouse(
            wh,
            market=selected["market"],
            symbol=selected["symbol"],
            interval=selected["interval"],
            limit=int(limit),
            label_config=config,
            min_followthrough_change_pct=float(min_followthrough),
        )
    )
except WarehouseBusyError:
    st.warning("Warehouse is busy (collection in progress). Please retry shortly.")
    st.stop()
except ValueError as exc:
    st.error(str(exc))
    st.stop()

if not candles:
    st.info("No candles for this series.")
    st.stop()

m1, m2, m3 = st.columns(3)
m1.metric("Raw events", selection.raw_event_count)
m2.metric("Filtered events", selection.filtered_event_count)
m3.metric("Accepted segments", selection.saved_segment_count)

# --- Render -------------------------------------------------------------------
fig = plot_fractal_events(
    candles,
    label_config=config,
    title=f"{selected['symbol']} fractal events ({selected['interval']})",
)
fig.update_layout(height=600)
st.plotly_chart(fig, use_container_width=True)

# --- Save ---------------------------------------------------------------------
if st.button("Save plot to event_plots/"):
    out_dir = Path(EVENT_PLOTS_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)
    # Sanitize the stem so a symbol/interval can never escape event_plots/.
    safe_stem = re.sub(r"[^A-Za-z0-9._-]", "_", f"{selected['symbol']}_{selected['interval']}")
    out_path = out_dir / f"{safe_stem}_fractal.html"
    fig.write_html(str(out_path))
    st.success(f"Saved: {out_path}")
