"""okf publish command."""

from __future__ import annotations

import json
import urllib.error
from pathlib import Path
from urllib.parse import urlencode

import typer

from okf.remote import http_post, server_url, tar_directory
from okf.server._common import validate_slug


def publish(
    bundle_dir: str = typer.Argument(..., help="Local OKF bundle directory to publish"),
    name: str | None = typer.Argument(
        None, help="Bundle name on the server (default: directory name)"
    ),
    token: str = typer.Option(
        ..., envvar="OKF_TOKEN", help="API bearer token (or OKF_TOKEN env)"
    ),
    url: str | None = typer.Option(None, "--url", help="Server URL (or OKF_URL env)"),
    force: bool = typer.Option(
        False, "--force", "-f", help="Overwrite an existing bundle"
    ),
) -> None:
    """Publish a local OKF bundle to an okf-server."""
    src = Path(bundle_dir)
    if not src.is_dir():
        typer.echo(f"Error: '{src}' is not a directory", err=True)
        raise typer.Exit(code=1)

    bundle_name = name or src.name
    try:
        validate_slug(bundle_name)
    except ValueError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1)

    base_url = server_url(url)
    query = "?" + urlencode({"force": "true"}) if force else ""
    publish_url = f"{base_url}/api/v1/bundles/{bundle_name}{query}"

    archive = tar_directory(src)
    try:
        data = archive.read_bytes()
        body = http_post(
            publish_url,
            files={"bundle": (f"{bundle_name}.tar.gz", data)},
            token=token,
        )
    except urllib.error.HTTPError as exc:  # type: ignore[name-defined]
        detail = exc.read().decode("utf-8", errors="replace")
        typer.echo(f"Error: {exc.code} {exc.reason}", err=True)
        if detail:
            typer.echo(detail, err=True)
        raise typer.Exit(code=1) from exc
    finally:
        archive.unlink(missing_ok=True)

    try:
        result = json.loads(body)
    except json.JSONDecodeError:
        result = {}

    username = result.get("username", "")
    published_name = result.get("name", bundle_name)
    published_url = (
        f"{base_url}/{username}/{published_name}" if username else publish_url
    )
    typer.echo(f"Published {published_url}")
