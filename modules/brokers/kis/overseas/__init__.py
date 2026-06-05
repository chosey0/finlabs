"""Overseas high-level REST APIs.

`_OverseasNamespace` is accessed as `KisClient.overseas`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from modules.brokers.kis.overseas.analysis import OverseasAnalysisAPI
from modules.brokers.kis.overseas.chart import OverseasChartAPI
from modules.brokers.kis.overseas.price import OverseasPriceAPI

if TYPE_CHECKING:
    from modules.brokers.kis.client import KisClient


class _OverseasNamespace:
    def __init__(self, parent: "KisClient") -> None:
        self._parent = parent
        self.price = OverseasPriceAPI(parent)
        self.chart = OverseasChartAPI(parent)
        self.analysis = OverseasAnalysisAPI(parent)
