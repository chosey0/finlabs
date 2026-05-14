from __future__ import annotations

from typing import Literal

Environment = Literal["real", "mock"]

Market = Literal["NAS", "NYS", "AMS", "HKS", "TSE", "SHS", "SZS"]

Interval = Literal["1d", "1w", "1m", "1y", "1min"]

OverseasExchange = Literal["NAS", "NYS", "AMS", "HKS", "TSE", "SHS", "SZS"]

HttpMethod = Literal["GET", "POST"]

CustType = Literal["P", "B"]

TrType = Literal["1", "2"]
