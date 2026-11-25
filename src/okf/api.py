"""Python API for okf-cli — programmatic access without typer."""

from __future__ import annotations

import os
import posixpath
import re
import shutil
import tempfile
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from importlib.metadata import version as _package_version
from pathlib import Path, PurePosixPath
from typing import Any

import yaml

from okf.core import (
    RESERVED,
    SPEC_RESERVED,
    build_frontmatter,
    check_conformance,
    check_file,
    dump_frontmatter,
    parse_frontmatter,
    parse_md_with_frontmatter,
)

_LINK_RE = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")


# ---------------------------------------------------------------------------
# Package version for provenance
# ---------------------------------------------------------------------------


def _okfcli_actor() -> str:
    """Return the actor identifier used in generated frontmatter."""
    try:
        return f"okf-cli/{_package_version('okf-cli')}"
    except Exception:  # pragma: no cover
        return "okf-cli/unknown"


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
    id: str = ""
    links: list[dict[str, Any]] = field(default_factory=list)


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
        entry = line.lstrip("./")
        # Normalize folder globs: tables/foo/*, tables/foo/** -> tables/foo/
        if entry.endswith("/**"):
            entry = entry[:-3] + "/"
        elif entry.endswith("/*"):
            entry = entry[:-2] + "/"
        entries.add(entry)
    return entries


def _is_ignored(rel_posix: str, ignored: set[str]) -> bool:
    """Check exact match or folder-prefix match (entries ending with /)."""
    if rel_posix in ignored:
        return True
    return any(pat.endswith("/") and rel_posix.startswith(pat) for pat in ignored)


def _copy_assets(src: Path, dst: Path, ignored: set[str]) -> int:
    """Copy non-.md assets (e.g. .py, .sql) from src to dst.

    Skips ``.md`` files (already processed as concepts), ``.okfignore``,
    and any path listed in ``ignored``. Returns count of copied files.
    """
    copied = 0
    for item in src.rglob("*"):
        if item.is_symlink() or not item.is_file():
            continue
        rel = item.relative_to(src).as_posix()
        if (
            item.suffix == ".md"
            or _is_ignored(rel, ignored)
            or item.name == ".okfignore"
        ):
            continue
        target = dst / item.relative_to(src)
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, target)
            copied += 1
    return copied


def _path_exists(path: Path) -> bool:
    """Return true for paths including dangling symlinks."""
    return path.exists() or path.is_symlink()


def _remove_path(path: Path) -> None:
    """Remove a file, symlink, or directory without following symlinks."""
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    else:
        path.unlink()


def _commit_staged_bundle(staged: Path, dst: Path) -> bool:
    """Replace ``dst`` with a fully built staging directory.

    The previous output is moved aside only at commit time and restored if
    promoting the staged bundle fails. Returns whether an output was replaced.
    """
    backup: Path | None = None
    if _path_exists(dst):
        fd, backup_name = tempfile.mkstemp(
            prefix=f".{dst.name or 'okf'}.backup-", dir=dst.parent
        )
        os.close(fd)
        backup = Path(backup_name)
        backup.unlink()
        os.replace(dst, backup)

    try:
        os.replace(staged, dst)
    except BaseException:
        if backup is not None:
            os.replace(backup, dst)
        raise

    if backup is not None:
        _remove_path(backup)
    return backup is not None


def _index_texts(processed: list[tuple[Path, dict]]) -> dict[Path, str]:
    """Render the index.md text of every directory that should have one.

    Returns a mapping from bundle-relative directory to the index content.
    Directories whose concepts could not be represented (or with no
    concepts at all) are simply absent from the mapping.
    """
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

    texts: dict[Path, str] = {}
    for dir_path in sorted(set(dir_files.keys()) | set(dir_subdirs.keys())):
        lines: list[str] = []
        if dir_path == Path("."):
            lines.append("---")
            lines.append('okf_version: "0.2"')
            lines.append("---")
            lines.append("")

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
            texts[dir_path] = "\n".join(lines)

    return texts


def _empty_index_text(dir_path: Path) -> str:
    """Minimal index content for a directory with nothing left to list."""
    if dir_path == Path("."):
        return '---\nokf_version: "0.2"\n---\n\n'
    return ""


