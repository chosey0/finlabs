"""Configured one-process Uvicorn runtime for the local intelligence app."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI

from finlabs_intelligence.api.app import app
from modules.adapters.brokers.kiwoom.market_data import KiwoomMinuteMarketData
from modules.adapters.brokers.kiwoom.reaction_data import KiwoomReactionMarketData
from modules.adapters.news.naver import NaverNewsSearchAdapter
from modules.brokers.kiwoom.client import KiwoomClient
from modules.news.naver import NaverNewsClient
from modules.orchestration.news_intelligence import NewsIntelligenceServices
from modules.storage.news_intelligence.catalog import load_catalog_snapshot
from modules.storage.news_intelligence.database import resolve_dsn
from modules.storage.news_intelligence.writer import SingleWriter
from modules.storage.warehouse import data_dir


@asynccontextmanager
async def lifespan(application: FastAPI):
    root = data_dir()
    dsn = resolve_dsn()
    kiwoom = KiwoomClient.from_env()
    await kiwoom.__aenter__()
    naver = NaverNewsClient(
        os.environ["NAVER_CLIENT_ID"],
        os.environ["NAVER_CLIENT_SECRET"],
    )
    writer = SingleWriter(dsn)
    application.state.news_intelligence_services = NewsIntelligenceServices(
        catalog_snapshot=load_catalog_snapshot(dsn),
        market_data=KiwoomMinuteMarketData(kiwoom),
        news_search=NaverNewsSearchAdapter(naver),
        annotation_writer=writer,
        export_root=root / "news-intelligence-exports",
        reaction_data=KiwoomReactionMarketData(kiwoom),
    )
    try:
        yield
    finally:
        naver.close()
        writer.close()
        await kiwoom.__aexit__(None, None, None)


app.router.lifespan_context = lifespan
