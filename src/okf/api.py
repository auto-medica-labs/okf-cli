"""Python API for okf-cli — programmatic access without typer."""

from __future__ import annotations

import os
import posixpath
import re
import shutil
import tempfile
from dataclasses import dataclass, field
from datetime import UTC, datetime
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


def _generate_indexes(
    processed: list[tuple[Path, dict]], dst: Path, *, overwrite: bool = False
) -> int:
    """Generate index.md for every directory with concept files or subdirs.

    Returns the number of index files written. Existing index files are kept
    unless ``overwrite`` is true.
    """
    written = 0
    for dir_path, text in _index_texts(processed).items():
        index_path = dst / dir_path / "index.md"
        if index_path.exists() and not overwrite:
            continue
        index_path.parent.mkdir(parents=True, exist_ok=True)
        index_path.write_text(text, encoding="utf-8")
        written += 1
    return written


def _index_texts(processed: list[tuple[Path, dict]]) -> dict[Path, str]:
    """Render the index.md text of every directory with concepts or subdirs."""
    dir_files: dict[Path, list[dict]] = {}
    dir_subdirs: dict[Path, set[str]] = {}
    texts: dict[Path, str] = {}

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

        if not dry_run:
            _generate_indexes(processed, build_dir)

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

        if not dry_run:
            replaced = _commit_staged_bundle(staging_dir, dst)
            if replaced:
                warnings.append(f"Replaced existing '{dst}'")
    finally:
        if staging_dir is not None and _path_exists(staging_dir):
            _remove_path(staging_dir)

    return BundleResult(
        files_written=len(processed),
        output_dir=dst,
        warnings=warnings,
        errors=errors,
    )


