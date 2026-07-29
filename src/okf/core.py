"""Shared OKF parsing and formatting utilities."""

import json
from pathlib import Path
from typing import Any

import yaml
from rich.console import Console

console = Console()
err_console = Console(stderr=True)

RESERVED = frozenset({"index.md", "log.md", "readme.md"})
SPEC_RESERVED = frozenset({"index.md", "log.md", "agents.md"})


def yaml_val(v: str) -> str:
    """Format a string value as valid YAML via JSON encoding."""
    return json.dumps(v, ensure_ascii=True)


def build_frontmatter(
    type_: str,
    title: str,
    description: str,
    generated: dict[str, str] | None = None,
    extras: dict[str, Any] | None = None,
) -> str:
    """Render OKF concept frontmatter as a YAML block.

    ``extras`` are producer-defined keys preserved from input frontmatter.
    ``type``, ``generated``, and ``okf_version`` are ignored inside ``extras``;
    input ``title``/``description`` should already have been applied by the
    caller if desired.
    """
    data: dict[str, Any] = {"type": type_}
    if title:
        data["title"] = title
    data["description"] = description
    if generated:
        data["generated"] = generated
    for key, value in (extras or {}).items():
        if key in {"type", "title", "description", "generated", "okf_version"}:
            continue
        data[key] = value

    yaml_text = yaml.safe_dump(
        data,
        sort_keys=False,
        default_flow_style=False,
        allow_unicode=True,
    ).rstrip("\n")
    return f"---\n{yaml_text}\n---"


def _parse_strict(text: str) -> tuple[str, str, str]:
    """Parse strict: line 1 must be '# Title' followed by '>' block.

    Raises ValueError on format violation.
    """
    lines = text.splitlines(keepends=True)

    if not lines or not lines[0].startswith("# "):
        raise ValueError("Line 1 must be '# Title'")

    title = lines[0][2:].strip()
    if not title:
        raise ValueError("Title cannot be empty")

    i = 1
    while i < len(lines) and not lines[i].strip():
        i += 1

    desc_lines = []
    while i < len(lines) and lines[i].startswith(">"):
        content = lines[i][1:].strip()
        desc_lines.append(content)
        i += 1

    if not desc_lines:
        raise ValueError("Must have a '> description' block after title")

    description = " ".join(desc_lines).strip()

    while i < len(lines) and not lines[i].strip():
        i += 1

    body = "".join(lines[i:])

    return title, description, body


def _parse_lenient(text: str) -> tuple[str, str, str]:
    """Parse lenient: best-effort title from line 0, description from body.

    Never raises.
    """
    lines = text.splitlines(keepends=True)

    if lines and lines[0].startswith("# "):
        title = lines[0][2:].strip()
        rest = "".join(lines[1:])
    else:
        title = ""
        rest = text

    body = rest.strip()

    if body:
        collapsed = " ".join(body.split())
        desc = collapsed[:80]
        if len(collapsed) > 80:
            desc = desc.rstrip() + "..."
    else:
        desc = ""

    return title, desc, body


def parse_md(text: str) -> tuple[str, str, str]:
    """Parse title, description, body from plain markdown.

    Tries strict parsing first (line 1 '# Title', '>' block).
    Falls back to lenient: title from line 0 if present, description
    derived from first 80 chars of body.

    Returns (title, description, body). Never raises.
    """
    try:
        return _parse_strict(text)
    except ValueError:
        return _parse_lenient(text)


def parse_md_with_frontmatter(
    text: str,
    *,
    strict: bool = False,
) -> tuple[dict[str, Any], str, str, str]:
    """Parse frontmatter, title, description, and body from markdown.

    If the file starts with ``---``, the region up to the next ``---`` on its
    own line is parsed as YAML frontmatter and stripped before ``parse_md()``
    sees the body.

    In normal mode a malformed or unclosed frontmatter block falls back to
    treating the whole file as plain markdown. In ``strict`` mode it raises
    ``ValueError``.

    Returns (frontmatter_dict, title, description, body). ``frontmatter_dict``
    is empty when there is no parseable frontmatter.
    """
    if not text.startswith("---"):
        return {}, *parse_md(text)

    lines = text.split("\n")
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            content = "\n".join(lines[1:i])
            try:
                frontmatter = yaml.safe_load(content)
            except yaml.YAMLError as exc:
                if strict:
                    raise ValueError(f"Malformed YAML frontmatter: {exc}") from exc
                return {}, *parse_md(text)

            if frontmatter is None:
                frontmatter = {}
            elif not isinstance(frontmatter, dict):
                if strict:
                    raise ValueError("Frontmatter must be a YAML mapping")
                return {}, *parse_md(text)

            body_source = "\n".join(lines[i + 1 :]).lstrip("\n")
            title, description, body = parse_md(body_source)
            return frontmatter, title, description, body

    if strict:
        raise ValueError("Unclosed frontmatter block")
    return {}, *parse_md(text)


def parse_frontmatter(text: str) -> dict[str, Any] | None:
    """Parse YAML frontmatter from an OKF concept file.

    Returns dict of key-value pairs, or None if frontmatter is missing
    or malformed (no opening ---, no closing ---, or invalid YAML).
    """
    lines = text.split("\n")
    if not lines or lines[0].strip() != "---":
        return None

    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            content = "\n".join(lines[1:i])
            try:
                result = yaml.safe_load(content)
            except yaml.YAMLError:
                return None
            if result is None:
                return {}
            if not isinstance(result, dict):
                return None
            return result

    return None


def check_conformance(dir_path: Path) -> tuple[list[str], list[str]]:
    """Check OKF v0.2 conformance for a directory (§11).

    Returns (errors, warnings).  An empty directory produces no errors.

    §9 rules enforced:
    1. Every non-reserved .md file must have parseable YAML frontmatter.
    2. Every frontmatter must contain a non-empty 'type' field.
    3. Reserved filenames (index.md, log.md) follow spec structure:
       - index.md must not contain frontmatter (§6), except root
         index.md may contain only 'okf_version' (§11).
       - log.md must not contain frontmatter (§7).
    """
    errors: list[str] = []
    warnings: list[str] = []
    for f in sorted(dir_path.rglob("*.md")):
        rel = str(f.relative_to(dir_path))
        name_lower = f.name.lower()
        try:
            text = f.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            errors.append(f"{rel}: file is not valid UTF-8")
            continue

        if name_lower in SPEC_RESERVED:
            if name_lower == "agents.md":
                continue

            fm = parse_frontmatter(text)

            if name_lower == "index.md" and fm is not None:
                if rel == "index.md":
                    # Root index.md — only okf_version allowed per §11
                    extra = set(fm.keys()) - {"okf_version"}
                    if extra:
                        errors.append(
                            f"{rel}: index.md frontmatter may only contain "
                            f"'okf_version' (§11)"
                        )
                else:
                    errors.append(f"{rel}: index.md must not contain frontmatter (§6)")

            elif name_lower == "log.md" and fm is not None:
                errors.append(f"{rel}: log.md must not contain frontmatter (§7)")
        else:
            fm = parse_frontmatter(text)
            if fm is None:
                errors.append(f"{rel}: missing or unparseable YAML frontmatter")
            elif not isinstance(fm.get("type"), str) or not str(fm["type"]).strip():
                errors.append(f"{rel}: frontmatter missing non-empty 'type' field")

    return errors, warnings
