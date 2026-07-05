"""Shared OKF parsing and formatting utilities."""

import json
from pathlib import Path
from typing import Any

import yaml

RESERVED = frozenset({"index.md", "log.md", "readme.md"})
SPEC_RESERVED = frozenset({"index.md", "log.md"})


def yaml_val(v: str) -> str:
    """Format a string value as valid YAML via JSON encoding."""
    return json.dumps(v, ensure_ascii=True)


def build_frontmatter(type_: str, title: str, description: str, timestamp: str) -> str:
    parts = [
        "---",
        f"type: {yaml_val(type_)}",
        f"title: {yaml_val(title)}",
        f"description: {yaml_val(description)}",
    ]
    if timestamp:
        parts.append(f"timestamp: {yaml_val(timestamp)}")
    parts.append("---")
    return "\n".join(parts)


def parse_md(text: str) -> tuple[str, str, str]:
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
    """Check OKF v0.1 conformance for a directory.

    Returns (errors, warnings).  An empty directory produces no errors.
    """
    errors: list[str] = []
    warnings: list[str] = []
    for f in sorted(dir_path.rglob("*.md")):
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
            elif not isinstance(fm.get("type"), str) or not str(fm["type"]).strip():
                errors.append(f"{rel}: frontmatter missing non-empty 'type' field")

    return errors, warnings
