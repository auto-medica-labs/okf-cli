"""Python API for okf-cli — programmatic access without typer."""

from __future__ import annotations

import posixpath
import re
import shutil
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from okf.core import (
    RESERVED,
    SPEC_RESERVED,
    build_frontmatter,
    check_conformance,
    parse_frontmatter,
    parse_md,
)

_LINK_RE = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass
class BundleResult:
    files_written: int
    output_dir: Path
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


@dataclass
class ValidateResult:
    total_files: int
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return len(self.errors) == 0


@dataclass
class ConceptContent:
    frontmatter: dict[str, Any]
    body: str
    raw: str


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _iter_links(text: str):
    """Yield inline markdown link targets from body text."""
    for m in _LINK_RE.finditer(text):
        yield m.group(1).strip()


def _resolve_md_target(current_rel: Path, raw_target: str) -> str | None:
    """Resolve local markdown link target to bundle-relative POSIX path."""
    if not raw_target:
        return None

    target = raw_target.strip()
    if target.startswith("<") and target.endswith(">"):
        target = target[1:-1].strip()
    if not target:
        return None

    if re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", target):
        return None
    if target.startswith("#"):
        return None

    target = target.split("#", 1)[0].split("?", 1)[0].strip()
    if not target or target.endswith("/"):
        return None
    if not target.lower().endswith(".md"):
        return None

    if target.startswith("/"):
        resolved = posixpath.normpath(target.lstrip("/"))
    else:
        resolved = posixpath.normpath(
            posixpath.join(current_rel.parent.as_posix(), target)
        )

    if resolved in {"", "."}:
        return None

    return resolved


def _load_okfignore(src: Path) -> set[str]:
    """Load .okfignore entries as bundle-relative POSIX paths."""
    ignore_file = src / ".okfignore"
    if not ignore_file.is_file():
        return set()

    try:
        lines = ignore_file.read_text(encoding="utf-8").splitlines()
    except UnicodeDecodeError:
        raise ValueError(".okfignore is not valid UTF-8") from None

    entries: set[str] = set()
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        entries.add(line.lstrip("./"))
    return entries


def _generate_indexes(processed: list[tuple[Path, dict]], dst: Path) -> None:
    """Generate index.md for every directory with concept files or subdirs."""
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
        for i in range(len(rel.parts) - 1):
            grandparent = Path(*rel.parts[:i]) if i > 0 else Path(".")
            child_dir = rel.parts[i]
            dir_subdirs.setdefault(grandparent, set()).add(child_dir)

    for dir_path in sorted(set(dir_files.keys()) | set(dir_subdirs.keys())):
        index_path = dst / dir_path / "index.md"
        if index_path.exists():
            continue

        lines: list[str] = []
        entries = dir_files.get(dir_path, [])
        subdirs = sorted(dir_subdirs.get(dir_path, set()))

        if entries:
            lines.append("# Contents")
            lines.append("")
            for e in entries:
                display = e["title"] if e["title"] else Path(e["path"]).stem
                desc = f" - {e['description']}" if e.get("description") else ""
                lines.append(f"* [{display}]({e['path']}){desc}")
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


# ---------------------------------------------------------------------------
# Single-file conversion
# ---------------------------------------------------------------------------


def _write_concept(
    title: str,
    description: str,
    body: str,
    output_file: Path,
    type_: str,
    timestamp: str,
) -> None:
    """Parse content, build frontmatter, write OKF concept file."""
    frontmatter = build_frontmatter(type_, title, description, timestamp)
    if not (frontmatter.startswith("---\n") and frontmatter.endswith("\n---")):
        raise ValueError("generated invalid frontmatter")
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(f"{frontmatter}\n\n{body}", encoding="utf-8")


