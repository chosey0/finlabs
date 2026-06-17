from __future__ import annotations

from typing import Literal

Environment = Literal["real", "mock", "dev"]

HttpMethod = Literal["GET", "POST"]

ChartInterval = Literal["tick", "1min", "1d", "1w", "1mo", "1y"]