def _generate_indexes(
    processed: list[tuple[Path, dict]], dst: Path, *, overwrite: bool = False
) -> tuple[int, list[Path]]:
    """Generate index.md for every directory with concept files or subdirs.

    Returns ``(files_written, emptied)`` where ``emptied`` lists the index
    paths that were reduced to an empty listing because no concept remains
    under them; ``bundle`` never empties anything (it builds into a fresh
    directory), only ``reindex`` does. Emptying a stale index also counts
    as writing a file. Existing index files are kept unless ``overwrite`` is
    true (``reindex`` passes it) — in which case generated indexes are
    rewritten even where unchanged, and stale ones emptied.
    """
    texts = _index_texts(processed)
    written = 0
    emptied: list[Path] = []
    for dir_path, text in texts.items():
        index_path = dst / dir_path / "index.md"
        if index_path.exists() and not overwrite:
            continue
        index_path.parent.mkdir(parents=True, exist_ok=True)
        index_path.write_text(text, encoding="utf-8")
        written += 1

    if overwrite:
        for index_path in dst.rglob("index.md"):
            rel_dir = index_path.relative_to(dst).parent
            dir_path = Path(".") if rel_dir == Path(".") else rel_dir
            if dir_path in texts:
                continue
            text = _empty_index_text(dir_path)
            if index_path.read_text(encoding="utf-8") == text:
                continue
            index_path.write_text(text, encoding="utf-8")
            emptied.append(index_path)
            written += 1

    return written, emptied


# ---------------------------------------------------------------------------
# Single-file conversion
# ---------------------------------------------------------------------------


def _merge_input_frontmatter(
    existing: dict[str, Any] | None,
    title: str,
    description: str,
) -> tuple[str, str, dict[str, Any]]:
    """Apply bundler precedence to input frontmatter values.

    Conflict resolution:
    - ``type`` and ``generated`` are dropped (caller supplies them).
    - ``okf_version`` is dropped (belongs only in the bundle-root index.md).
    - ``title``/``description`` from input frontmatter override parsed body
      values when present.
    - All other keys are returned as ``extras`` to be preserved.
    """
    if not existing:
        return title, description, {}

    extras = dict(existing)
    merged_title = extras.pop("title", title) if "title" in extras else title
    merged_description = (
        extras.pop("description", description)
        if "description" in extras
        else description
    )
    extras.pop("type", None)
    extras.pop("generated", None)
    extras.pop("okf_version", None)
    return merged_title, merged_description, extras


def _write_concept(
    title: str,
    description: str,
    body: str,
    output_file: Path,
    type_: str,
    generated: dict[str, str] | None,
    existing_frontmatter: dict[str, Any] | None = None,
) -> None:
    """Parse content, build frontmatter, write OKF concept file."""
    merged_title, merged_description, extras = _merge_input_frontmatter(
        existing_frontmatter, title, description
    )
    frontmatter = build_frontmatter(
        type_, merged_title, merged_description, generated, extras
    )
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

    ``generated.at`` is derived from the input file's mtime; ``generated.by``
    is the okf-cli actor.

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
    existing, title, description, body = parse_md_with_frontmatter(text)
    ts = datetime.fromtimestamp(src.stat().st_mtime, tz=UTC).isoformat()
    generated = {"by": _okfcli_actor(), "at": ts}

    _write_concept(title, description, body, dst, type_, generated, existing)
    return BundleResult(files_written=1, output_dir=dst.parent)


