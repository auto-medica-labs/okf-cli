"""okf bundle command."""

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
    strict: bool = typer.Option(
        False,
        "--strict",
        help=(
            "Enforce strict OKF spec output: fail on broken local .md links "
            "and skip AGENTS.md generation"
        ),
    ),
) -> None:
    """Convert plain markdown into an OKF-conformant knowledge bundle."""
    try:
        result = api.bundle(
            input_dir,
            output_dir,
            default_type=default_type,
            force=force,
            strict=strict,
        )
    except FileNotFoundError as e:
        typer.secho(f"Error: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)
    except FileExistsError as e:
        typer.secho(f"Error: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)
    except ValueError as e:
        typer.secho(f"Error: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    for w in result.warnings:
        typer.secho(f"Warning: {w}", fg=typer.colors.YELLOW, err=True)
    for e in result.errors:
        typer.secho(f"Error: {e}", fg=typer.colors.RED, err=True)

    if result.errors:
        raise typer.Exit(code=1)

    n = result.files_written
    typer.secho(
        f"Done. Converted {n} file{'s' if n != 1 else ''} → {result.output_dir}",
        fg=typer.colors.GREEN,
    )
