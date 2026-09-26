"""`flask build` — turn events into the evidence ledger and fingerprint.

    flask build                          # as of today
    flask build --as-of 2025-01-27       # as of a past day
    flask build --snapshots 2024-01-31,2024-07-31,2025-01-31
    flask build --placebo                # the honesty check

Rerunning is safe: evidence is rebuilt, and each fingerprint snapshot
replaces only its own as_of.
"""
from __future__ import annotations

import click
from flask.cli import with_appcontext

from app.models import evidence as evidence_model
from app.services import event_study
from config import get_config

cfg = get_config()


@click.command("build")
@click.option("--as-of", default=None, help="Date to build for (default: today).")
@click.option("--snapshots", default=None,
              help="Comma-separated extra dates, for the drift-over-time view.")
@click.option("--placebo", is_flag=True, help="Run the fake-event sanity check.")
@with_appcontext
def build_command(as_of, snapshots, placebo):
    """Build the evidence ledger and fingerprint."""
    as_of = as_of or cfg.default_as_of()

    click.echo(f"evidence, as of {as_of}")
    ev = event_study.build_evidence(
        as_of, progress=lambda i, n: click.echo(f"\r  {i}/{n} events", nl=False))
    click.echo("")
    if ev.empty:
        raise click.ClickException("No evidence rows. Did `flask ingest` run?")
    counts = evidence_model.counts()
    for r in counts.itertuples():
        click.echo(f"  {r.event_type:<10} {r.kept:>6} kept / {r.n:>6} measured")

    dates = [as_of] + [d.strip() for d in (snapshots or "").split(",") if d.strip()]
    for d in dates:
        fp = event_study.build_fingerprint(d)
        cells = 0 if fp.empty else len(fp[fp["direction"] == "all"])
        reliable = 0 if fp.empty else int(fp[fp["direction"] == "all"]["reliable"].sum())
        click.echo(f"fingerprint {d}: {cells} cells, {reliable} reliable")

    if placebo:
        click.echo("\nplacebo check (fake events should look ordinary):")
        for k, v in event_study.placebo(as_of).items():
            click.echo(f"  {k:<26} {v}")