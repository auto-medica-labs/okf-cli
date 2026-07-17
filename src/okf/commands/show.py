"""okf show command."""

import urllib.error

import typer

from okf import api
from okf.remote import http_get, parse_ref, server_url


def cmd_show(
    directory: str | None = typer.Argument(None, help="Directory of the OKF bundle"),
    concept_id: str | None = typer.Argument(
        None, help="Concept ID to read (e.g. tables/orders)"
    ),
    remote: str | None = typer.Option(
        None, "--remote", help="Remote username/bundle or full URL"
    ),
    remote_concept_id: str | None = typer.Option(
        None, "--concept-id", help="Concept ID to read from a remote bundle"
    ),
    token: str | None = typer.Option(
        None, envvar="OKF_TOKEN", help="Optional API bearer token"
    ),
    url: str | None = typer.Option(None, "--url", help="Server URL (or OKF_URL env)"),
) -> None:
    """Print a concept's full contents by its concept ID."""
    if remote:
        if directory is not None:
            typer.echo("Error: directory not used with --remote", err=True)
            raise typer.Exit(code=1)
        cid = remote_concept_id or concept_id
        if not cid:
            typer.echo("Error: --concept-id required for remote show", err=True)
            raise typer.Exit(code=1)

        base_url = server_url(url)
        try:
            _base, username, bundle_name = parse_ref(remote, base_url)
        except ValueError as exc:
            typer.echo(f"Error: {exc}", err=True)
            raise typer.Exit(code=1) from exc

        concept_url = f"{base_url}/{username}/{bundle_name}/concepts/{cid}"
        try:
            raw = http_get(concept_url, token=token)
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            typer.echo(f"Error: {exc.code} {exc.reason}", err=True)
            if detail:
                typer.echo(detail, err=True)
            raise typer.Exit(code=1) from exc
        typer.echo(raw.decode("utf-8"), nl=False)
    else:
        if directory is None:
            typer.echo("Error: directory required when --remote is not used", err=True)
            raise typer.Exit(code=1)
        if concept_id is None:
            typer.echo("Error: CONCEPT_ID required", err=True)
            raise typer.Exit(code=1)
        try:
            result = api.show_concept(directory, concept_id)
        except (ValueError, FileNotFoundError, NotADirectoryError) as e:
            typer.echo(f"Error: {e}", err=True)
            raise typer.Exit(code=1)

        typer.echo(result.raw, nl=False)
