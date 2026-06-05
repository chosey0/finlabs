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


def _python_files(relative_dir: str) -> tuple[Path, ...]:
    return tuple(sorted((REPO_ROOT / relative_dir).rglob("*.py")))


def test_modules_broker_sdks_stay_standalone() -> None:
    forbidden_prefixes = (
        "modules.adapters",
        "modules.orchestration",
        "modules.storage",
        "modules.domain",
    )
    for path in _python_files("modules/brokers"):
        modules = _imported_modules(str(path.relative_to(REPO_ROOT)))
        assert not any(m.startswith(forbidden_prefixes) for m in modules), (
            f"{path} must stay SDK-pure and not import adapters/orchestration/storage/domain"
        )


def test_modules_adapters_do_not_persist_or_orchestrate() -> None:
    forbidden_prefixes = ("modules.storage", "modules.orchestration")
    for path in _python_files("modules/adapters"):
        modules = _imported_modules(str(path.relative_to(REPO_ROOT)))
        assert not any(m.startswith(forbidden_prefixes) for m in modules), (
            f"{path} must translate broker models only, not persist or orchestrate"
        )


def test_modules_storage_does_not_depend_on_higher_layers() -> None:
    forbidden_prefixes = (
        "modules.brokers",
        "modules.adapters",
        "modules.orchestration",
    )
    for path in _python_files("modules/storage"):
        modules = _imported_modules(str(path.relative_to(REPO_ROOT)))
        assert not any(m.startswith(forbidden_prefixes) for m in modules), (
            f"{path} must stay persistence-only"
        )


def test_legacy_kis_package_is_removed() -> None:
    assert not (REPO_ROOT / "kis").exists(), (
        "top-level kis package was removed; import modules.brokers.kis directly"
    )