def convert_content(
    content: str,
    output_file: str | Path,
    *,
    type_: str,
) -> BundleResult:
    """Convert raw markdown content to an OKF concept.

    No ``generated`` block is set (field omitted from frontmatter).

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
    existing, title, description, body = parse_md_with_frontmatter(content)

    _write_concept(title, description, body, dst, type_, None, existing)
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
    dry_run: bool = False,
) -> BundleResult:
    """Convert plain markdown into an OKF-conformant knowledge bundle.

    Args:
        input_dir: Source directory of plain markdown files.
        output_dir: Target directory. Defaults to ``<input-dir>_knowledge_base``.
        default_type: Concept type for root-level files.
        force: Replace an existing output only after a complete staged build.
        strict: Enforce strict OKF spec output: fail on broken local .md
            links and skip AGENTS.md generation.
        dry_run: Validate and report what would be written without creating
            or modifying any files or directories.

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

    try:
        dst.resolve().relative_to(src.resolve())
    except ValueError:
        pass
    else:
        raise ValueError("Output directory must not be inside input directory")

    output_exists = _path_exists(dst)
    if output_exists and not dry_run and not force:
        raise FileExistsError(
            f"Output directory '{dst}' exists. Use --force to overwrite."
        )
    if output_exists and force and dry_run:
        warnings.append(f"Would replace existing '{dst}'")

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

        if _is_ignored(rel_posix, ignored):
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

    # Parse input files and check links
    planned_rels = [f.relative_to(src) for f in md_files]
    bundle_targets = {rel.as_posix() for rel in planned_rels}
    for rel in planned_rels:
        bundle_targets.add((rel.parent / "index.md").as_posix())
        for i in range(len(rel.parts) - 1):
            grandparent = Path(*rel.parts[:i]) if i > 0 else Path(".")
            bundle_targets.add((grandparent / "index.md").as_posix())

    parsed: list[tuple[Path, dict[str, Any], str, str, str, float]] = []
    link_issues: list[str] = []

    for f in md_files:
        rel = f.relative_to(src)
        text = f.read_text(encoding="utf-8")
        try:
            fm, title, description, body = parse_md_with_frontmatter(
                text, strict=strict
            )
        except ValueError as e:
            errors.append(f"{rel}: {e}")
            continue
        parsed.append((rel, fm, title, description, body, f.stat().st_mtime))

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

    if errors:
        return BundleResult(0, dst, warnings, errors)
    if strict and link_issues:
        errors.append("strict link check failed")
        return BundleResult(0, dst, warnings, errors)

    # Build in a temporary sibling directory so failures never destroy the
    # existing output. Rename into place only after all bundle files are ready.
    processed: list[tuple[Path, dict]] = []
    staging_dir: Path | None = None
    build_dir = dst
    if not dry_run:
        dst.parent.mkdir(parents=True, exist_ok=True)
        staging_dir = Path(
            tempfile.mkdtemp(prefix=f".{dst.name or 'okf'}.staging-", dir=dst.parent)
        )
        build_dir = staging_dir

    try:
        for rel, fm, title, description, body, mtime in parsed:
            out_file = build_dir / rel

            if rel.parent == Path("."):
                type_name = default_type or src.name
            else:
                type_name = rel.parent.name

            ts = datetime.fromtimestamp(mtime, tz=UTC).isoformat()
            generated = {"by": _okfcli_actor(), "at": ts}

            merged_title, merged_description, _ = _merge_input_frontmatter(
                fm, title, description
            )

            if not dry_run:
                out_file.parent.mkdir(parents=True, exist_ok=True)
                try:
                    _write_concept(
                        title, description, body, out_file, type_name, generated, fm
                    )
                except ValueError as e:
                    errors.append(f"{rel}: {e}")
                    return BundleResult(len(processed), dst, warnings, errors)
            processed.append(
                (
                    rel,
                    {
                        "title": merged_title,
                        "description": merged_description,
                        "type": type_name,
                    },
                )
            )

        files_written = len(processed)

        if not dry_run:
            _generate_indexes(processed, build_dir)
            files_written += _copy_assets(src, build_dir, ignored)

        # Write AGENTS.md (skipped in strict mode)
        if not dry_run and not strict:
            (build_dir / "AGENTS.md").write_text(
                f"# Knowledge Base: {dst.name}\n\n"
                f"You are in an OKF (Open Knowledge Format) knowledge base called "
                f"**{dst.name}**. OKF is a structured markdown format where each "
                f"`.md` file is a concept with YAML frontmatter and cross-links "
                f"between related concepts.\n\n"
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
                "`description`, and other producer-defined metadata.\n"
                "- Subdirectories group related concepts by topic.\n"
                "- Cross-links (e.g. `[Customers](/tables/customers.md)`) "
                "express relationships.\n",
                encoding="utf-8",
            )

        if staging_dir is not None:
            replaced = _commit_staged_bundle(staging_dir, dst)
            if replaced:
                warnings.append(f"Replaced existing '{dst}'")
    finally:
        if staging_dir is not None and _path_exists(staging_dir):
            _remove_path(staging_dir)

    return BundleResult(
        files_written=files_written,
        output_dir=dst,
        warnings=warnings,
        errors=errors,
    )


def reindex(bundle_dir: str | Path) -> BundleResult:
    """Rebuild the index files of a bundle from the concepts on disk.

    Rewrites every index.md the bundle needs (creating them where they are
    missing) and *empties* index files left behind by removed concepts or
    removed directories, so the listing never references a deleted concept.
    Index files are never deleted; the bundle-root okf_version is kept.
    Hand-written content in index.md files is discarded.

    Args:
        bundle_dir: Path to an OKF bundle directory.

    Returns:
        BundleResult with ``files_written`` set to the number of index files
        written and ``warnings`` naming every index that was emptied.

    Raises:
        NotADirectoryError: If bundle_dir is not a directory.
        ValueError: If the directory is not a conformant OKF bundle.
    """
    dst = Path(bundle_dir)
    entries = list_entries(dst)
    processed = [
        (
            Path(e["id"] + ".md"),
            {
                "title": e["title"],
                "description": e["description"],
                "type": e["type"],
            },
        )
        for e in entries
    ]
    count, emptied = _generate_indexes(processed, dst, overwrite=True)
    warnings = [
        f"Emptied stale index: {index.relative_to(dst)}"
        for index in sorted(emptied, key=str)
    ]
    return BundleResult(files_written=count, output_dir=dst, warnings=warnings)


