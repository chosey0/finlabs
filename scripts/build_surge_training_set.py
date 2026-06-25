"""Collect move-independent random-control samples and reaction-label them.

This drives the negative side of the surge dataset: it draws seeded random
``(security, minute)`` anchors over a weekday calendar and runs the same news
discovery as the UI, tagged ``random_control`` so the samples are not conditioned
on a price move. Discovered samples are then reaction-labeled (beta-corrected,
standardized abnormal return) so they are ready for the human relevance gate.

Relevance annotation and dataset freeze stay in the labeling tool's
human-in-the-loop flow -- this script only builds and labels the candidate pool.

Requires live credentials (Kiwoom + Naver) and INTELLIGENCE_DATABASE_URL, so it is
run operationally rather than in tests:

    uv run python -m scripts.build_surge_training_set \
        --start 2026-05-01 --end 2026-05-31 \
        --securities-limit 50 --per-session 1 --seed 2026-05 --label-reactions
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
from collections.abc import Awaitable, Callable
from datetime import date

from modules.adapters.brokers.kiwoom.market_data import KiwoomMinuteMarketData
from modules.adapters.brokers.kiwoom.reaction_data import KiwoomReactionMarketData
from modules.adapters.news.naver import NaverNewsSearchAdapter
from modules.brokers.kiwoom.client import KiwoomClient
from modules.domain.news_intelligence import CatalogSnapshot
from modules.news.intelligence.processors.session_grid import weekday_trading_sessions
from modules.news.naver import NaverNewsClient
from modules.orchestration.news_intelligence import NewsIntelligenceServices
from modules.storage.news_intelligence.catalog import load_catalog_snapshot
from modules.storage.news_intelligence.database import load_env, resolve_dsn
from modules.storage.news_intelligence.writer import SingleWriter
from modules.storage.warehouse import data_dir


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build surge control samples")
    parser.add_argument("--start", type=date.fromisoformat, required=True)
    parser.add_argument("--end", type=date.fromisoformat, required=True)
    parser.add_argument("--securities-limit", type=int, default=50)
    parser.add_argument("--per-session", type=int, default=1)
    parser.add_argument("--seed", type=str, required=True)
    parser.add_argument(
        "--label-reactions",
        action="store_true",
        help="Reaction-label each discovered sample after collection",
    )
    return parser.parse_args(argv)


def _select_securities(
    catalog: CatalogSnapshot, *, limit: int, seed: str
) -> tuple[str, ...]:
    ids = sorted(security.security_id for security in catalog.securities)
    if limit <= 0 or limit >= len(ids):
        return tuple(ids)
    rng = random.Random(seed)
    return tuple(sorted(rng.sample(ids, limit)))


async def _build_services() -> tuple[
    NewsIntelligenceServices, Callable[[], Awaitable[None]]
]:
    load_env()
    dsn = resolve_dsn()
    kiwoom = KiwoomClient.from_env()
    await kiwoom.__aenter__()
    naver = NaverNewsClient(
        os.environ["NAVER_CLIENT_ID"], os.environ["NAVER_CLIENT_SECRET"]
    )
    writer = SingleWriter(dsn)
    services = NewsIntelligenceServices(
        catalog_snapshot=load_catalog_snapshot(dsn),
        market_data=KiwoomMinuteMarketData(kiwoom),
        news_search=NaverNewsSearchAdapter(naver),
        annotation_writer=writer,
        export_root=data_dir() / "news-intelligence-exports",
        reaction_data=KiwoomReactionMarketData(kiwoom),
    )

    async def _close() -> None:
        naver.close()
        writer.close()
        await kiwoom.__aexit__(None, None, None)

    return services, _close


async def _run(args: argparse.Namespace) -> int:
    services, close = await _build_services()
    try:
        securities = _select_securities(
            services.catalog_snapshot, limit=args.securities_limit, seed=args.seed
        )
        sessions = weekday_trading_sessions(args.start, args.end)
        collection = await services.collect_control_samples(
            securities=securities,
            sessions=sessions,
            seed=args.seed,
            per_session=args.per_session,
        )

        labeled = 0
        excluded = 0
        if args.label_reactions:
            for sample_id in collection.sample_ids:
                try:
                    result = await services.preview_reaction_for_sample(
                        sample_id=sample_id
                    )
                except Exception:  # noqa: BLE001 - one bad sample must not abort
                    excluded += 1
                    continue
                if result.preview.exclusion_reason is None:
                    labeled += 1
                else:
                    excluded += 1

        print(
            json.dumps(
                {
                    "securities": len(securities),
                    "sessions": len(sessions),
                    "planned": collection.planned,
                    "skipped": collection.skipped,
                    "discovered": len(collection.sample_ids),
                    "reaction_labeled": labeled,
                    "reaction_excluded": excluded,
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return 0
    finally:
        await close()


def main(argv: list[str] | None = None) -> int:
    return asyncio.run(_run(_parse_args(argv)))


if __name__ == "__main__":
    raise SystemExit(main())
