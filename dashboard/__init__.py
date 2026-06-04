"""Streamlit dashboard for KIS price data and fractal research.

Read pages (chart, fractal) read the DuckDB warehouse directly via
``dashboard.reader`` and never call the FastAPI job server. Only the collect
page talks to the server through ``dashboard.api_client``. This enforces the
read/write path separation: writes are serialized through the server, reads go
straight to the warehouse with lock-aware retries.
"""
