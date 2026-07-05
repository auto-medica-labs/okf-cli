"""okf list command."""

from pathlib import Path

import typer

from okf.core import SPEC_RESERVED


def cmd_list(
    directory: str = typer.Argument(..., help="Directory of the OKF bundle"),
) -> None:
    """List all concept IDs in an OKF bundle."""
    dir_path = Path(directory)

    if not dir_path.is_dir():
        typer.echo(f"Error: '{directory}' is not a directory", err=True)
        raise typer.Exit(code=1)

    md_files = sorted(dir_path.rglob("*.md"))
    cids: list[str] = []
    for f in md_files:
        if f.name.lower() in SPEC_RESERVED:
            continue
        rel = f.relative_to(dir_path)
        cid = str(rel.parent / rel.stem) if rel.parent != Path(".") else rel.stem
        cids.append(cid)

    if not cids:
        typer.echo("No concepts found", err=True)
        raise typer.Exit(code=1)

    for cid in cids:
        typer.echo(cid)
