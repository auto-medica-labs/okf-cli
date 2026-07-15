"""okf show command."""

import typer

from okf import api


def cmd_show(
    directory: str = typer.Argument(..., help="Directory of the OKF bundle"),
    concept_id: str = typer.Argument(
        ..., help="Concept ID to read (e.g. tables/orders)"
    ),
) -> None:
    """Print a concept's full contents by its concept ID."""
    try:
        result = api.show_concept(directory, concept_id)
    except (ValueError, FileNotFoundError, NotADirectoryError) as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1)

    typer.echo(result.raw, nl=False)
