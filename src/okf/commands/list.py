"""okf list command."""

import typer

from okf import api


def cmd_list(
    directory: str = typer.Argument(..., help="Directory of the OKF bundle"),
) -> None:
    """List all concept IDs in an OKF bundle."""
    try:
        cids = api.list_concepts(directory)
    except (ValueError, NotADirectoryError) as e:
        typer.secho(f"Error: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    if not cids:
        typer.secho("No concepts found", fg=typer.colors.YELLOW, err=True)
        raise typer.Exit(code=1)

    for cid in cids:
        typer.secho(cid, fg=typer.colors.CYAN)