def convert_file(
    input_file: str | Path,
    output_file: str | Path,
    *,
    type_: str,
) -> BundleResult:
    """Convert a single markdown file to an OKF concept.

    Timestamp is derived from the input file's mtime.

    Args:
        input_file: Path to a plain markdown file.
        output_file: Target path for the OKF concept file.
        type_: Concept type (e.g. ``"reference"``, ``"playbook"``).

    Returns:
        BundleResult with files_written=1 on success.

    Raises:
        FileNotFoundError: If input_file does not exist.
        ValueError: If conversion fails.
    """
    src = Path(input_file)
    dst = Path(output_file)

    if not src.is_file():
        raise FileNotFoundError(f"Input file '{src}' not found")

    text = src.read_text(encoding="utf-8")
    title, description, body = parse_md(text)
    ts = datetime.fromtimestamp(src.stat().st_mtime, tz=UTC).isoformat()

    _write_concept(title, description, body, dst, type_, ts)
    return BundleResult(files_written=1, output_dir=dst.parent)


def convert_content(
    content: str,
    output_file: str | Path,
    *,
    type_: str,
) -> BundleResult:
    """Convert raw markdown content to an OKF concept.

    No timestamp is set (field omitted from frontmatter).

    Args:
        content: Raw markdown text.
        output_file: Target path for the OKF concept file.
        type_: Concept type (e.g. ``"reference"``, ``"playbook"``).

    Returns:
        BundleResult with files_written=1 on success.

    Raises:
        ValueError: If conversion fails.
    """
    dst = Path(output_file)
    title, description, body = parse_md(content)

    _write_concept(title, description, body, dst, type_, "")
    return BundleResult(files_written=1, output_dir=dst.parent)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def bundle(
    input_dir: str | Path,
    output_dir: str | Path | None = None,
    *,
    default_type: str | None = None,
    force: bool = False,
    strict: bool = False,
) -> BundleResult:
    """Convert plain markdown into an OKF-conformant knowledge bundle.

    Args:
        input_dir: Source directory of plain markdown files.
        output_dir: Target directory. Defaults to ``<input-dir>_knowledge_base``.
        default_type: Concept type for root-level files.
        force: Overwrite output directory if it exists.
        strict: Enforce strict OKF spec output: fail on broken local .md
            links and skip AGENTS.md generation.

    Returns:
        BundleResult with counts, warnings, and errors.
    """
    src = Path(input_dir)
    warnings: list[str] = []
    errors: list[str] = []

    if output_dir is None:
        output_dir = f"{src.name}_knowledge_base"
    dst = Path(output_dir)

    if not src.is_dir():
        raise FileNotFoundError(f"Input directory '{src}' not found")

    if src.resolve() == dst.resolve():
        raise ValueError("Input and output directories must be different")

    if dst.exists():
        if not force:
            raise FileExistsError(
                f"Output directory '{dst}' exists. Use --force to overwrite."
            )
        shutil.rmtree(dst)
        warnings.append(f"Removed existing '{dst}'")

    try:
        ignored = _load_okfignore(src)
    except ValueError as e:
        errors.append(str(e))
        return BundleResult(0, dst, warnings, errors)

    # Collect .md files (skip .okfignore and reserved)
    md_files: list[Path] = []
    for f in sorted(src.rglob("*.md")):
        rel = f.relative_to(src)
        rel_posix = rel.as_posix()

        if rel_posix in ignored:
            warnings.append(f"Skipping {rel} — matched .okfignore")
            continue
        if f.name.lower() in RESERVED:
            warnings.append(
                f"Skipping {rel} — reserved filename '{f.name}' (not a concept)"
            )
            continue
        md_files.append(f)

    if not md_files:
        errors.append("No markdown files found (excluding index.md, log.md)")
        return BundleResult(0, dst, warnings, errors)

    # Link checking
    planned_rels = [f.relative_to(src) for f in md_files]
    bundle_targets = {rel.as_posix() for rel in planned_rels}
    for rel in planned_rels:
        bundle_targets.add((rel.parent / "index.md").as_posix())
        for i in range(len(rel.parts) - 1):
            grandparent = Path(*rel.parts[:i]) if i > 0 else Path(".")
            bundle_targets.add((grandparent / "index.md").as_posix())

    link_issues: list[str] = []
    for f in md_files:
        rel = f.relative_to(src)
        text = f.read_text(encoding="utf-8")
        _title, _description, body = parse_md(text)

        seen: set[str] = set()
        for raw_target in _iter_links(body):
            resolved = _resolve_md_target(rel, raw_target)
            if resolved is None:
                continue
            if resolved.startswith("../"):
                msg = f"{rel}: link '{raw_target}' points outside bundle"
            elif resolved not in bundle_targets:
                msg = (
                    f"{rel}: link '{raw_target}' target "
                    f"'{resolved}' not found in bundle"
                )
            else:
                continue
            if msg not in seen:
                seen.add(msg)
                link_issues.append(msg)

    warnings.extend(link_issues)

    if strict and link_issues:
        errors.append("strict link check failed")
        return BundleResult(0, dst, warnings, errors)

    # Process files
    processed: list[tuple[Path, dict]] = []

    for f in md_files:
        rel = f.relative_to(src)
        out_file = dst / rel
        out_file.parent.mkdir(parents=True, exist_ok=True)

        if rel.parent == Path("."):
            type_name = default_type or src.name
        else:
            type_name = rel.parent.name

        text = f.read_text(encoding="utf-8")
        title, description, body = parse_md(text)
        ts = datetime.fromtimestamp(f.stat().st_mtime, tz=UTC).isoformat()

        try:
            _write_concept(title, description, body, out_file, type_name, ts)
        except ValueError as e:
            errors.append(f"{rel}: {e}")
            return BundleResult(len(processed), dst, warnings, errors)
        processed.append(
            (rel, {"title": title, "description": description, "type": type_name})
        )

    _generate_indexes(processed, dst)

    # Write AGENTS.md (skipped in strict mode)
    if not strict:
        (dst / "AGENTS.md").write_text(
            f"# Knowledge Base: {dst.name}\n\n"
            f"You are in an OKF (Open Knowledge Format) knowledge base called "
            f"**{dst.name}**. OKF is a structured markdown format where each "
            f"`.md` file is a concept with YAML frontmatter (`type`, `title`, "
            f"`description`) and cross-links between related concepts.\n\n"
            "## Instructions\n\n"
            "- **Answer from this knowledge base only.** Use the concepts and "
            "links here as your source of truth.\n"
            "- **If the answer is not in the knowledge base, say so directly.** "
            "Do not fabricate, guess, or pull from external knowledge.\n\n"
            "## Getting Started\n\n"
            "Read [index.md](index.md) first — it lists all concepts "
            "and subdirectories.\n\n"
            "## Navigation\n\n"
            "- Follow markdown links between concepts.\n"
            "- Each `.md` file has YAML frontmatter with `type`, `title`, "
            "`description`.\n"
            "- Subdirectories group related concepts by topic.\n"
            "- Cross-links (e.g. `[Customers](/tables/customers.md)`) "
            "express relationships.\n",
            encoding="utf-8",
        )

    return BundleResult(
        files_written=len(processed),
        output_dir=dst,
        warnings=warnings,
        errors=errors,
    )


