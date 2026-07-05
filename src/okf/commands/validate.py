"""okf validate command."""

from pathlib import Path

import typer

from okf.core import check_conformance


def validate(
    directory: str = typer.Argument(..., help="Directory to validate as an OKF bundle"),
) -> None:
    """Check whether a directory conforms to the OKF specification.

    Validates OKF v0.1 conformance per §9:
    - Every non-reserved .md file must have parseable YAML frontmatter.
    - Every frontmatter must have a non-empty 'type' field.
    - Reserved filenames (index.md, log.md) follow spec structure.
    """
    dir_path = Path(directory)

    if not dir_path.is_dir():
        typer.echo(f"Error: '{directory}' is not a directory", err=True)
        raise typer.Exit(code=1)

    md_files = sorted(dir_path.rglob("*.md"))
    if not md_files:
        typer.echo("No .md files found", err=True)
        raise typer.Exit(code=1)

    errors, warnings = check_conformance(dir_path)

    for w in warnings:
        typer.echo(f"Warning: {w}", err=True)
    for e in errors:
        typer.echo(f"Error: {e}", err=True)

    ok = len(md_files) - len(errors)
    parts = [f"{len(md_files)} files: {ok} ok"]
    if errors:
        parts.append(f"{len(errors)} errors")
    if warnings:
        parts.append(f"{len(warnings)} warnings")
    typer.echo("\n" + ", ".join(parts))

    if errors:
        raise typer.Exit(code=1)
