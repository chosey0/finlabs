"""Static checks that enforce the plan's architectural boundaries.

These are cheap text/import assertions, not behavioural tests, but they guard the
two structural invariants the design depends on:

- AC8: dashboard read pages must not import the FastAPI HTTP client.
- library-first: the job core (jobs.py) must not import FastAPI.
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def _imported_modules(relative: str) -> set[str]:
    """Return the set of modules imported by a file (via AST, not text matching).

    Text matching would false-positive on docstrings that merely *mention* a
    module, so we parse real import statements instead.
    """
    tree = ast.parse((REPO_ROOT / relative).read_text(encoding="utf-8"))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


def test_read_pages_do_not_import_api_client() -> None:
    for page in ("dashboard/pages/2_Chart.py", "dashboard/pages/3_Fractal.py"):
        modules = _imported_modules(page)
        assert not any("api_client" in m for m in modules), (
            f"{page} must not import the job-server HTTP client"
        )


def test_job_core_is_fastapi_free() -> None:
    modules = _imported_modules("kis_cli/server/jobs.py")
    assert not any(m == "fastapi" or m.startswith("fastapi.") for m in modules), (
        "jobs.py must stay transport-agnostic (no FastAPI)"
    )


def test_job_core_does_not_import_services() -> None:
    modules = _imported_modules("kis_cli/server/jobs.py")
    assert not any(m.startswith("kis_cli.services") for m in modules), (
        "jobs.py must stay service-agnostic"
    )
