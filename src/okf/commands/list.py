"""okf list command."""

import urllib.error

import typer

from okf import api
from okf.remote import http_get, parse_ref, server_url


def cmd_list(
    directory: str | None = typer.Argument(None, help="Directory of the OKF bundle"),
    remote: str | None = typer.Option(
        None, "--remote", help="Remote username/bundle or full URL"
    ),
    token: str | None = typer.Option(
        None, envvar="OKF_TOKEN", help="Optional API bearer token"
    ),
    url: str | None = typer.Option(None, "--url", help="Server URL (or OKF_URL env)"),
) -> None:
    """List all concept IDs in a local or remote OKF bundle."""
    if remote:
        base_url = server_url(url)
        try:
            _base, username, bundle_name = parse_ref(remote, base_url)
        except ValueError as exc:
            typer.echo(f"Error: {exc}", err=True)
            raise typer.Exit(code=1) from exc

        concepts_url = f"{base_url}/{username}/{bundle_name}/concepts"
        try:
            data = http_get(concepts_url, token=token)
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            typer.echo(f"Error: {exc.code} {exc.reason}", err=True)
            if detail:
                typer.echo(detail, err=True)
            raise typer.Exit(code=1) from exc

        import json

        try:
            cids = json.loads(data)
        except json.JSONDecodeError as exc:
            typer.echo("Error: invalid response from server", err=True)
            raise typer.Exit(code=1) from exc
    else:
        if directory is None:
            typer.echo("Error: directory required when --remote is not used", err=True)
            raise typer.Exit(code=1)
        try:
            cids = api.list_concepts(directory)
        except (ValueError, NotADirectoryError) as e:
            typer.echo(f"Error: {e}", err=True)
            raise typer.Exit(code=1)

    if not cids:
        typer.echo("No concepts found", err=True)
        raise typer.Exit(code=1)

    for cid in cids:
        typer.echo(cid)
