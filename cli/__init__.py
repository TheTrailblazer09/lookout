"""Offline jobs, exposed as `flask <command>`."""
from cli.build import build_command
from cli.ingest import ingest_command
from cli.train import train_command
from cli.detect import detect_command
from cli.alerts import alerts_command
from cli.llm import llm_command


def register_commands(app):
    app.cli.add_command(ingest_command)
    app.cli.add_command(build_command)
    app.cli.add_command(train_command)
    app.cli.add_command(detect_command)
    app.cli.add_command(alerts_command)
    app.cli.add_command(llm_command)