# ---------------------------------------------------------------------------
# Loaded bundle: one conformance pass, then repeated reads and searches
# ---------------------------------------------------------------------------

# Field relevance for search; unlisted frontmatter keys weigh 1.
_SEARCH_KEY_WEIGHTS = {"title": 3, "tags": 2, "description": 2}
# Keys treated as provenance, not content; never matched by search.
_PROVENANCE_KEYS = frozenset({"generated", "verified"})
_CONCEPT_ID_WEIGHT = 3
_WHOLE_VALUE_BONUS = 5
_ATX_PREFIX_RE = re.compile(r"^(#{1,6})[ \t]+(.*)$")
_TRAILING_HASHES_RE = re.compile(r"[ \t]+#+[ \t]*$")
_FENCE_RE = re.compile(r"^[ ]{0,3}(`{3,}|~{3,})")


def _scalar_text(value: Any) -> str | None:
    """Render a YAML scalar as search/filter text; None when not a scalar."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, str):
        return value
    return None


def _frontmatter_strings(value: Any) -> list[str]:
    """Every searchable string inside a frontmatter value (nested included)."""
    scalar = _scalar_text(value)
    if scalar is not None:
        return [scalar]
    if isinstance(value, dict):
        out: list[str] = []
        for item in value.values():
            out.extend(_frontmatter_strings(item))
        return out
    if isinstance(value, (list, tuple)):
        out = []
        for item in value:
            out.extend(_frontmatter_strings(item))
        return out
    return []


def _search_document(
    concept_id: str, frontmatter: dict[str, Any]
) -> list[tuple[int, str]]:
    """(weight, casefolded text) pairs that search matches against."""
    document = [(_CONCEPT_ID_WEIGHT, concept_id.casefold())]
    for key, value in frontmatter.items():
        if key in _PROVENANCE_KEYS:
            continue
        weight = _SEARCH_KEY_WEIGHTS.get(key, 1)
        document.extend(
            (weight, text.casefold()) for text in _frontmatter_strings(value)
        )
    return document


def _filter_equal(actual: Any, expected: Any) -> bool:
    """Case-insensitive scalar equality; membership for list-valued keys."""
    wanted = _scalar_text(expected)
    if wanted is None:
        wanted = str(expected)
    wanted = wanted.casefold()
    values = actual if isinstance(actual, (list, tuple)) else [actual]
    for item in values:
        candidate = _scalar_text(item)
        if candidate is not None and candidate.casefold() == wanted:
            return True
    return False


def _entry(concept_id: str, frontmatter: dict[str, Any]) -> dict[str, str]:
    return {
        "id": concept_id,
        "type": str(frontmatter.get("type", "")),
        "title": str(frontmatter.get("title", "")),
        "description": str(frontmatter.get("description", "")),
    }


def _split_frontmatter(raw: str) -> str:
    """Return the markdown after the frontmatter block, or all of it."""
    if raw.startswith("---"):
        lines = raw.split("\n")
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                return "\n".join(lines[i + 1 :]).lstrip("\n")
    return raw


def _scan_headings(lines: list[str]) -> list[tuple[int, int, str]]:
    """(line index, level, text) of every ATX heading outside fenced code."""
    headings: list[tuple[int, int, str]] = []
    fence: str | None = None
    for index, line in enumerate(lines):
        match = _FENCE_RE.match(line.rstrip("\n"))
        if match:
            marker = match.group(1)[0]
            if fence is None:
                fence = marker
            elif fence == marker:
                fence = None
            continue
        if fence is not None:
            continue
        match = _ATX_PREFIX_RE.match(line.rstrip("\n"))
        if match:
            text = _TRAILING_HASHES_RE.sub("", match.group(2)).strip()
            headings.append((index, len(match.group(1)), text))
    return headings


def _section_lines(body: str, section: str) -> str | None:
    """Return one section: its heading through the next same-or-higher heading."""
    lines = body.splitlines(keepends=True)
    headings = _scan_headings(lines)
    wanted = section.strip().strip("#").strip().casefold()
    for index, (start, level, text) in enumerate(headings):
        if text.casefold() != wanted:
            continue
        end = len(lines)
        for candidate, candidate_level, _ in headings[index + 1 :]:
            if candidate_level <= level:
                end = candidate
                break
        return "".join(lines[start:end]).rstrip("\n") + "\n"
    return None


def _concept_file(root: Path, concept_id: str) -> Path:
    """Resolve a concept ID to a file inside ``root``.

    Accepts a leading ``/`` (link style) and a trailing ``.md``. Raises
    ValueError for empty, unsafe, or reserved IDs.
    """
    cid = concept_id.strip().lstrip("/")
    if cid.lower().endswith(".md"):
        cid = cid[:-3]
    if not cid:
        raise ValueError("concept ID must not be empty")

    path = root / f"{cid}.md"
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        raise ValueError(f"'{concept_id}' is outside the bundle directory") from None
    if path.name.lower() in SPEC_RESERVED:
        raise ValueError(f"'{concept_id}' is a reserved filename, not a concept")
    return path


def _concept_sort_key(rel: str) -> tuple[str, ...]:
    """Order bundle paths by path component, like ``Path.rglob`` does."""
    return PurePosixPath(rel).parts


@dataclass
class _ConceptRecord:
    """What the bundle knows about one .md file on disk."""

    rel: str
    stamp: tuple[int, int, int]
    errors: list[str]
    concept_id: str | None
    frontmatter: dict[str, Any]
    search_fields: list[tuple[int, str]]


class Bundle:
    """A conformant OKF bundle loaded into memory for repeated access.

    ``Bundle.open`` validates the whole bundle once and indexes every
    concept's frontmatter. Subsequent calls serve from memory; call
    ``refresh()`` to re-read files that changed on disk (only added,
    modified or removed files are re-read). ``write()`` refreshes itself.
    """

    def __init__(self, root: Path) -> None:
        self.path = root
        self._records: dict[str, _ConceptRecord] = {}

    @classmethod
    def open(cls, bundle_dir: str | Path) -> Bundle:
        """Load a bundle and check its conformance.

        Raises:
            NotADirectoryError: If bundle_dir is not a directory.
            ValueError: If the bundle is not OKF-conformant.
        """
        root = Path(bundle_dir)
        if not root.is_dir():
            raise NotADirectoryError(f"'{root}' is not a directory")
        bundle = cls(root)
        bundle.refresh()
        return bundle

    def refresh(self) -> bool:
        """Re-read files added, changed or removed since the last load.

        Returns whether anything changed. On failure the previously loaded
        state is kept and ValueError is raised; the bundle is left
        conformant or untouched, never half-updated.
        """
        found: dict[str, _ConceptRecord] = {}
        scan_errors: list[str] = []
        try:
            candidates = list(self.path.rglob("*.md"))
        except OSError as exc:
            raise ValueError(
                f"not an OKF-conformant bundle:\nscan failed: {exc.strerror or exc}"
            ) from exc

        for md in candidates:
            rel = md.relative_to(self.path).as_posix()
            try:
                stat = md.stat()
            except OSError as exc:
                scan_errors.append(f"{rel}: unreadable ({exc.strerror or exc})")
                continue
            stamp = (stat.st_mtime_ns, stat.st_size, stat.st_ino)
            prior = self._records.get(rel)
            if prior is not None and prior.stamp == stamp:
                found[rel] = prior
                continue
            found[rel] = self._load(md, rel, stamp)

        errors = scan_errors + [
            error
            for rel in sorted(found, key=_concept_sort_key)
            for error in found[rel].errors
        ]
        if errors:
            raise ValueError("not an OKF-conformant bundle:\n" + "\n".join(errors))

        changed = set(found) != set(self._records) or any(
            found[rel] is not self._records[rel] for rel in found
        )
        self._records = found
        return changed

    @staticmethod
    def _load(path: Path, rel: str, stamp: tuple[int, int, int]) -> _ConceptRecord:
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return _ConceptRecord(
                rel=rel,
                stamp=stamp,
                errors=[f"{rel}: file is not valid UTF-8"],
                concept_id=None,
                frontmatter={},
                search_fields=[],
            )
        except OSError as exc:
            return _ConceptRecord(
                rel=rel,
                stamp=stamp,
                errors=[f"{rel}: unreadable ({exc.strerror or exc})"],
                concept_id=None,
                frontmatter={},
                search_fields=[],
            )

        problems, fm = check_file(rel, text)
        errors = [f"{rel}: {problem}" for problem in problems]
        name_lower = Path(rel).name.lower()
        concept_id: str | None = None
        fields: list[tuple[int, str]] = []
        if name_lower not in SPEC_RESERVED and fm is not None:
            concept_id = rel[:-3]
            fields = _search_document(concept_id, fm)
        return _ConceptRecord(
            rel=rel,
            stamp=stamp,
            errors=errors,
            concept_id=concept_id,
            frontmatter=fm if fm is not None else {},
            search_fields=fields,
        )

    def _concepts(self) -> list[tuple[str, _ConceptRecord]]:
        """(concept_id, record) pairs for every concept, sorted by ID."""
        pairs = [
            (record.concept_id, record)
            for rel, record in self._records.items()
            if record.concept_id is not None
        ]
        pairs.sort(key=lambda pair: PurePosixPath(pair[0]).parts)
        return pairs

    def ids(self) -> list[str]:
        """Sorted concept IDs."""
        return [concept_id for concept_id, _ in self._concepts()]

    def entries(self) -> list[dict[str, str]]:
        """Sorted ``{id, type, title, description}`` for every concept."""
        return [
            _entry(concept_id, record.frontmatter)
            for concept_id, record in self._concepts()
        ]

    def search(
        self,
        query: str = "",
        *,
        type_: str | None = None,
        filters: dict[str, Any] | None = None,
        limit: int | None = 20,
    ) -> list[dict[str, str]]:
        """Find concepts by words in the ID or any frontmatter value.

        Each word of ``query`` is matched case-insensitively as a substring
        of the ID, type, title, description, tags and every other
        frontmatter value (nested values included; dates and numbers are
        matched as their text; ``generated`` and ``verified`` are skipped).
        Results rank by how many words they match, then by field weight
        (ID and title weigh more than tags and description, which weigh
        more than other keys); a field equal to the whole query earns a
        bonus. An empty query returns everything that passes the filters.

        Args:
            query: Space-separated words.
            type_: Only concepts whose ``type`` equals this (case-insensitive).
            filters: Frontmatter key -> required value. Scalar comparison
                is case-insensitive; a list-valued key matches when it
                contains the value.
            limit: Maximum results; ``None`` for all, negatives mean none.

        Returns:
            Entries shaped like ``entries()``, best match first.
        """
        terms = query.casefold().split()
        whole = " ".join(terms)
        type_norm = type_.casefold() if type_ is not None else None
        ranked: list[tuple[int, int, str, dict[str, str]]] = []
        for concept_id, record in self._concepts():
            fm = record.frontmatter
            if type_norm is not None:
                actual = fm.get("type")
                actual_text = actual if isinstance(actual, str) else str(actual or "")
                if actual_text.casefold() != type_norm:
                    continue
            if filters and not all(
                _filter_equal(fm.get(key), expected)
                for key, expected in filters.items()
            ):
                continue

            matched = 0
            score = 0
            for term in terms:
                hit = 0
                for weight, text in record.search_fields:
                    if term in text:
                        hit = max(hit, weight)
                if hit:
                    matched += 1
                    score += hit
            if terms and matched == 0:
                continue
            if terms and any(text == whole for _weight, text in record.search_fields):
                score += _WHOLE_VALUE_BONUS
            ranked.append((-matched, -score, concept_id, _entry(concept_id, fm)))

        ranked.sort(key=lambda row: (row[0], row[1], row[2]))
        results = [row[3] for row in ranked]
        if limit is None:
            return results
        return results[: max(limit, 0)]

    def read(self, concept_id: str, *, section: str | None = None) -> ConceptContent:
        """Read one concept, or only one of its sections.

        With ``section``, ``body`` holds just that section: the heading line
        through the line before the next heading of the same or higher
        level. Heading text is matched case-insensitively, with optional
        leading ``#`` characters accepted. ``raw`` is always the whole file.

        ``id`` is the normalized concept ID. ``links`` lists the bundle-local
        concept links in the returned body, deduplicated, as
        ``{target, id, exists}``: ``target`` as written, ``id`` resolved
        relative to this concept, ``exists`` false when the bundle has no
        concept at that path. Links to reserved files, outside the bundle,
        to external URLs or to anchors are omitted.

        Raises:
            ValueError: Unsafe or reserved ID, or the section does not exist.
            FileNotFoundError: The concept does not exist.
        """
        path = _concept_file(self.path, concept_id)
        if not path.is_file():
            raise FileNotFoundError(f"Concept '{concept_id}' not found")
        rel = posixpath.normpath(path.relative_to(self.path).as_posix())

        raw = path.read_text(encoding="utf-8")
        fm = parse_frontmatter(raw) or {}
        body = _split_frontmatter(raw)
        if section is not None:
            part = _section_lines(body, section)
            if part is None:
                names = [
                    text for _index, _level, text in _scan_headings(body.splitlines())
                ] or ["none"]
                available = ", ".join(names)
                raise ValueError(
                    f"No section '{section}' in '{concept_id}'. "
                    f"Available sections: {available}"
                )
            body = part
        return ConceptContent(
            frontmatter=fm,
            body=body,
            raw=raw,
            id=rel[:-3],
            links=self._concept_links(rel, body),
        )

    def _concept_links(self, rel: str, body: str) -> list[dict[str, Any]]:
        """Bundle-local concept links in the body of the concept file ``rel``."""
        links: list[dict[str, Any]] = []
        seen: set[str] = set()
        for target in _iter_links(body):
            resolved = _resolve_md_target(Path(rel), target)
            if resolved is None:
                continue
            if resolved == ".." or resolved.startswith("../"):
                continue
            if resolved in seen:
                continue
            seen.add(resolved)
            name_lower = PurePosixPath(resolved).name.lower()
            if name_lower in SPEC_RESERVED:
                continue
            record = self._records.get(resolved)
            links.append(
                {
                    "target": target,
                    "id": resolved[:-3],
                    "exists": record is not None and record.concept_id is not None,
                }
            )
        return links

    def _directory_rel(self, directory: str) -> str:
        """Normalize a directory argument; reject paths outside the bundle."""
        rel = posixpath.normpath(directory.strip().strip("/") or ".")
        if rel == ".." or rel.startswith("../"):
            raise ValueError(f"'{directory}' is outside the bundle directory")
        return rel

    def listdir(self, directory: str = "") -> dict[str, Any]:
        """Concepts and subdirectories directly inside a bundle directory.

        Every path is bundle-relative, so a concept ``id`` can be passed
        straight to ``read`` and a directory back to ``listdir``.

        Returns:
            ``{"path", "concepts", "directories"}``; concepts are shaped
            like ``entries()``, directories are sorted bundle-relative paths.

        Raises:
            ValueError: If the directory is outside the bundle.
            FileNotFoundError: If the directory does not exist or holds no
                concepts.
        """
        rel = self._directory_rel(directory)
        target = self.path / rel if rel != "." else self.path
        if rel != "." and not target.is_dir():
            concept_ids = {cid for cid, _ in self._concepts()}
            if rel in concept_ids:
                raise FileNotFoundError(f"'{rel}' is a concept, not a directory")
            raise FileNotFoundError(f"Directory '{directory}' not found in the bundle")

        concepts: list[dict[str, str]] = []
        subdirs: set[str] = set()
        prefix = "" if rel == "." else f"{rel}/"
        for concept_id, record in self._concepts():
            if not concept_id.startswith(prefix):
                continue
            head, sep, _rest = concept_id[len(prefix) :].partition("/")
            if sep:
                subdirs.add(prefix + head)
            else:
                concepts.append(_entry(concept_id, record.frontmatter))

        if not concepts and not subdirs:
            if rel in self.ids():
                raise FileNotFoundError(f"'{rel}' is a concept, not a directory")
            raise FileNotFoundError(f"No concepts under '{directory or '/'}'")
        return {
            "path": "" if rel == "." else rel,
            "concepts": concepts,
            "directories": sorted(subdirs),
        }

    def browse(self, directory: str = "") -> str:
        """Return the ``index.md`` of a bundle directory (``""`` is the root).

        When the directory has no ``index.md`` file, the same listing is
        generated from the loaded concepts.

        Raises:
            ValueError: If the directory is outside the bundle.
            FileNotFoundError: If the directory does not exist or holds no
                concepts.
        """
        rel = self._directory_rel(directory)
        target = self.path / rel if rel != "." else self.path
        concept_ids = {cid for cid, _ in self._concepts()}
        if rel != "." and not target.is_dir():
            if rel in concept_ids:
                raise FileNotFoundError(f"'{rel}' is a concept, not a directory")
            raise FileNotFoundError(f"Directory '{directory}' not found in the bundle")

        index_file = target / "index.md"
        if index_file.is_file():
            return index_file.read_text(encoding="utf-8")

        processed = [
            (
                Path(entry["id"] + ".md"),
                {"title": entry["title"], "description": entry["description"]},
            )
            for entry in self.entries()
        ]
        dir_path = Path(".") if rel == "." else Path(rel)
        text = _index_texts(processed).get(dir_path)
        if text is None:
            raise FileNotFoundError(f"No concepts under '{directory or '/'}'")
        return text

    def write(self, concept_id: str, frontmatter: dict[str, Any], body: str) -> Path:
        """``write_concept`` into this bundle, then ``refresh()``."""
        path = write_concept(self.path, concept_id, frontmatter, body)
        self.refresh()
        return path


def list_concepts(bundle_dir: str | Path) -> list[str]:
    """List all concept IDs in an OKF-conformant bundle.

    Args:
        bundle_dir: Path to an OKF bundle directory.

    Returns:
        Sorted list of concept IDs (bundle-relative path with .md stripped).

    Raises:
        ValueError: If the directory is not a valid OKF bundle.
    """
    return Bundle.open(bundle_dir).ids()


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
    return Bundle.open(bundle_dir).entries()


def search(
    bundle_dir: str | Path,
    query: str = "",
    *,
    type_: str | None = None,
    filters: dict[str, Any] | None = None,
    limit: int | None = 20,
) -> list[dict[str, str]]:
    """Search a bundle once. See ``Bundle.search`` for matching and ranking.

    For repeated searches, open a ``Bundle`` and call ``search`` on it.
    """
    return Bundle.open(bundle_dir).search(
        query, type_=type_, filters=filters, limit=limit
    )


def show_concept(
    bundle_dir: str | Path, concept_id: str, *, section: str | None = None
) -> ConceptContent:
    """Read a concept by its ID from an OKF bundle.

    Args:
        bundle_dir: Path to an OKF bundle directory.
        concept_id: Concept ID (e.g. ``tables/orders``).
        section: Optional heading; return only that section as ``body``.

    Returns:
        ConceptContent with parsed frontmatter, body, and raw text.

    Raises:
        ValueError: If bundle is not conformant, the ID is unsafe or
            reserved, or the section does not exist.
        FileNotFoundError: If concept file does not exist.
    """
    return Bundle.open(bundle_dir).read(concept_id, section=section)


def _render_concept(frontmatter: dict[str, Any], body: str) -> str:
    return f"{dump_frontmatter(frontmatter)}\n\n{body}"


def validate_concept(frontmatter: dict[str, Any], body: str) -> ValidateResult:
    """Check one concept before it is written (OKF v0.2 §11 rules).

    The frontmatter is rendered to YAML and parsed back, so values that
    YAML cannot represent — or that break the frontmatter block — are
    reported as errors too.

    Returns:
        ValidateResult with ``total_files=1``.
    """
    if not isinstance(frontmatter, dict):
        return ValidateResult(1, ["frontmatter must be a mapping"])
    if not isinstance(body, str):
        return ValidateResult(1, ["body must be a string"])
    try:
        text = _render_concept(frontmatter, body)
        text.encode("utf-8")
    except (yaml.YAMLError, ValueError, TypeError) as exc:
        return ValidateResult(1, [f"frontmatter cannot be written as YAML: {exc}"])

    problems, parsed = check_file("concept.md", text)
    if not problems and parsed != frontmatter:
        problems.append("frontmatter does not survive a YAML round trip")
    return ValidateResult(1, problems)


def write_concept(
    bundle_dir: str | Path,
    concept_id: str,
    frontmatter: dict[str, Any],
    body: str,
) -> Path:
    """Write one concept file exactly as given, replacing any existing one.

    Unlike ``bundle``/``convert_*``, every frontmatter key is kept as given,
    including ``type`` and ``generated``. ``type``, ``title`` and
    ``description`` are written first. The file is written to a temporary
    file in the same directory and moved into place, so readers never see a
    half-written concept. ``index.md`` files are not updated; call
    ``reindex`` when done.

    Args:
        bundle_dir: Bundle root (must exist; it may be empty).
        concept_id: Target ID, e.g. ``features/import/declaration-entry``.
        frontmatter: Must contain a non-empty string ``type``.
        body: Markdown body.

    Returns:
        Path of the written file.

    Raises:
        NotADirectoryError: If bundle_dir is not a directory.
        ValueError: Unsafe or reserved ID, or the concept is not valid.
    """
    root = Path(bundle_dir)
    if not root.is_dir():
        raise NotADirectoryError(f"'{root}' is not a directory")
    path = _concept_file(root, concept_id)

    report = validate_concept(frontmatter, body)
    if not report.ok:
        raise ValueError(
            f"invalid concept '{concept_id}':\n" + "\n".join(report.errors)
        )

    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            handle.write(_render_concept(frontmatter, body))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    except BaseException:
        Path(tmp_name).unlink(missing_ok=True)
        raise
    return path


def validate(bundle_dir: str | Path) -> ValidateResult:
    """Check whether a directory conforms to the OKF v0.2 specification (§11).

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
