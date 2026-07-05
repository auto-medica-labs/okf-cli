"""okf validate command."""

from pathlib import Path

import typer

from okf.core import SPEC_RESERVED, parse_frontmatter


def validate(
    directory: str = typer.Argument(..., help="Directory to validate as an OKF bundle"),
) -> None:
    """Check whether a directory conforms to the OKF specification.

    Validates OKF v0.1 conformance per §9:
    - Every non-reserved .md file must have parseable YAML frontmatter.
    - Every frontmatter must have a non-empty 'type' field.
    """
    dir_path = Path(directory)

    if not dir_path.is_dir():
        typer.echo(f"Error: '{directory}' is not a directory", err=True)
        raise typer.Exit(code=1)

    md_files = sorted(dir_path.rglob("*.md"))
    if not md_files:
        typer.echo("No .md files found", err=True)
        raise typer.Exit(code=1)

    errors: list[str] = []
    warnings: list[str] = []

    for f in md_files:
        rel = str(f.relative_to(dir_path))
        name_lower = f.name.lower()
        text = f.read_text(encoding="utf-8")

        if name_lower in SPEC_RESERVED:
            if name_lower == "index.md" and text.startswith("---"):
                warnings.append(
                    f"{rel}: index.md has frontmatter — "
                    "only root index.md with okf_version is permitted (§11)"
                )
        else:
            fm = parse_frontmatter(text)
            if fm is None:
                errors.append(f"{rel}: missing or unparseable YAML frontmatter")
            elif not fm.get("type"):
                errors.append(f"{rel}: frontmatter missing non-empty 'type' field")

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
