"""`flask train` — train the drawdown risk model and score every day.

    flask train
    flask train --as-of 2025-01-27

Prints the honest scorecard: our model beside a simple baseline, on a test
year the model never saw. Save this output; it is the evaluation table.
"""
from __future__ import annotations

import json
from pathlib import Path

import click
from flask.cli import with_appcontext

from app.services import risk_model
from config import get_config

cfg = get_config()


@click.command("train")
@click.option("--as-of", default=None, help="Cut-off date (default: today).")
@click.option("--save", default="data/metrics.json", help="Where to write the scorecard.")
@with_appcontext
def train_command(as_of, save):
    """Train, evaluate against a baseline, and score every stock-day."""
    as_of = as_of or cfg.default_as_of()
    click.echo(f"training, data through {as_of}")
    try:
        m = risk_model.train_and_score(as_of)
    except RuntimeError as exc:
        raise click.ClickException(str(exc))

    click.echo(f"\n  test year: {m['test_from']} to {m['test_to']} "
               f"({m['test_rows']:,} stock-days, {m['base_rate']:.1%} of them risky)")
    click.echo(f"  {'metric':<22}{'model':>10}{'baseline':>12}")
    click.echo(f"  {'PR-AUC':<22}{m['pr_auc_model']:>10}{m['pr_auc_baseline']:>12}")
    click.echo(f"  {'Brier (lower better)':<22}{m['brier_model']:>10}{m['brier_baseline']:>12}")
    click.echo(f"  {'ROC-AUC':<22}{m['roc_auc_model']:>10}{'-':>12}")
    lo, hi = m["pr_auc_lift_ci95"]
    verdict = "beats the baseline" if m["beats_baseline"] else "ties the baseline"
    click.echo(f"\n  lift over baseline, 95% interval: [{lo}, {hi}] -> {verdict}")
    if not m["beats_baseline"]:
        click.echo("  (report this as it is; an honest tie beats an unverifiable claim)")
    click.echo(f"\n  scored {m['scored_rows']:,} stock-days")

    Path(save).parent.mkdir(parents=True, exist_ok=True)
    Path(save).write_text(json.dumps(m, indent=2))
    click.echo(f"  scorecard -> {save}")