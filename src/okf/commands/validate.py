"""okf validate command."""

import typer

from okf import api


def validate(
    directory: str = typer.Argument(..., help="Directory to validate as an OKF bundle"),
) -> None:
    """Check whether a directory conforms to the OKF specification."""
    try:
        result = api.validate(directory)
    except NotADirectoryError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1)

    for w in result.warnings:
        typer.echo(f"Warning: {w}", err=True)
    for e in result.errors:
        typer.echo(f"Error: {e}", err=True)

    ok = result.total_files - len(result.errors)
    parts = [f"{result.total_files} files: {ok} ok"]
    if result.errors:
        parts.append(f"{len(result.errors)} errors")
    if result.warnings:
        parts.append(f"{len(result.warnings)} warnings")
    typer.echo("\n" + ", ".join(parts))

    if result.errors:
        raise typer.Exit(code=1)
