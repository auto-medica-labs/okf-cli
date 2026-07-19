"""okf read command."""

import typer

from okf import api
from okf.core import console, err_console


def cmd_read(
    directory: str = typer.Argument(..., help="Directory of the OKF bundle"),
    concept_id: str = typer.Argument(
        ..., help="Concept ID to read (e.g. tables/orders)"
    ),
) -> None:
    """Print a concept's full contents by its concept ID."""
    try:
        result = api.show_concept(directory, concept_id)
    except FileNotFoundError as e:
        err_console.print(f"Error: {e}", style="red")
        err_console.print(
            f"Run `okf list {directory}` to see available concept IDs.",
            style="yellow",
        )
        raise typer.Exit(code=1)
    except (ValueError, NotADirectoryError) as e:
        err_console.print(f"Error: {e}", style="red")
        raise typer.Exit(code=1)

    raw = result.raw
    if not raw.endswith("\n"):
        raw += "\n"
    console.print(raw, end="", markup=False, highlight=False)
