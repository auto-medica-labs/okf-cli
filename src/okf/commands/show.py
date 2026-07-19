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
    except FileNotFoundError as e:
        typer.secho(f"Error: {e}", fg=typer.colors.RED, err=True)
        typer.secho(
            f"Run `okf list {directory}` to see available concept IDs.",
            fg=typer.colors.YELLOW,
            err=True,
        )
        raise typer.Exit(code=1)
    except (ValueError, NotADirectoryError) as e:
        typer.secho(f"Error: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    typer.echo(result.raw, nl=False)
