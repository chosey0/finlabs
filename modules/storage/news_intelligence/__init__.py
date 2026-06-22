"""DuckDB persistence primitives for news-intelligence workflows."""

from .schema import initialize_schema
from .writer import SingleWriter

__all__ = ["SingleWriter", "initialize_schema"]
