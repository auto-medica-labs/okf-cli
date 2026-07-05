"""okf show command."""

from pathlib import Path

import typer

from okf.core import SPEC_RESERVED, check_conformance


def cmd_show(
    directory: str = typer.Argument(..., help="Directory of the OKF bundle"),
    concept_id: str = typer.Argument(
        ..., help="Concept ID to read (e.g. tables/orders)"
    ),
) -> None:
    """Print a concept's full contents by its concept ID."""
    dir_path = Path(directory)

    if not dir_path.is_dir():
        typer.echo(f"Error: '{directory}' is not a directory", err=True)
        raise typer.Exit(code=1)

    errors, _warnings = check_conformance(dir_path)
    if errors:
        for e in errors:
            typer.echo(f"Error: {e}", err=True)
        typer.echo("\nDirectory is not an OKF-conformant bundle", err=True)
        raise typer.Exit(code=1)

    concept_path = dir_path / f"{concept_id}.md"

    # Guard path traversal
    try:
        concept_path.resolve().relative_to(dir_path.resolve())
    except ValueError:
        typer.echo(f"Error: '{concept_id}' is outside the bundle directory", err=True)
        raise typer.Exit(code=1)

    if concept_path.name.lower() in SPEC_RESERVED:
        typer.echo(
            f"Error: '{concept_id}' is a reserved filename, not a concept",
            err=True,
        )
        raise typer.Exit(code=1)

    if not concept_path.is_file():
        typer.echo(
            f"Error: concept '{concept_id}' not found (tried {concept_path})",
            err=True,
        )
        raise typer.Exit(code=1)

    typer.echo(concept_path.read_text(encoding="utf-8"), nl=False)