def list_concepts(bundle_dir: str | Path) -> list[str]:
    """List all concept IDs in an OKF-conformant bundle.

    Args:
        bundle_dir: Path to an OKF bundle directory.

    Returns:
        Sorted list of concept IDs (bundle-relative path with .md stripped).

    Raises:
        ValueError: If the directory is not a valid OKF bundle.
    """
    dir_path = Path(bundle_dir)

    if not dir_path.is_dir():
        raise NotADirectoryError(f"'{dir_path}' is not a directory")

    errors, _warnings = check_conformance(dir_path)
    if errors:
        raise ValueError("not an OKF-conformant bundle:\n" + "\n".join(errors))

    cids: list[str] = []
    for f in sorted(dir_path.rglob("*.md")):
        if f.name.lower() in SPEC_RESERVED:
            continue
        rel = f.relative_to(dir_path)
        cid = str(rel.parent / rel.stem) if rel.parent != Path(".") else rel.stem
        cids.append(cid)

    return cids


def list_entries(bundle_dir: str | Path) -> list[dict[str, str]]:
    """List all concepts with their frontmatter metadata.

    Args:
        bundle_dir: Path to an OKF bundle directory.

    Returns:
        Sorted list of dicts with keys ``id``, ``type``, ``title``,
        ``description``.  ``title`` and ``description`` are empty strings
        when absent from frontmatter.

    Raises:
        ValueError: If the directory is not a valid OKF bundle.
    """
    dir_path = Path(bundle_dir)

    if not dir_path.is_dir():
        raise NotADirectoryError(f"'{dir_path}' is not a directory")

    errors, _warnings = check_conformance(dir_path)
    if errors:
        raise ValueError("not an OKF-conformant bundle:\n" + "\n".join(errors))

    entries: list[dict[str, str]] = []
    for f in sorted(dir_path.rglob("*.md")):
        if f.name.lower() in SPEC_RESERVED:
            continue
        rel = f.relative_to(dir_path)
        cid = str(rel.parent / rel.stem) if rel.parent != Path(".") else rel.stem
        fm = parse_frontmatter(f.read_text(encoding="utf-8")) or {}
        entries.append({
            "id": cid,
            "type": str(fm.get("type", "")),
            "title": str(fm.get("title", "")),
            "description": str(fm.get("description", "")),
        })

    return entries