def reindex(bundle_dir: str | Path) -> BundleResult:
    """Rebuild every index.md in a bundle from the concept files on disk.

    Args:
        bundle_dir: Path to an OKF bundle directory.

    Returns:
        BundleResult with ``files_written`` set to the number of index files
        written and ``output_dir`` set to ``bundle_dir``.

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
    count = _generate_indexes(processed, dst, overwrite=True)
    return BundleResult(files_written=count, output_dir=dst)


# ---------------------------------------------------------------------------
# Loaded bundle: one conformance pass, then repeated reads and searches
# ---------------------------------------------------------------------------

# Search relevance per frontmatter key; unlisted keys weigh 1.
_FIELD_WEIGHTS = {"title": 3, "tags": 2, "description": 2}
# Provenance metadata, not content: never matched by search.
_UNSEARCHED_KEYS = frozenset({"generated", "verified"})
_ID_WEIGHT = 3
_EXACT_BONUS = 5
_HEADING_RE = re.compile(r"^(#{1,6})[ \t]+(.*?)(?:[ \t]+#+)?[ \t]*$")
_FENCE_RE = re.compile(r"^[ \t]{0,3}(`{3,}|~{3,})")


@dataclass
class _FileState:
    stamp: tuple[int, int, int]
    errors: list[str]
    concept_id: str | None = None
    frontmatter: dict[str, Any] = field(default_factory=dict)
    fields: list[tuple[int, str]] = field(default_factory=list)


def _strings(value: Any) -> list[str]:
    """Every string inside a frontmatter value, including nested lists/maps."""
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [s for v in value.values() for s in _strings(v)]
    if isinstance(value, list | tuple):
        return [s for v in value for s in _strings(v)]
    return []


def _search_fields(concept_id: str, fm: dict[str, Any]) -> list[tuple[int, str]]:
    """(weight, casefolded text) pairs that search matches against."""
    fields = [(_ID_WEIGHT, concept_id.casefold())]
    for key, value in fm.items():
        if key in _UNSEARCHED_KEYS:
            continue
        weight = _FIELD_WEIGHTS.get(key, 1)
        fields.extend((weight, s.casefold()) for s in _strings(value))
    return fields


def _matches_filter(actual: Any, expected: Any) -> bool:
    """Equality for scalars; membership for list-valued frontmatter keys."""
    values = actual if isinstance(actual, list) else [actual]
    return any(v is not None and str(v) == str(expected) for v in values)


def _entry(concept_id: str, fm: dict[str, Any]) -> dict[str, str]:
    return {
        "id": concept_id,
        "type": str(fm.get("type", "")),
        "title": str(fm.get("title", "")),
        "description": str(fm.get("description", "")),
    }


def _split_body(raw: str) -> str:
    """Return the markdown after the frontmatter block."""
    if raw.startswith("---"):
        lines = raw.split("\n")
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                return "\n".join(lines[i + 1 :]).lstrip("\n")
    return raw


def _headings(lines: list[str]) -> list[tuple[int, int, str]]:
    """(line index, level, text) of every ATX heading outside fenced code."""
    found: list[tuple[int, int, str]] = []
    fence: str | None = None
    for i, line in enumerate(lines):
        stripped = line.rstrip("\r\n")
        fence_match = _FENCE_RE.match(stripped)
        if fence_match:
            marker = fence_match.group(1)[0]
            if fence is None:
                fence = marker
            elif marker == fence:
                fence = None
            continue
        if fence is not None:
            continue
        heading = _HEADING_RE.match(stripped)
        if heading:
            found.append((i, len(heading.group(1)), heading.group(2).strip()))
    return found


def _extract_section(body: str, section: str) -> str | None:
    """Return one section (its heading through the next same-or-higher heading)."""
    lines = body.splitlines(keepends=True)
    headings = _headings(lines)
    wanted = section.strip().lstrip("#").strip().casefold()
    for n, (start, level, text) in enumerate(headings):
        if text.casefold() == wanted:
            end = next(
                (i for i, lvl, _ in headings[n + 1 :] if lvl <= level), len(lines)
            )
            return "".join(lines[start:end]).rstrip("\n") + "\n"
    return None


def _concept_path(dir_path: Path, concept_id: str) -> Path:
    """Resolve a concept ID to its file, rejecting unsafe or reserved IDs.

    A leading ``/`` (link style) and a trailing ``.md`` are accepted.
    """
    cid = concept_id.strip().lstrip("/")
    if cid.lower().endswith(".md"):
        cid = cid[:-3]
    if not cid:
        raise ValueError("concept ID must not be empty")

    path = dir_path / f"{cid}.md"
    try:
        path.resolve().relative_to(dir_path.resolve())
    except ValueError:
        raise ValueError(f"'{concept_id}' is outside the bundle directory") from None
    if path.name.lower() in SPEC_RESERVED:
        raise ValueError(f"'{concept_id}' is a reserved filename, not a concept")
    return path


def _sort_key(rel: str) -> tuple[str, ...]:
    """Order paths like ``sorted(Path.rglob())`` does (by path components)."""
    return PurePosixPath(rel).parts


class Bundle:
    """A conformant OKF bundle held in memory for repeated reads and searches.

    ``Bundle.open`` checks conformance once and indexes every concept's
    frontmatter. Later calls do not rescan the directory; call ``refresh()``
    to pick up files that another process changed (only changed files are
    re-read). ``write()`` refreshes by itself.
    """

    def __init__(self, path: Path) -> None:
        self.path = path
        self._files: dict[str, _FileState] = {}

    @classmethod
    def open(cls, bundle_dir: str | Path) -> Bundle:
        """Load a bundle.

        Raises:
            NotADirectoryError: If bundle_dir is not a directory.
            ValueError: If the bundle is not OKF-conformant.
        """
        path = Path(bundle_dir)
        if not path.is_dir():
            raise NotADirectoryError(f"'{path}' is not a directory")
        loaded = cls(path)
        loaded.refresh()
        return loaded

    def refresh(self) -> bool:
        """Re-read files added, changed or removed since the last load.

        Returns whether anything changed.

        Raises:
            ValueError: If the bundle is no longer OKF-conformant.
        """
        current: dict[str, _FileState] = {}
        changed = False
        for f in self.path.rglob("*.md"):
            st = f.stat()
            stamp = (st.st_mtime_ns, st.st_size, st.st_ino)
            rel = f.relative_to(self.path).as_posix()
            known = self._files.get(rel)
            if known is not None and known.stamp == stamp:
                current[rel] = known
                continue
            current[rel] = self._load(f, rel, stamp)
            changed = True

        changed = changed or current.keys() != self._files.keys()
        self._files = current
        errors = [
            error
            for rel in sorted(current, key=_sort_key)
            for error in current[rel].errors
        ]
        if errors:
            raise ValueError("not an OKF-conformant bundle:\n" + "\n".join(errors))
        return changed

    @staticmethod
    def _load(f: Path, rel: str, stamp: tuple[int, int, int]) -> _FileState:
        try:
            text = f.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return _FileState(stamp, [f"{rel}: file is not valid UTF-8"])
        problems, fm = check_file(rel, text)
        state = _FileState(stamp, [f"{rel}: {p}" for p in problems])
        if f.name.lower() not in SPEC_RESERVED and fm is not None:
            state.concept_id = rel[:-3]
            state.frontmatter = fm
            state.fields = _search_fields(state.concept_id, fm)
        return state

    def _concepts(self) -> list[_FileState]:
        return [
            self._files[rel]
            for rel in sorted(self._files, key=_sort_key)
            if self._files[rel].concept_id is not None
        ]

    def ids(self) -> list[str]:
        """Sorted concept IDs."""
        return [c.concept_id for c in self._concepts()]

    def entries(self) -> list[dict[str, str]]:
        """Sorted ``{id, type, title, description}`` for every concept."""
        return [_entry(c.concept_id, c.frontmatter) for c in self._concepts()]

    def search(
        self,
        query: str = "",
        *,
        type_: str | None = None,
        filters: dict[str, Any] | None = None,
        limit: int | None = 20,
    ) -> list[dict[str, str]]:
        """Find concepts whose frontmatter or ID contains the query words.

        Each word of ``query`` is matched case-insensitively as a substring of
        the concept ID, title, description, tags and every other frontmatter
        string (nested values included; ``generated``/``verified`` excluded).
        Concepts matching more words rank first, then by field weight (ID and
        title > tags and description > other keys); a field equal to the
        whole query ranks highest. An empty query returns every concept that
        passes the filters, sorted by ID.

        Args:
            query: Space-separated words.
            type_: Only concepts with this ``type``.
            filters: Frontmatter key -> required value. A list-valued key
                matches when it contains the value.
            limit: Maximum results; ``None`` for all.

        Returns:
            Entries shaped like ``entries()``, best match first.
        """
        terms = query.casefold().split()
        whole = " ".join(terms)
        ranked: list[tuple[int, int, str, dict[str, str]]] = []
        for c in self._concepts():
            fm = c.frontmatter
            if type_ is not None and fm.get("type") != type_:
                continue
            if filters and not all(
                _matches_filter(fm.get(k), v) for k, v in filters.items()
            ):
                continue
            matched = score = 0
            for term in terms:
                best = max((w for w, text in c.fields if term in text), default=0)
                if best:
                    matched += 1
                    score += best
            if terms and not matched:
                continue
            if terms and any(text == whole for _w, text in c.fields):
                score += _EXACT_BONUS
            ranked.append((-matched, -score, c.concept_id, _entry(c.concept_id, fm)))
        ranked.sort(key=lambda r: r[:3])
        results = [r[3] for r in ranked]
        return results if limit is None else results[: max(limit, 0)]

    def read(self, concept_id: str, *, section: str | None = None) -> ConceptContent:
        """Read one concept, or only one of its sections.

        With ``section``, ``body`` holds that section only: its heading line
        through the line before the next heading of the same or a higher
        level. The heading is matched case-insensitively, without ``#``s.
        ``raw`` is always the whole file.

        Raises:
            ValueError: Unsafe or reserved ID, or the section does not exist.
            FileNotFoundError: The concept does not exist.
        """
        path = _concept_path(self.path, concept_id)
        if not path.is_file():
            raise FileNotFoundError(f"Concept '{concept_id}' not found")

        raw = path.read_text(encoding="utf-8")
        fm = parse_frontmatter(raw) or {}
        body = _split_body(raw)
        if section is not None:
            part = _extract_section(body, section)
            if part is None:
                names = [t for _i, _l, t in _headings(body.splitlines())]
                available = ", ".join(names) if names else "none"
                raise ValueError(
                    f"Section '{section}' not found in '{concept_id}'. "
                    f"Available: {available}"
                )
            body = part
        return ConceptContent(frontmatter=fm, body=body, raw=raw)

    def browse(self, directory: str = "") -> str:
        """Return the ``index.md`` of a bundle directory (``""`` is the root).

        When the directory has no ``index.md`` file, the same listing is
        generated from the loaded concepts.

        Raises:
            ValueError: If the directory is outside the bundle.
            FileNotFoundError: If the directory holds no concepts.
        """
        rel = directory.strip().strip("/") or "."
        target = self.path / rel
        try:
            target.resolve().relative_to(self.path.resolve())
        except ValueError:
            raise ValueError(f"'{directory}' is outside the bundle directory") from None

        index_file = target / "index.md"
        if index_file.is_file():
            return index_file.read_text(encoding="utf-8")

        processed = [
            (
                Path(e["id"] + ".md"),
                {"title": e["title"], "description": e["description"]},
            )
            for e in self.entries()
        ]
        text = _index_texts(processed).get(Path(rel))
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

    The frontmatter is rendered to YAML and parsed back, so values that YAML
    cannot represent, or that break the ``---`` block, are reported too.

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
    except (yaml.YAMLError, ValueError, TypeError) as e:
        return ValidateResult(1, [f"frontmatter cannot be written as YAML: {e}"])

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
    file and moved into place, so readers never see a partial concept.
    ``index.md`` files are not updated; call ``reindex`` when done.

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
    dir_path = Path(bundle_dir)
    if not dir_path.is_dir():
        raise NotADirectoryError(f"'{dir_path}' is not a directory")
    path = _concept_path(dir_path, concept_id)

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
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as fh:
            fh.write(_render_concept(frontmatter, body))
            fh.flush()
            os.fsync(fh.fileno())
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
