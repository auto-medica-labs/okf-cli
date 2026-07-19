"""okf list command."""

from pathlib import Path

import typer
from rich.text import Text

from okf import api
from okf.core import console, err_console


def cmd_list(
    directory: str = typer.Argument(..., help="Directory of the OKF bundle"),
) -> None:
    """List concepts with title, description, and concept ID."""
    try:
        entries = api.list_entries(directory)
    except (ValueError, NotADirectoryError) as e:
        err_console.print(f"Error: {e}", style="red")
        raise typer.Exit(code=1)

    if not entries:
        err_console.print("No concepts found", style="yellow")
        raise typer.Exit(code=1)

    console.print(
        Text(
            "  Concept ID in parentheses — use with: okf read <bundle> <id>",
            style="dim italic",
        )
    )
    console.print()

    for e in entries:
        title = e["title"] if e["title"] else Path(e["id"]).stem
        desc = e["description"]

        line = Text()
        line.append(title, style="bold")
        if desc:
            line.append(f": {desc}")
        line.append(f" ({e['id']})", style="dim")
        console.print(line)
