"""`flask llm` — check or set up the local model from the terminal."""
from __future__ import annotations

import time

import click
from flask.cli import with_appcontext

from app.services import llm_setup


@click.command("llm")
@click.option("--setup", is_flag=True, help="Start Ollama and download the model.")
@click.option("--model", default=None)
@with_appcontext
def llm_command(setup, model):
    """Show local model status, or set it up."""
    if setup:
        for step in llm_setup.ensure(model)["steps"]:
            click.echo(f"  {step.get('message')}")
        while llm_setup.status()["downloading"]:
            s = llm_setup.status()
            click.echo(f"\r  {s['stage']} {s['percent']}%", nl=False)
            time.sleep(1)
        click.echo("")
    s = llm_setup.status()
    click.echo(f"  {s['message']}")
    if s["installed_models"]:
        click.echo(f"  installed: {', '.join(s['installed_models'])}")