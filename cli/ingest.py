"""`flask ingest` — pull real market data.

    flask ingest                       # prices + earnings, 2019 to today
    flask ingest --start 2018-01-01
    flask ingest --skip-macro          # if you have no FRED key yet
    flask ingest --tickers NVDA,AAPL   # a quick subset while developing

Everything downstream reads the tables this writes; nothing else in the app
knows where the data came from.
"""
from __future__ import annotations

import datetime as dt

import click
import pandas as pd
from flask.cli import with_appcontext

from app.models import event as event_model
from app.models import fundamental as fundamental_model
from app.models import indicator as indicator_model
from app.models.base import insert_df, query, truncate
from app.services.sources import macro as macro_source
from app.services.sources import market as market_source
from config import get_config

cfg = get_config()


def _sessions() -> list:
    """Trading dates we actually have prices for, as datetime.date."""
    df = query(f"SELECT DISTINCT date FROM prices WHERE ticker = '{cfg.MARKET_TICKER}' ORDER BY date")
    return [market_source.to_date(d) for d in df["date"].tolist()]


def _available(universe: list[str]) -> list[str]:
    """Tickers that actually landed in the price table. Yahoo silently drops
    some symbols (renamed, delisted, or class-share quirks); asking for
    earnings on those just wastes rate limit."""
    got = set(query("SELECT DISTINCT ticker FROM prices")["ticker"].tolist())
    missing = [t for t in universe if t not in got]
    if missing:
        click.echo(f"  ! no prices for: {', '.join(missing)} (skipping them)")
    return [t for t in universe if t in got]


@click.command("ingest")
@click.option("--start", default="2019-01-01", help="First date to pull.")
@click.option("--end", default=None, help="Last date (default: today).")
@click.option("--tickers", default=None, help="Comma-separated override of the universe.")
@click.option("--skip-prices", is_flag=True)
@click.option("--skip-earnings", is_flag=True)
@click.option("--skip-macro", is_flag=True)
@click.option("--skip-fundamentals", is_flag=True)
@with_appcontext
def ingest_command(start, end, tickers, skip_prices, skip_earnings, skip_macro,
                   skip_fundamentals):
    """Fetch real prices, earnings and macro releases."""
    universe = [t.strip().upper() for t in tickers.split(",")] if tickers else list(cfg.UNIVERSE)
    end = end or str(dt.date.today())

    if not skip_prices:
        click.echo(f"prices: {len(universe)} tickers + {cfg.MARKET_TICKER}, {start} to {end}")
        px = market_source.fetch_prices(universe + [cfg.MARKET_TICKER], start, end)
        truncate("prices")
        n = insert_df("prices", px)
        span = f"{px['date'].min()} to {px['date'].max()}"
        click.echo(f"  {n:,} rows, {span}")

    sessions = _sessions()
    if not sessions:
        raise click.ClickException("No prices in the database; run without --skip-prices first.")

    if not skip_earnings:
        universe = _available(universe)
        click.echo(f"earnings: {len(universe)} tickers, slow (Yahoo rate-limits per ticker)")
        def _tick(i, total, ticker):
            click.echo(f"\r  [{i:>3}/{total}] {ticker:<6}", nl=False)
        ev = market_source.fetch_earnings(universe, sessions, progress=_tick)
        click.echo("")
        n = event_model.upsert(ev)
        click.echo(f"  {n:,} earnings events")

    if not skip_macro:
        key = (cfg.FRED_KEY or "").strip()
        if not key:
            click.echo("  ! FRED_KEY not set, skipping macro. "
                       "Free key: https://fredaccount.stlouisfed.org/apikeys")
        elif not (len(key) == 32 and key.islower() and key.isalnum()):
            click.echo(f"  ! FRED_KEY looks wrong (got {len(key)} chars; FRED keys are "
                       "32 lower-case letters/digits). Skipping macro.")
        else:
            click.echo("macro: FRED releases (using first-publication dates)")
            inds = macro_source.fetch_indicators(cfg.FRED_KEY, start)
            rows = []
            for sid, df in inds.items():
                click.echo(f"  {sid:<12} {len(df):>5} observations")
                label = macro_source.SERIES[sid][1]
                for r in df.itertuples():
                    rows.append({"series_id": sid, "label": label, "date": r.date,
                                 "known_at": r.published, "value": float(r.value)})
            if rows:
                import pandas as pd
                n = indicator_model.replace(pd.DataFrame(rows))
                click.echo(f"  stored {n:,} indicator readings")
            ev = macro_source.to_events(inds, sessions)
            n = event_model.upsert(ev)
            click.echo(f"  {n:,} macro events")

    if not skip_fundamentals:
        held = _available(universe)
        click.echo(f"company facts: {len(held)} tickers")

        def _tick(i, total, ticker):
            click.echo(f"\r  [{i:>3}/{total}] {ticker:<6}", nl=False)

        rows = market_source.fetch_fundamentals(held, progress=_tick)
        click.echo("")
        click.echo(f"  stored {fundamental_model.replace(rows)} company profiles")

    click.echo("\nevents by type:")
    counts = event_model.counts_by_type()
    if counts.empty:
        click.echo("  (none yet)")
    else:
        for r in counts.itertuples():
            click.echo(f"  {r.type:<10} {r.n:>5}   {r.first} to {r.last}")
    click.echo(f"\nlatest session: {sessions[-1]}")