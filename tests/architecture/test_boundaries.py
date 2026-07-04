"""Static checks that enforce the plan's architectural boundaries.

These are cheap text/import assertions, not behavioural tests, but they guard the
two structural invariants the design depends on:

- AC8: dashboard read pages must not import the FastAPI HTTP client.
- removed legacy app: runtime Python code must not import the deleted CLI package.
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


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


def _python_files(relative_dir: str) -> tuple[Path, ...]:
    return tuple(sorted((REPO_ROOT / relative_dir).rglob("*.py")))


def test_runtime_code_does_not_import_removed_cli_package() -> None:
    removed_package = "kis" + "_cli"
    for relative_dir in ("dashboard", "finlabs_cli", "modules", "research"):
        for path in _python_files(relative_dir):
            modules = _imported_modules(str(path.relative_to(REPO_ROOT)))
            assert not any(
                m == removed_package or m.startswith(f"{removed_package}.") for m in modules
            ), (
                f"{path} must not import the removed CLI package"
            )


def test_modules_broker_sdks_stay_standalone() -> None:
    assert not (REPO_ROOT / "brokers").exists(), (
        "broker SDK source now lives in the sibling broker-modules repository"
    )
    forbidden_prefixes = (
        "modules.adapters",
        "modules.orchestration",
        "modules.storage",
        "modules.domain",
    )
    for path in _python_files("brokers"):
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
        "brokers",
        "modules.adapters",
        "modules.orchestration",
    )
    for path in _python_files("modules/storage"):
        modules = _imported_modules(str(path.relative_to(REPO_ROOT)))
        assert not any(m.startswith(forbidden_prefixes) for m in modules), (
            f"{path} must stay persistence-only"
        )


def test_news_does_not_own_market_surge_extraction() -> None:
    assert not (REPO_ROOT / "modules/news/surge_events.py").exists()
    assert not (REPO_ROOT / "modules/news/schema/surge.py").exists()
    for path in _python_files("modules/news/db"):
        source = path.read_text(encoding="utf-8")
        assert "CREATE TABLE IF NOT EXISTS surge_events" not in source, (
            f"{path} must not persist market surge events in the news database"
        )


def test_legacy_kis_package_is_removed() -> None:
    assert not (REPO_ROOT / "kis").exists(), (
        "top-level kis package was removed; import brokers.kis directly"
    )


def test_news_intelligence_processors_are_io_free() -> None:
    forbidden_prefixes = (
        "duckdb",
        "psycopg",
        "fastapi",
        "httpx",
        "modules.adapters",
        "brokers",
        "modules.orchestration",
        "modules.storage",
        "pathlib",
    )
    for path in _python_files("modules/news/intelligence/processors"):
        modules = _imported_modules(str(path.relative_to(REPO_ROOT)))
        assert not any(module.startswith(forbidden_prefixes) for module in modules), (
            f"{path} must remain a pure processor without provider, I/O or storage imports"
        )
