<!-- Parent: ../AGENTS.md -->

# tests

## Purpose

`pytest`-based unit and integration suite. Tests use mock transports and temporary
databases; they never call a real brokerage API or touch user data directories.

## Layout

| Directory | Ownership |
|-----------|-----------|
| `architecture/` | Cross-package dependency and transport-boundary guards |
| `brokers/kis/` | Pure KIS SDK surface, parser, facade, and realtime tests |
| `brokers/toss/` | Pure Toss SDK tests |
| `applications/finlabs_cli/` | FinLabs CLI account, auth, chart, and realtime command tests |
| `applications/dashboard/` | Dashboard transport and retry behavior |
| `research/fractal/` | Fractal research implementation tests |
| `research/tokenizers/` | Tokenizer research implementation tests |

Keep tests under the directory that owns the behavior. Only cross-package
architecture and integration tests belong directly under shared central areas.

## For AI Agents

### Working In This Directory

- Never call the real KIS or Toss APIs. Use `httpx.MockTransport`, mock objects,
  or `monkeypatch`.
- Isolate database tests with `tmp_path`; never touch the user data directory.
- Validate WebSocket behavior with injected frames and mock connections.
- Add endpoint registry checks to `brokers/kis/test_kis_package.py` and follow
  `brokers/kis/test_stage5_facades.py` for high-level KIS methods.
- `architecture/test_boundaries.py` enforces the layered architecture from
  [modules/AGENTS.md](../modules/AGENTS.md).
- Add a matching AST assertion whenever a new forbidden dependency edge is
  introduced.

### Testing Requirements

- Run: `uv run python -m pytest`
- Lint: `uv run ruff check .`
- Name tests `test_<behavior>`; async tests require the repository's configured
  async test support.

### Common Patterns

- Mock REST transport: `httpx.MockTransport(handler)`.
- DuckDB tests create a minimal temporary database under `tmp_path`.
- Prefer frozen dataclass equality assertions for result objects.
- Keep small response fixtures inline when that improves readability.

## Dependencies

### Internal

- `modules`: layered core and broker SDKs
- `finlabs_cli`: broker SDK operation CLI
- `dashboard`, `research`: application and experimental consumers

### External

- `pytest>=9.0.3`

<!-- MANUAL: Manually added notes below this line are preserved on regeneration -->
