"""Path bootstrap shared by the Streamlit entry and pages.

``streamlit run dashboard/app.py`` puts ``dashboard/`` on ``sys.path`` but not
necessarily the repo root, so importing ``modules`` / ``research`` can fail. Each
page imports this first to guarantee the repo root is importable, mirroring how
``research.fractal.plot_command`` already relies on repo-root imports.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def ensure_repo_root_on_path() -> None:
    root = str(REPO_ROOT)
    if root not in sys.path:
        sys.path.insert(0, root)


def warehouse_path() -> Path:
    ensure_repo_root_on_path()
    from modules.storage.warehouse import default_warehouse_file

    return default_warehouse_file()
