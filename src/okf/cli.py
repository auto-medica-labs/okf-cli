"""okf enrich — Plain markdown to OKF bundle converter."""

import os
from datetime import datetime, timezone
from pathlib import Path

import typer

app = typer.Typer(
    name="okf",
    help="Open Knowledge Format tooling",
    no_args_is_help=True,
)

RESERVED = frozenset({"index.md", "log.md", "README.md"})


def _yaml_val(v: str) -> str:
    """Format a string value for YAML. Quote if needed."""
    if not v:
        return '""'
    needs = (
        v.startswith((" ", "\t"))
        or v.endswith((" ", "\t"))
        or any(c in v for c in ":,#{}[]&*!|>%@`\"'")
    )
    if needs or v.lower() in ("true", "false", "yes", "no", "on", "off", "null", "~"):
        v = v.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{v}"'
    return v


def _build_frontmatter(type_: str, title: str, description: str, timestamp: str) -> str:
    parts = [
        "---",
        f"type: {_yaml_val(type_)}",
        f"title: {_yaml_val(title)}",
        f"description: {_yaml_val(description)}",
    ]
    if timestamp:
        parts.append(f"timestamp: {timestamp}")
    parts.append("---")
    return "\n".join(parts)


def _parse_md(text: str) -> tuple[str, str, str]:
    """Parse title, description, body from plain markdown.

    Returns (title, description, body).
    Raises ValueError on format violation.
    """
    lines = text.splitlines(keepends=True)

    if not lines or not lines[0].startswith("# "):
        raise ValueError("Line 1 must be '# Title'")

    title = lines[0][2:].strip()
    if not title:
        raise ValueError("Title cannot be empty")

    # Find first non-blank after title line
    i = 1
    while i < len(lines) and not lines[i].strip():
        i += 1

    # Collect consecutive > lines
    desc_lines = []
    while i < len(lines) and lines[i].startswith(">"):
        # Handle both "> text" and ">text"
        content = lines[i][1:].strip()
        desc_lines.append(content)
        i += 1

    if not desc_lines:
        raise ValueError("Must have a '> description' block after title")

    description = " ".join(desc_lines).strip()

    # Skip blank lines between description and body
    while i < len(lines) and not lines[i].strip():
        i += 1

    body = "".join(lines[i:])

    return title, description, body


def _make_index(entries: list[dict]) -> str:
    """Generate index.md content from a list of concept entries."""
    if not entries:
        return ""
    lines = ["# Contents", ""]
    for e in entries:
        desc = f" - {e['description']}" if e.get("description") else ""
        lines.append(f"* [{e['title']}]({e['path']}){desc}")
    lines.append("")
    return "\n".join(lines)


@app.command()
def enrich(
    input_dir: str = typer.Argument(
        ..., help="Source directory of plain markdown files"
    ),
    output_dir: str = typer.Argument(..., help="Output directory for the OKF bundle"),
    default_type: str = typer.Option(
        None, help="Type for root-level files (skip root files if omitted)"
    ),
) -> None:
    """Convert plain markdown into an OKF-conformant knowledge bundle.

    Each .md file must start with '# Title' followed by a '>' description block.
    Directory name determines the concept 'type'. Root-level files need --default-type.
    """
    src = Path(input_dir)
    dst = Path(output_dir)

    if not src.is_dir():
        typer.echo(f"Error: input directory '{input_dir}' not found", err=True)
        raise typer.Exit(code=1)

    if dst.exists():
        typer.echo(f"Error: output directory '{output_dir}' already exists", err=True)
        raise typer.Exit(code=1)

    # Collect all .md files (skip reserved names)
    md_files = sorted(f for f in src.rglob("*.md") if f.name not in RESERVED)
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
            title, description, body = _parse_md(text)
        except ValueError as e:
            typer.echo(f"Error: {rel}: {e}", err=True)
            raise typer.Exit(code=1)

        # Timestamp from file mtime
        mtime = os.path.getmtime(f)
        ts = datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat()

        # Build and write
        frontmatter = _build_frontmatter(type_name, title, description, ts)

        # Preserve original line endings? Keep as-is from input.
        out_file.write_text(f"{frontmatter}\n\n{body}", encoding="utf-8")

        processed.append(
            (rel, {"title": title, "description": description, "type": type_name})
        )

    # Generate index.md per directory that has concepts
    dir_entries: dict[Path, list[dict]] = {}
    # Also track top-level subdirectories for root index
    top_level_subdirs: set[str] = set()
    root_entries: list[dict] = []

    for rel, meta in processed:
        parent = rel.parent
        if parent == Path("."):
            root_entries.append(
                {
                    "title": meta["title"],
                    "description": meta["description"],
                    "path": rel.name,
                }
            )
        else:
            dir_entries.setdefault(parent, []).append(
                {
                    "title": meta["title"],
                    "description": meta["description"],
                    "path": rel.name,
                }
            )
            # Top-level subdirectory = first component of relative path
            top_level_subdirs.add(rel.parts[0])

    for dir_path, entries in sorted(dir_entries.items()):
        index_path = dst / dir_path / "index.md"
        if not index_path.exists():
            index_content = _make_index(entries)
            if index_content:
                index_path.parent.mkdir(parents=True, exist_ok=True)
                index_path.write_text(index_content, encoding="utf-8")

    # Generate root index.md listing subdirectories and root-level concepts
    if top_level_subdirs or root_entries:
        root_index_entries: list[dict] = []
        for d in sorted(top_level_subdirs):
            root_index_entries.append({"title": d, "description": "", "path": f"{d}/"})
        root_index_entries.extend(root_entries)
        index_content = _make_index(root_index_entries)
        if index_content:
            (dst / "index.md").write_text(index_content, encoding="utf-8")

    # Summary
    n = len(processed)
    typer.echo(f"Done. Converted {n} file{'s' if n != 1 else ''} → {dst}")


if __name__ == "__main__":
    app()
