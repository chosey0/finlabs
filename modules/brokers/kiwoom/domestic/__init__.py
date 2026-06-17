"""Domestic high-level REST APIs accessed through ``KiwoomClient.domestic``."""

from __future__ import annotations

from typing import TYPE_CHECKING

from modules.brokers.kiwoom.domestic.chart import DomesticChartAPI

if TYPE_CHECKING:
    from modules.brokers.kiwoom.client import KiwoomClient


class _DomesticNamespace:
    def __init__(self, parent: "KiwoomClient") -> None:
        self.chart = DomesticChartAPI(parent)


__all__ = ["DomesticChartAPI"]
