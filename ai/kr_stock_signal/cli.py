from __future__ import annotations

import argparse
from pathlib import Path

from .ingestion import NewsIngestionService, NewsProvider
from .models import NewsItem
from .openai_news import OpenAINewsProvider
from .repository import KrStockRepository
from .watchlist import require_watchlist_symbol


class SampleNewsProvider(NewsProvider):
    def fetch_news_items(self, symbol: str) -> list[NewsItem]:
        watch = require_watchlist_symbol(symbol)
        return [
            NewsItem(
                symbol=watch.symbol,
                title=f"{watch.name_ko} 반도체 수요 개선 기대",
                summary_ko=f"{watch.name_ko} 관련 수요 개선 기대가 언급됐지만 실제 주가 판단에는 가격 지표와 함께 보조적으로만 사용해야 합니다.",
                sentiment_score=1,
                impact_score=2,
                relevance_score=3,
                source="sample",
                url="",
                published_at=None,
                risk_tags=("sector",),
                model="sample",
            )
        ]


def main() -> int:
    parser = argparse.ArgumentParser(description="Collect, summarize, and score Korean stock news.")
    parser.add_argument("symbol", help="Watchlist symbol or Korean name. Example: 삼성전자, 005930.KS")
    parser.add_argument("--db", default="data/kr_stock_news.db", help="SQLite DB path.")
    parser.add_argument("--provider", choices=("openai", "sample"), default="openai", help="News provider.")
    parser.add_argument("--score-date", default=None, help="Score date in YYYY-MM-DD. Defaults to today.")
    args = parser.parse_args()

    repo = KrStockRepository(Path(args.db))
    repo.initialize()
    provider: NewsProvider = OpenAINewsProvider() if args.provider == "openai" else SampleNewsProvider()
    result = NewsIngestionService(repo, provider).ingest_symbol(args.symbol, score_date=args.score_date)
    score = result.daily_score

    print(f"[{result.score_date}] {result.symbol} news analysis")
    print(f"- collected_items: {result.item_count}")
    print(f"- scored_items: {score.item_count}")
    print(f"- weighted_score: {score.weighted_score}")
    print(f"- positive_count: {score.positive_count}")
    print(f"- negative_count: {score.negative_count}")
    print(f"- high_impact_count: {score.high_impact_count}")
    print(f"- negative_shock_count: {score.negative_shock_count}")
    if score.risk_tags:
        print(f"- risk_tags: {', '.join(score.risk_tags)}")
    if score.top_summaries:
        print("- top_summaries:")
        for summary in score.top_summaries:
            print(f"  - {summary}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
