"""`flask alerts` — generate today's alerts for a portfolio.

    flask alerts
    flask alerts --as-of 2025-01-27
    flask alerts --no-llm          # templates only, instant
    flask alerts --replay 2025-01-13:2025-02-14   # precompute a window

Precomputing a replay window matters for the demo: stepping through days
then reads stored rows instead of calling a model live.
"""
from __future__ import annotations

import click
import pandas as pd
from flask.cli import with_appcontext

from app.services import narrator, severity
from config import get_config

cfg = get_config()


def _one(day: str, portfolio_id: str, use_llm: bool) -> list[dict]:
    return severity.build(day, portfolio_id, use_llm=use_llm)


@click.command("alerts")
@click.option("--as-of", default=None)
@click.option("--portfolio", default=None, help="Portfolio id (default: demo).")
@click.option("--no-llm", is_flag=True, help="Skip the model, use templates.")
@click.option("--replay", default=None, help="START:END, precompute every session.")
@with_appcontext
def alerts_command(as_of, portfolio, no_llm, replay):
    """Build alerts, narrated by the local model."""
    portfolio = portfolio or cfg.DEMO_PORTFOLIO_ID
    use_llm = not no_llm

    if use_llm and not narrator.available():
        click.echo(f"  ! Ollama not reachable at {cfg.OLLAMA_URL}; using templates. "
                   f"Start it and `ollama pull {cfg.LLM_FAST}` for written alerts.")
        use_llm = False
    elif use_llm:
        click.echo(f"  narrator: {cfg.LLM_FAST} on this machine")

    days = [as_of or cfg.default_as_of()]
    if replay:
        start, _, end = replay.partition(":")
        days = [str(d.date()) for d in pd.bdate_range(start, end)]

    total, ungrounded, hows = 0, 0, {}
    for day in days:
        rows = _one(day, portfolio, use_llm)
        total += len(rows)
        for r in rows:
            hows[r["_how"]] = hows.get(r["_how"], 0) + 1
            if not r["grounded"]:
                ungrounded += 1
        if len(days) == 1:
            for r in rows:
                import json
                click.echo(f"\n  [{r['severity']}] {r['ticker']} · {r['category']}")
                click.echo(f"    {json.loads(r['text'])['title']}")
                click.echo(f"    {json.loads(r['text'])['why']}")
        else:
            click.echo(f"  {day}: {len(rows)} alerts")

    click.echo(f"\n  {total} alerts across {len(days)} day(s)")
    if hows:
        click.echo("  written by: " + ", ".join(f"{k} x{v}" for k, v in hows.items()))
    click.echo(f"  ungrounded (a number not in the facts): {ungrounded}")