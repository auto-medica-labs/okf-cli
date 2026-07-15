"""okf bundle command."""

from pathlib import Path

import typer

from okf import api


def bundle(
    input_dir: str = typer.Argument(
        ..., help="Source directory of plain markdown files"
    ),
    output_dir: str | None = typer.Argument(
        None,
        help="Output directory for the OKF bundle "
        "(default: <input-dir>_knowledge_base)",
    ),
    default_type: str = typer.Option(
        None, help="Type for root-level files (default: input directory name)"
    ),
    force: bool = typer.Option(
        False, "--force", "-f", help="Overwrite output directory if it exists"
    ),
    strict_links: bool = typer.Option(
        False,
        "--strict-links",
        help="Fail when local markdown links point outside bundle or missing targets",
    ),
) -> None:
    """Convert plain markdown into an OKF-conformant knowledge bundle."""
    try:
        result = api.bundle(
            input_dir,
            output_dir,
            default_type=default_type,
            force=force,
            strict_links=strict_links,
        )
    except FileNotFoundError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1)
    except FileExistsError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1)
    except ValueError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1)

    for w in result.warnings:
        typer.echo(f"Warning: {w}", err=True)
    for e in result.errors:
        typer.echo(f"Error: {e}", err=True)

    if result.errors:
        raise typer.Exit(code=1)

    n = result.files_written
    typer.echo(f"Done. Converted {n} file{'s' if n != 1 else ''} → {result.output_dir}")
