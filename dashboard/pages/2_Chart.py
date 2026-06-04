"""Chart page — read the warehouse directly and render candlesticks."""

# ruff: noqa: E402 -- imports follow the sys.path bootstrap below by design.
from __future__ import annotations

from _paths import ensure_repo_root_on_path, warehouse_path

ensure_repo_root_on_path()

import plotly.graph_objects as go
import streamlit as st

from dashboard.reader import WarehouseBusyError, list_available_series, read_candles_with_retry

st.title("Chart")

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

labels = [f"{s['symbol']} · {s['market']} · {s['interval']}" for s in series]
choice = st.selectbox("Series", options=list(range(len(series))), format_func=lambda i: labels[i])
selected = series[choice]
limit = st.slider("Max candles", min_value=50, max_value=2000, value=300, step=50)

try:
    candles = read_candles_with_retry(
        wh,
        market=selected["market"],
        symbol=selected["symbol"],
        interval=selected["interval"],
        limit=limit,
    )
except WarehouseBusyError:
    st.warning("Warehouse is busy (collection in progress). Please retry shortly.")
    st.stop()

if not candles:
    st.info("No candles for this series.")
    st.stop()

fig = go.Figure(
    data=[
        go.Candlestick(
            x=[c.timestamp for c in candles],
            open=[c.open for c in candles],
            high=[c.high for c in candles],
            low=[c.low for c in candles],
            close=[c.close for c in candles],
            name=selected["symbol"],
        )
    ]
)
fig.update_layout(
    title=f"{selected['symbol']} ({selected['interval']})",
    xaxis_rangeslider_visible=False,
    height=600,
)
st.plotly_chart(fig, use_container_width=True)
st.caption(f"{len(candles)} candles")
