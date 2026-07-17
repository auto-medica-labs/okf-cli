"""okf clone command."""

from __future__ import annotations

import os
import shutil
import tempfile
import urllib.error
from pathlib import Path

import typer

from okf.remote import extract_archive, http_get, parse_ref, server_url


def clone(
    ref: str = typer.Argument(..., help="username/bundle or full server URL"),
    local_dir: str | None = typer.Argument(
        None, help="Local directory to extract into (default: bundle name)"
    ),
    token: str | None = typer.Option(
        None, envvar="OKF_TOKEN", help="Optional API bearer token"
    ),
    url: str | None = typer.Option(None, "--url", help="Server URL (or OKF_URL env)"),
) -> None:
    """Download an OKF bundle from an okf-server."""
    base_url = server_url(url)
    try:
        _base, username, bundle_name = parse_ref(ref, base_url)
    except ValueError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    dest = Path(local_dir or bundle_name)
    if dest.exists() and (dest.is_file() or (dest.is_dir() and any(dest.iterdir()))):
        typer.echo(f"Error: destination '{dest}' already exists", err=True)
        raise typer.Exit(code=1)

    archive_url = f"{base_url}/{username}/{bundle_name}/archive"
    try:
        data = http_get(archive_url, token=token)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        typer.echo(f"Error: {exc.code} {exc.reason}", err=True)
        if detail:
            typer.echo(detail, err=True)
        raise typer.Exit(code=1) from exc

    fd, archive_path = tempfile.mkstemp(suffix=".tar.gz")
    os.close(fd)
    try:
        Path(archive_path).write_bytes(data)
        extract_archive(Path(archive_path), dest)
    finally:
        Path(archive_path).unlink(missing_ok=True)

    # The server archive wraps the bundle in a top-level directory.
    # Unwrap it so the destination contains the bundle contents directly.
    children = list(dest.iterdir())
    if len(children) == 1 and children[0].is_dir() and children[0].name == bundle_name:
        inner = children[0]
        for child in inner.iterdir():
            shutil.move(str(child), str(dest / child.name))
        inner.rmdir()

    typer.echo(f"Cloned into {dest}")
