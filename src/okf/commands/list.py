"""okf list command."""

import typer

from okf import api
from okf.core import console, err_console


def cmd_list(
    directory: str = typer.Argument(..., help="Directory of the OKF bundle"),
) -> None:
    """List all concept IDs in an OKF bundle."""
    try:
        cids = api.list_concepts(directory)
    except (ValueError, NotADirectoryError) as e:
        err_console.print(f"Error: {e}", style="red")
        raise typer.Exit(code=1)

    if not cids:
        err_console.print("No concepts found", style="yellow")
        raise typer.Exit(code=1)

    for cid in cids:
        console.print(cid, style="cyan")
