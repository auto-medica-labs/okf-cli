"""Shared OKF parsing and formatting utilities."""

import json

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


def parse_frontmatter(text: str) -> dict[str, str] | None:
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
