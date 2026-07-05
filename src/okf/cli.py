"""okf bundle — Plain markdown to OKF bundle converter."""

import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path

import typer

app = typer.Typer(
    name="okf",
    help="Open Knowledge Format tooling",
    no_args_is_help=True,
)


@app.callback()
def main() -> None:
    """Convert plain markdown into OKF-conformant knowledge bundles."""
    pass


RESERVED = frozenset({"index.md", "log.md", "readme.md"})
SPEC_RESERVED = frozenset({"index.md", "log.md"})


def _yaml_val(v: str) -> str:
    """Format a string value as valid YAML via JSON encoding."""
    return json.dumps(v, ensure_ascii=True)


def _build_frontmatter(type_: str, title: str, description: str, timestamp: str) -> str:
    parts = [
        "---",
        f"type: {_yaml_val(type_)}",
        f"title: {_yaml_val(title)}",
        f"description: {_yaml_val(description)}",
    ]
    if timestamp:
        parts.append(f"timestamp: {_yaml_val(timestamp)}")
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


@app.command()
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
        shutil.rmtree(dst)
        typer.echo(f"Removed existing '{output_dir}'", err=True)

    # Collect all .md files (skip reserved names, warn for reserved)
    md_files = []
    for f in sorted(src.rglob("*.md")):
        lower = f.name.lower()
        if lower in RESERVED:
            if lower == "log.md":
                typer.echo(
                    f"Warning: Skipping {f.relative_to(src)} — reserved filename '{f.name}' (not a concept)",
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
            title, description, body = _parse_md(text)
        except ValueError as e:
            typer.echo(f"Error: {rel}: {e}", err=True)
            raise typer.Exit(code=1)

        # Timestamp from file mtime
        mtime = os.path.getmtime(f)
        ts = datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat()

        # Build and write
        frontmatter = _build_frontmatter(type_name, title, description, ts)

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


def _parse_frontmatter(text: str) -> dict[str, str] | None:
    """Parse YAML frontmatter from an OKF concept file.

    Returns dict of key-value pairs, or None if frontmatter is missing
    or malformed (no opening ---, no closing ---).
    """
    lines = text.split("\n")
    if not lines or lines[0].strip() != "---":
        return None

    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            result: dict[str, str] = {}
            for line in lines[1:i]:
                if ":" in line:
                    key, _, val = line.partition(":")
                    result[key.strip()] = val.strip()
            return result

    return None


@app.command("list")
def cmd_list(
    directory: str = typer.Argument(
        ..., help="Directory of the OKF bundle"
    ),
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


@app.command("show")
def cmd_show(
    directory: str = typer.Argument(
        ..., help="Directory of the OKF bundle"
    ),
    concept_id: str = typer.Argument(
        ..., help="Concept ID to read (e.g. tables/orders)"
    ),
) -> None:
    """Print a concept's full contents by its concept ID."""
    dir_path = Path(directory)

    if not dir_path.is_dir():
        typer.echo(f"Error: '{directory}' is not a directory", err=True)
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


@app.command()
def validate(
    directory: str = typer.Argument(
        ..., help="Directory to validate as an OKF bundle"
    ),
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
    reserved = frozenset({"index.md", "log.md"})

    for f in md_files:
        rel = str(f.relative_to(dir_path))
        name_lower = f.name.lower()
        text = f.read_text(encoding="utf-8")

        if name_lower in reserved:
            if name_lower == "index.md" and text.startswith("---"):
                warnings.append(
                    f"{rel}: index.md has frontmatter — "
                    "only root index.md with okf_version is permitted (§11)"
                )
        else:
            fm = _parse_frontmatter(text)
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


if __name__ == "__main__":
    app()
