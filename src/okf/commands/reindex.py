"""okf reindex command."""

import typer

from okf import api
from okf.core import console, err_console


def cmd_reindex(
    directory: str = typer.Argument(..., help="Directory of the OKF bundle"),
) -> None:
    """Rebuild every index.md in a bundle from the concepts on disk."""
    try:
        result = api.reindex(directory)
    except (ValueError, NotADirectoryError) as e:
        err_console.print(f"Error: {e}", style="red")
        raise typer.Exit(code=1)

    n = result.files_written
    console.print(
        f"Done. Wrote {n} index file{'s' if n != 1 else ''} → {result.output_dir}",
        style="green",
    )
