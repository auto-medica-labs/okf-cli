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
        typer.secho(f"Error: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    for w in result.warnings:
        typer.secho(f"Warning: {w}", fg=typer.colors.YELLOW, err=True)
    for e in result.errors:
        typer.secho(f"Error: {e}", fg=typer.colors.RED, err=True)

    ok = result.total_files - len(result.errors)
    parts = [f"{result.total_files} files: {ok} ok"]
    if result.errors:
        parts.append(f"{len(result.errors)} errors")
    if result.warnings:
        parts.append(f"{len(result.warnings)} warnings")
    summary_color = typer.colors.GREEN if not result.errors else typer.colors.RED
    typer.secho("\n" + ", ".join(parts), fg=summary_color)

    if result.errors:
        raise typer.Exit(code=1)
