"""Domestic (KRX/NXT) high-level REST APIs.

`_DomesticNamespace` is accessed as `KisClient.domestic`. Each attribute
(`price`, `chart`, ...) is a lightweight client built around a single
endpoint family.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from kis.domestic.analysis import DomesticAnalysisAPI
from kis.domestic.chart import DomesticChartAPI
from kis.domestic.price import DomesticPriceAPI
from kis.domestic.rank import DomesticRankAPI
from kis.domestic.symbols import DomesticSymbolsAPI

if TYPE_CHECKING:
    from kis.client import KisClient


class _DomesticNamespace:
    def __init__(self, parent: "KisClient") -> None:
        self._parent = parent
        self.price = DomesticPriceAPI(parent)
        self.chart = DomesticChartAPI(parent)
        self.symbols = DomesticSymbolsAPI(parent)
        self.rank = DomesticRankAPI(parent)
        self.analysis = DomesticAnalysisAPI(parent)
