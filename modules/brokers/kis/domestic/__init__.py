"""Domestic high-level REST APIs accessed through ``KisClient.domestic``."""

from __future__ import annotations

from typing import TYPE_CHECKING

from modules.brokers.kis.domestic.chart import DomesticChartAPI

if TYPE_CHECKING:
    from modules.brokers.kis.client import KisClient


class _DomesticNamespace:
    def __init__(self, parent: "KisClient") -> None:
        self._parent = parent
        self.chart = DomesticChartAPI(parent)
