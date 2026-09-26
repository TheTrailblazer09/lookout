"""`flask detect` — run the bots that watch for new events.

    flask detect                    # technical + news, last 30 days
    flask detect --news-fetch       # also pull fresh articles first
    flask detect --days 120         # wider backfill

Earnings and macro events arrive through `flask ingest`; this command adds
the two bots that derive events from data we already hold (technical) or
from the news feed (news).
"""
from __future__ import annotations

from pathlib import Path

import click
from flask.cli import with_appcontext

from app.models import event as event_model
from app.models import portfolio as portfolio_model
from app.services.bots import news as news_bot
from app.services.bots import technical as technical_bot
from app.services.sources import news as news_source
from config import get_config

cfg = get_config()


@click.command("detect")
@click.option("--as-of", default=None)
@click.option("--days", default=30, help="How far back to scan.")
@click.option("--news-fetch", is_flag=True, help="Pull fresh articles from Alpha Vantage.")
@click.option("--news-tickers", default=None, help="Which tickers to fetch news for.")
@click.option("--no-finbert", is_flag=True, help="Skip local sentiment, use vendor scores.")
@with_appcontext
def detect_command(as_of, days, news_fetch, news_tickers, no_finbert):
    """Run the technical and news bots."""
    as_of = as_of or cfg.default_as_of()

    click.echo(f"technical bot, last {days} sessions to {as_of}")
    n = technical_bot.run(as_of, lookback_days=days)
    click.echo(f"  {n} technical events")

    if news_fetch:
        if not cfg.ALPHAVANTAGE_KEY:
            click.echo("  ! ALPHAVANTAGE_KEY not set; skipping the fetch. "
                       "Free key: alphavantage.co/support/#api-key")
        else:
            tickers = ([t.strip().upper() for t in news_tickers.split(",")]
                       if news_tickers
                       else portfolio_model.get_holdings(cfg.DEMO_PORTFOLIO_ID)["ticker"].tolist()
                       or cfg.UNIVERSE[:5])
            click.echo(f"news fetch: {len(tickers)} tickers "
                       "(free tier is ~25 requests/day; responses are cached)")
            feed = news_source.fetch_raw(cfg.ALPHAVANTAGE_KEY, tickers,
                                         Path(cfg.NEWS_CACHE_DIR))
            articles, mentions = news_source.to_frames(feed)
            click.echo(f"  {len(articles)} articles, {len(mentions)} ticker mentions")
            if not articles.empty:
                # Alpha Vantage returns every ticker mentioned in an article,
                # including ones we do not hold; those add tens of thousands of
                # rows and nothing to the demo.
                if not mentions.empty:
                    mentions = mentions[mentions["ticker"].isin(tickers)]
                    keep = set(mentions["article_id"])
                    articles = articles[articles["id"].isin(keep)]
                    click.echo(f"  kept {len(articles)} articles mentioning your "
                               f"tickers ({len(mentions)} mentions)")

                def _score_tick(done, total):
                    click.echo(f"\r  scoring {done:,}/{total:,}", nl=False)

                scores = news_bot.score(articles, mentions,
                                        use_finbert=not no_finbert,
                                        progress=_score_tick)
                click.echo("")
                stored = news_bot.store(articles, scores)
                click.echo(f"  stored {stored['articles']} articles, "
                           f"{stored['scores']} scores, {stored['mood_days']} mood-days")
                if not scores.empty:
                    click.echo(f"  scorer: {scores['model_version'].iloc[0]}")

    click.echo("news bot")
    n = news_bot.run(as_of, lookback_days=days)
    click.echo(f"  {n} news events")

    click.echo("\nevents by type:")
    for r in event_model.counts_by_type().itertuples():
        click.echo(f"  {r.type:<12}{r.n:>7}   {r.first} to {r.last}")