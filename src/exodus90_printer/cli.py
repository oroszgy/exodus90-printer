"""Command-line interface for exodus90-printer."""

from __future__ import annotations

import functools
from collections.abc import Callable
from datetime import date
from pathlib import Path

import typer

from exodus90_printer.auth import request_otp, verify_otp
from exodus90_printer.client import ExodusClient
from exodus90_printer.config import OutputFormat, Settings, load_settings
from exodus90_printer.discovery import discover_printer_uri, discover_printers
from exodus90_printer.exceptions import ExodusError
from exodus90_printer.render import render
from exodus90_printer.render.markdown import render_markdown
from exodus90_printer.scraper import (
    discover_program_id,
    fetch_days,
    fetch_reading_for_date,
    find_day,
)
from exodus90_printer.web import run_server

app = typer.Typer(
    name="exodus90",
    help="Fetch and print the daily readings from the Exodus 90 app.",
    no_args_is_help=True,
)

ALL_FORMATS = {"markdown", "pdf", "print"}


def _handle_errors[F: Callable[..., object]](fn: F) -> F:
    @functools.wraps(fn)
    def wrapper(*args: object, **kwargs: object) -> object:
        try:
            return fn(*args, **kwargs)
        except ExodusError as exc:
            typer.echo(f"Error: {exc}", err=True)
            raise typer.Exit(1) from exc

    return wrapper  # type: ignore[return-value]


def _resolve_program_id(client: ExodusClient, settings: Settings) -> int:
    """Return the configured program id, or discover the current one."""
    return settings.program_id if settings.program_id is not None else discover_program_id(client)


def _parse_date(value: str | None) -> date:
    if value is None:
        return date.today()
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise typer.BadParameter(f"Invalid date '{value}'; expected YYYY-MM-DD.") from exc


def _parse_formats(value: list[str] | None) -> list[OutputFormat]:
    if value is None:
        return value  # type: ignore[return-value]
    unknown = set(value) - ALL_FORMATS
    if unknown:
        raise typer.BadParameter(
            f"Unknown format(s): {', '.join(sorted(unknown))}. "
            f"Choose from: {', '.join(sorted(ALL_FORMATS))}."
        )
    return value  # type: ignore[return-value]


@app.command()
@_handle_errors
def login(
    email: str = typer.Option(..., prompt="Email address", help="Exodus 90 account email address."),
    code: str | None = typer.Option(
        None, "--code", help="6-digit verification code (skip to be prompted)."
    ),
    config: Path | None = typer.Option(None, "--config", help="Path to the config TOML file."),
) -> None:
    """Log in and persist the session cookie."""
    settings = load_settings(config)
    with ExodusClient(settings) as client:
        if client.is_authenticated():
            typer.echo("Already authenticated.")
            return
        typer.echo("Requesting a verification code…")
        code_form = request_otp(client, email)
        if code is None:
            code = typer.prompt("Enter the 6-digit code")
        verify_otp(client, code_form, code)
        client.save_session()
    typer.echo(f"Authenticated. Session saved to {settings.session_path}")


@app.command()
@_handle_errors
def auth(
    config: Path | None = typer.Option(None, "--config", help="Path to the config TOML file."),
) -> None:
    """Check whether the persisted session is still valid."""
    settings = load_settings(config)
    with ExodusClient(settings) as client:
        if not client.is_authenticated():
            typer.echo("Not authenticated.", err=True)
            raise typer.Exit(1)
    typer.echo("Authenticated.")


@app.command()
@_handle_errors
def printers() -> None:
    """List network printers discovered via mDNS/DNS-SD (ippfind)."""
    found = discover_printers()
    if not found:
        typer.echo("No network printers discovered (is avahi-daemon/ippfind running?).")
        raise typer.Exit(1)
    for printer in found:
        typer.echo(f"{printer.host}\t{printer.uri}")


@app.command("discover")
@_handle_errors
def discover() -> None:
    """Print one ready-to-use IPP URI for a discovered network printer."""
    uri = discover_printer_uri()
    if uri is None:
        typer.echo("No network printer discovered.", err=True)
        raise typer.Exit(1)
    typer.echo(uri)


@app.command()
@_handle_errors
def status(
    config: Path | None = typer.Option(None, "--config", help="Path to the config TOML file."),
) -> None:
    """Check authentication and whether today has a reading."""
    settings = load_settings(config)
    with ExodusClient(settings) as client:
        if not client.is_authenticated():
            typer.echo("Not authenticated. Run `exodus90 login`.", err=True)
            raise typer.Exit(1)
        days = fetch_days(client, _resolve_program_id(client, settings))
        today = date.today()
        try:
            day = find_day(days, today)
        except ExodusError:
            typer.echo(f"Authenticated. No program has a reading for today ({today.isoformat()}).")
            raise typer.Exit(1) from None
        typer.echo(
            f"Authenticated. Today's reading ({today.isoformat()}): {day.title}"
            + (f" — {day.scripture}" if day.scripture else "")
        )


@app.command()
@_handle_errors
def fetch(
    target_date: str | None = typer.Option(
        None, "--date", help="Reading date (YYYY-MM-DD); default: today."
    ),
    config: Path | None = typer.Option(None, "--config", help="Path to the config TOML file."),
) -> None:
    """Fetch a reading and print it as markdown to stdout."""
    settings = load_settings(config)
    requested = _parse_date(target_date)
    with ExodusClient(settings) as client:
        reading = fetch_reading_for_date(client, _resolve_program_id(client, settings), requested)
    typer.echo(render_markdown(reading))


@app.command("print")
@_handle_errors
def print_reading(
    target_date: str | None = typer.Option(
        None, "--date", help="Reading date (YYYY-MM-DD); default: today."
    ),
    formats: list[str] | None = typer.Option(
        None,
        "--format",
        help="Output format; repeatable: markdown, pdf, print. Defaults to config.",
    ),
    config: Path | None = typer.Option(None, "--config", help="Path to the config TOML file."),
) -> None:
    """Fetch today's reading and render it (cron-safe, no prompts)."""
    settings = load_settings(config)
    requested = _parse_date(target_date)
    output_formats = _parse_formats(formats) or settings.formats
    with ExodusClient(settings) as client:
        reading = fetch_reading_for_date(client, _resolve_program_id(client, settings), requested)
    outputs = render(reading, settings, output_formats)
    for output_format, path in outputs.items():
        typer.echo(f"{output_format}: {path}")


@app.command()
@_handle_errors
def web(
    host: str = typer.Option("0.0.0.0", help="Address to bind."),
    port: int = typer.Option(8099, help="Port to serve on."),
    email: str | None = typer.Option(None, help="Prefill the login form with this email."),
    config: Path | None = typer.Option(None, "--config", help="Path to the config TOML file."),
) -> None:
    """Serve the Web UI (used by the Home Assistant app)."""
    settings = load_settings(config)
    run_server(settings, host=host, port=port, prefill_email=email or "")


@app.command()
@_handle_errors
def days(
    config: Path | None = typer.Option(None, "--config", help="Path to the config TOML file."),
) -> None:
    """List the days of the configured program."""
    settings = load_settings(config)
    with ExodusClient(settings) as client:
        for day in fetch_days(client, _resolve_program_id(client, settings)):
            ref = f" ({day.scripture})" if day.scripture else ""
            typer.echo(f"{day.date.isoformat()}  {day.title}{ref}")


if __name__ == "__main__":
    app()