def show_concept(bundle_dir: str | Path, concept_id: str) -> ConceptContent:
    """Read a concept by its ID from an OKF bundle.

    Args:
        bundle_dir: Path to an OKF bundle directory.
        concept_id: Concept ID (e.g. ``tables/orders``).

    Returns:
        ConceptContent with parsed frontmatter, body, and raw text.

    Raises:
        ValueError: If bundle is not conformant or concept not found.
        FileNotFoundError: If concept file does not exist.
    """
    dir_path = Path(bundle_dir)

    if not dir_path.is_dir():
        raise NotADirectoryError(f"'{dir_path}' is not a directory")

    errors, _warnings = check_conformance(dir_path)
    if errors:
        raise ValueError("not an OKF-conformant bundle:\n" + "\n".join(errors))

    concept_path = dir_path / f"{concept_id}.md"

    try:
        concept_path.resolve().relative_to(dir_path.resolve())
    except ValueError:
        raise ValueError(f"'{concept_id}' is outside the bundle directory")

    if concept_path.name.lower() in SPEC_RESERVED:
        raise ValueError(f"'{concept_id}' is a reserved filename, not a concept")

    if not concept_path.is_file():
        raise FileNotFoundError(
            f"Concept '{concept_id}' not found"
        )

    raw = concept_path.read_text(encoding="utf-8")
    fm = parse_frontmatter(raw)
    if fm is None:
        fm = {}

    # Strip frontmatter from body
    body = raw
    if raw.startswith("---"):
        lines = raw.split("\n")
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                body = "\n".join(lines[i + 1 :]).lstrip("\n")
                break

    return ConceptContent(frontmatter=fm, body=body, raw=raw)


def validate(bundle_dir: str | Path) -> ValidateResult:
    """Check whether a directory conforms to the OKF specification.

    Args:
        bundle_dir: Path to check.

    Returns:
        ValidateResult with file count, errors, and warnings.
    """
    dir_path = Path(bundle_dir)

    if not dir_path.is_dir():
        raise NotADirectoryError(f"'{dir_path}' is not a directory")

    md_files = sorted(dir_path.rglob("*.md"))
    if not md_files:
        return ValidateResult(total_files=0, errors=["No .md files found"], warnings=[])

    errors, warnings = check_conformance(dir_path)

    return ValidateResult(
        total_files=len(md_files),
        errors=errors,
        warnings=warnings,
    )
