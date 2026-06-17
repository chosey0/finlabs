"""Streamlit dashboard entry point.

Run with: ``streamlit run dashboard/app.py`` (from the repo root).

Pages live in ``dashboard/pages/`` and are auto-discovered by Streamlit:
- 1_Collect  : submit on-demand collection jobs to the FastAPI job server.
- 2_Chart    : read the warehouse directly and render candlesticks.
- 3_Fractal  : reuse research.fractal to render fractal segments.
"""

# ruff: noqa: E402 -- imports follow the sys.path bootstrap below by design.
from __future__ import annotations

from _paths import ensure_repo_root_on_path

ensure_repo_root_on_path()

import streamlit as st

from dashboard.config import base_url

st.set_page_config(page_title="finlabs dashboard", layout="wide")

st.title("finlabs — KIS price & fractal research dashboard")

st.markdown(
    """
This dashboard has two data paths:

- **Collect** sends on-demand collection jobs to a configured **job server**
  (`{server}`), when one is running.
- **Chart** and **Fractal** read the warehouse **directly** (read-only, with
  lock-aware retries) and do not require the job server.

### Running the dashboard
```bash
streamlit run dashboard/app.py
```
Use the sidebar to open the **Collect**, **Chart**, and **Fractal** pages.
""".format(server=base_url())
)
