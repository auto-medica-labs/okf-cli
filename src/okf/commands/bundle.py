"""okf bundle command."""

import shutil
from datetime import UTC, datetime
from pathlib import Path

import typer

from okf.core import RESERVED, build_frontmatter, parse_md


def bundle(
    input_dir: str = typer.Argument(
        ..., help="Source directory of plain markdown files"
    ),
    output_dir: str = typer.Argument(
        "bundled", help="Output directory for the OKF bundle (default: bundled)"
    ),
    default_type: str = typer.Option(
        None, help="Type for root-level files (skip root files if omitted)"
    ),
    force: bool = typer.Option(
        False, "--force", "-f", help="Overwrite output directory if it exists"
    ),
) -> None:
    """Convert plain markdown into an OKF-conformant knowledge bundle.

    Each .md file must start with '# Title' followed by a '>' description block.
    Directory name determines the concept 'type'. Root-level files need --default-type.
    If output-dir is omitted, defaults to 'bundled'.
    """
    src = Path(input_dir)
    dst = Path(output_dir)

    if not src.is_dir():
        typer.echo(f"Error: input directory '{input_dir}' not found", err=True)
        raise typer.Exit(code=1)

    if dst.exists():
        if not force:
            typer.echo(
                f"Error: output directory '{output_dir}' exists. "
                "Use --force to overwrite.",
                err=True,
            )
            raise typer.Exit(code=1)
        shutil.rmtree(dst)
        typer.echo(f"Removed existing '{output_dir}'", err=True)

    # Collect all .md files (skip reserved names, warn for reserved)
    md_files = []
    for f in sorted(src.rglob("*.md")):
        lower = f.name.lower()
        if lower in RESERVED:
            typer.echo(
                f"Warning: Skipping {f.relative_to(src)} — "
                f"reserved filename '{f.name}' (not a concept)",
                err=True,
            )
            continue
        md_files.append(f)
    if not md_files:
        typer.echo("No markdown files found (excluding index.md, log.md)", err=True)
        raise typer.Exit(code=1)

    # Process each file, storing metadata for index generation
    processed: list[tuple[Path, dict]] = []  # (relative_output_path, metadata)

    for f in md_files:
        rel = f.relative_to(src)
        out_file = dst / rel
        out_file.parent.mkdir(parents=True, exist_ok=True)

        # Determine type
        if rel.parent == Path("."):
            if default_type is None:
                typer.echo(
                    f"Warning: Skipping {rel} — root-level file needs --default-type",
                    err=True,
                )
                continue
            type_name = default_type
        else:
            type_name = rel.parent.name

        # Parse
        try:
            text = f.read_text(encoding="utf-8")
            title, description, body = parse_md(text)
        except ValueError as e:
            typer.echo(f"Error: {rel}: {e}", err=True)
            raise typer.Exit(code=1)

        # Timestamp from file mtime
        ts = datetime.fromtimestamp(f.stat().st_mtime, tz=UTC).isoformat()

        # Build and write
        frontmatter = build_frontmatter(type_name, title, description, ts)

        # Validate frontmatter structure
        if not (frontmatter.startswith("---\n") and frontmatter.endswith("\n---")):
            typer.echo(f"Error: {rel}: generated invalid frontmatter", err=True)
            raise typer.Exit(code=1)

        # Preserve original line endings? Keep as-is from input.
        out_file.write_text(f"{frontmatter}\n\n{body}", encoding="utf-8")

        processed.append(
            (rel, {"title": title, "description": description, "type": type_name})
        )

    # Collect per-directory files and subdirectories
    dir_files: dict[Path, list[dict]] = {}
    dir_subdirs: dict[Path, set[str]] = {}

    for rel, meta in processed:
        parent = rel.parent
        dir_files.setdefault(parent, []).append(
            {
                "title": meta["title"],
                "description": meta["description"],
                "path": rel.name,
            }
        )
        # Record subdirectory relationships at every level
        for i in range(len(rel.parts) - 1):
            grandparent = Path(*rel.parts[:i]) if i > 0 else Path(".")
            child_dir = rel.parts[i]
            dir_subdirs.setdefault(grandparent, set()).add(child_dir)

    # Generate index.md for every directory with files or subdirs
    for dir_path in sorted(set(dir_files.keys()) | set(dir_subdirs.keys())):
        index_path = dst / dir_path / "index.md"
        if index_path.exists():
            continue

        lines = []
        entries = dir_files.get(dir_path, [])
        subdirs = sorted(dir_subdirs.get(dir_path, set()))

        if entries:
            lines.append("# Contents")
            lines.append("")
            for e in entries:
                desc = f" - {e['description']}" if e.get("description") else ""
                lines.append(f"* [{e['title']}]({e['path']}){desc}")
            lines.append("")

        if subdirs:
            lines.append("# Directories")
            lines.append("")
            for d in subdirs:
                lines.append(f"* [{d}]({d}/)")
            lines.append("")

        if lines:
            index_path.parent.mkdir(parents=True, exist_ok=True)
            index_path.write_text("\n".join(lines), encoding="utf-8")

    # Summary
    n = len(processed)
    typer.echo(f"Done. Converted {n} file{'s' if n != 1 else ''} → {dst}")
