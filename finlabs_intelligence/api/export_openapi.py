"""Write the canonical deterministic OpenAPI artifact."""

from __future__ import annotations

import json
from pathlib import Path

from .app import app

OPENAPI_PATH = Path(__file__).with_name("openapi.json")


def export_openapi(path: Path = OPENAPI_PATH) -> Path:
    rendered = json.dumps(
        app.openapi(),
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )
    path.write_text(f"{rendered}\n", encoding="utf-8")
    return path


if __name__ == "__main__":
    export_openapi()
