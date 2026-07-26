"""okf list command."""

from pathlib import Path

import typer
from rich.table import Table

from okf import api
from okf.core import console, err_console


def cmd_list(
    directory: str = typer.Argument(..., help="Directory of the OKF bundle"),
) -> None:
    """List concepts in a table with ID, type, title, and description."""
    try:
        entries = api.list_entries(directory)
    except (ValueError, NotADirectoryError) as e:
        err_console.print(f"Error: {e}", style="red")
        raise typer.Exit(code=1)

    if not entries:
        err_console.print("No concepts found", style="yellow")
        raise typer.Exit(code=1)

    table = Table(
        "ID",
        "Type",
        "Title",
        "Description",
        caption="Use the ID column with: okf read <bundle> <id>",
    )
    table.columns[0].no_wrap = True

    for e in entries:
        title = e["title"] if e["title"] else Path(e["id"]).stem
        table.add_row(e["id"], e["type"], title, e["description"])

    console.print(table)
