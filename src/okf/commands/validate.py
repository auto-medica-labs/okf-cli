"""okf validate command."""

import typer

from okf import api
from okf.core import console, err_console


def validate(
    directory: str = typer.Argument(..., help="Directory to validate as an OKF bundle"),
) -> None:
    """Check whether a directory conforms to the OKF specification."""
    try:
        result = api.validate(directory)
    except NotADirectoryError as e:
        err_console.print(f"Error: {e}", style="red")
        raise typer.Exit(code=1)

    for w in result.warnings:
        err_console.print(f"Warning: {w}", style="yellow")
    for e in result.errors:
        err_console.print(f"Error: {e}", style="red")

    ok = result.total_files - len(result.errors)
    parts = [f"{result.total_files} files: {ok} ok"]
    if result.errors:
        parts.append(f"{len(result.errors)} errors")
    if result.warnings:
        parts.append(f"{len(result.warnings)} warnings")
    summary_color = "green" if not result.errors else "red"
    console.print("\n" + ", ".join(parts), style=summary_color)

    if result.errors:
        raise typer.Exit(code=1)
