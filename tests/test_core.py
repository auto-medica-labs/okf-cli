"""Unit tests for shared OKF parsing, formatting, and conformance helpers."""

import json
from pathlib import Path

import pytest
import yaml

from okf.core import (
    build_frontmatter,
    check_conformance,
    parse_frontmatter,
    parse_md,
    parse_md_with_frontmatter,
    yaml_val,
)

# --- yaml_val ---


def test_yaml_val_returns_json_string():
    value = 'Has: colons and "quotes"'
    encoded = yaml_val(value)

    assert json.loads(encoded) == value


# --- build_frontmatter ---


def _load_frontmatter(text: str) -> dict:
    content = text.split("---\n", 1)[1].rsplit("\n---", 1)[0]
    return yaml.safe_load(content)


def test_build_frontmatter_basic():
    fm = build_frontmatter(
        "tables",
        "Orders",
        "One row.",
        {"by": "okf-cli/0.6.0", "at": "2026-07-04T12:00:00"},
    )

    parsed = _load_frontmatter(fm)
    assert parsed == {
        "type": "tables",
        "title": "Orders",
        "description": "One row.",
        "generated": {"by": "okf-cli/0.6.0", "at": "2026-07-04T12:00:00"},
    }


def test_build_frontmatter_escapes_special_characters():
    fm = build_frontmatter("ref", "Thing: A", 'Has: colons and "quotes"', None)

    parsed = _load_frontmatter(fm)
    assert parsed["type"] == "ref"
    assert parsed["title"] == "Thing: A"
    assert parsed["description"] == 'Has: colons and "quotes"'
    assert "generated" not in parsed


def test_build_frontmatter_omits_empty_title():
    fm = build_frontmatter(
        "ref", "", "Desc here.", {"by": "okf-cli/0.6.0", "at": "2026-07-04T12:00:00"}
    )

    parsed = _load_frontmatter(fm)
    assert "title" not in parsed
    assert parsed["type"] == "ref"
    assert parsed["description"] == "Desc here."
    assert parsed["generated"] == {
        "by": "okf-cli/0.6.0",
        "at": "2026-07-04T12:00:00",
    }


def test_build_frontmatter_preserves_extras():
    fm = build_frontmatter(
        "ref",
        "Title",
        "Desc",
        None,
        extras={
            "tags": ["a", "b"],
            "resource": "https://example.com",
            "status": "stable",
        },
    )

    parsed = _load_frontmatter(fm)
    assert parsed["type"] == "ref"
    assert parsed["title"] == "Title"
    assert parsed["description"] == "Desc"
    assert parsed["tags"] == ["a", "b"]
    assert parsed["resource"] == "https://example.com"
    assert parsed["status"] == "stable"


def test_build_frontmatter_drops_reserved_extras():
    fm = build_frontmatter(
        "ref",
        "Title",
        "Desc",
        {"by": "okf-cli/1.0", "at": "2026-01-01T00:00:00"},
        extras={
            "type": "ignored",
            "generated": {"by": "ignored", "at": "ignored"},
            "okf_version": "0.2",
            "custom": "kept",
        },
    )

    parsed = _load_frontmatter(fm)
    assert parsed["type"] == "ref"
    assert parsed["generated"] == {"by": "okf-cli/1.0", "at": "2026-01-01T00:00:00"}
    assert "okf_version" not in parsed
    assert parsed["custom"] == "kept"


# --- parse_md ---


def test_parse_md_basic():
    text = "# Orders\n\n> One row per order.\n\nBody here."

    title, description, body = parse_md(text)
    assert title == "Orders"
    assert description == "One row per order."
    assert body == text


def test_parse_md_multiline_description():
    text = "# Orders\n\n> Line one\n> Line two\n\nBody."

    title, description, body = parse_md(text)
    assert title == "Orders"
    assert description == "Line one Line two"
    assert body == text


def test_parse_md_no_blank_after_title():
    text = "# Orders\n> Desc\n\nBody."

    title, description, body = parse_md(text)
    assert title == "Orders"
    assert description == "Desc"
    assert body == text


def test_parse_md_missing_title_uses_lenient_fallback():
    text = "No hash\n> Desc\n\nBody."

    assert parse_md(text) == ("", "No hash > Desc Body.", text)


def test_parse_md_missing_description_uses_body():
    text = "# Orders\n\nBody no desc."

    title, description, body = parse_md(text)
    assert title == "Orders"
    assert description == "Body no desc."
    assert body == text


def test_parse_md_empty_title_uses_lenient_fallback():
    text = "# \n> Desc\n\nBody."

    title, description, body = parse_md(text)
    assert title == ""
    assert description == "> Desc Body."
    assert body == text


def test_parse_md_only_title_and_description():
    text = "# Orders\n> Just a description"

    title, description, body = parse_md(text)
    assert title == "Orders"
    assert description == "Just a description"
    assert body == text


def test_parse_md_preserves_trailing_newline_in_body():
    text = "# Orders\n> Desc\n\nBody\n"

    title, description, body = parse_md(text)
    assert title == "Orders"
    assert description == "Desc"
    assert body == text


def test_parse_md_truncates_lenient_description():
    long_body = "x" * 120

    assert parse_md(long_body) == ("", "x" * 80 + "...", long_body)


def test_parse_md_empty_file():
    assert parse_md("") == ("", "", "")


# --- parse_frontmatter ---


def test_parse_frontmatter_basic():
    text = "---\ntype: table\ntitle: Orders\n---\n\nBody."

    assert parse_frontmatter(text) == {"type": "table", "title": "Orders"}


def test_parse_frontmatter_missing_opening():
    assert parse_frontmatter("type: table\n---\nBody.") is None


def test_parse_frontmatter_missing_closing():
    assert parse_frontmatter("---\ntype: table\nBody.") is None


def test_parse_frontmatter_empty():
    assert parse_frontmatter("---\n---\nBody.") == {}


def test_parse_frontmatter_empty_file():
    assert parse_frontmatter("") is None


def test_parse_frontmatter_supports_yaml_values():
    text = "---\ntype: table\ntags: [sales, orders]\n---\n\nBody."

    assert parse_frontmatter(text) == {
        "type": "table",
        "tags": ["sales", "orders"],
    }


def test_parse_frontmatter_malformed_yaml():
    text = '---\ntype: table\ntitle: "unclosed\n---\n\nBody.'

    assert parse_frontmatter(text) is None


def test_parse_frontmatter_rejects_non_dict():
    text = "---\n- just\n- a\n- list\n---\n\nBody."

    assert parse_frontmatter(text) is None


# --- check_conformance ---


def test_check_conformance_accepts_valid_bundle(tmp_path: Path):
    (tmp_path / "concept.md").write_text("---\ntype: ref\n---\n\nBody.")
    (tmp_path / "index.md").write_text("# Contents")
    (tmp_path / "log.md").write_text("## 2026-01-01")

    assert check_conformance(tmp_path) == ([], [])


def test_check_conformance_requires_frontmatter_and_type(tmp_path: Path):
    (tmp_path / "missing.md").write_text("# Title\n\nBody.")
    (tmp_path / "no_type.md").write_text("---\ntitle: Thing\n---\n\nBody.")
    (tmp_path / "empty_type.md").write_text("---\ntype: \n---\n\nBody.")

    errors, warnings = check_conformance(tmp_path)

    assert warnings == []
    assert errors == [
        "empty_type.md: frontmatter missing non-empty 'type' field",
        "missing.md: missing or unparseable YAML frontmatter",
        "no_type.md: frontmatter missing non-empty 'type' field",
    ]


def test_check_conformance_validates_reserved_frontmatter(tmp_path: Path):
    (tmp_path / "index.md").write_text("---\ntitle: Wrong\n---\n\n# Contents")
    (tmp_path / "nested").mkdir()
    (tmp_path / "nested" / "index.md").write_text("---\ntype: index\n---\n")
    (tmp_path / "log.md").write_text("---\nversion: 1\n---\n")

    errors, warnings = check_conformance(tmp_path)

    assert warnings == []
    assert errors == [
        "index.md: index.md frontmatter may only contain 'okf_version' (§11)",
        "log.md: log.md must not contain frontmatter (§7)",
        "nested/index.md: index.md must not contain frontmatter (§6)",
    ]


def test_check_conformance_allows_only_okf_version_in_root_index(tmp_path: Path):
    (tmp_path / "index.md").write_text('---\nokf_version: "0.2"\n---\n\n# Contents')

    assert check_conformance(tmp_path) == ([], [])


def test_check_conformance_reports_non_utf8_files(tmp_path: Path):
    (tmp_path / "bad.md").write_bytes(b"\xff\xfe")

    errors, warnings = check_conformance(tmp_path)

    assert warnings == []
    assert errors == ["bad.md: file is not valid UTF-8"]


# --- parse_md_with_frontmatter ---


def test_parse_md_with_frontmatter_basic():
    text = "---\ntype: ref\ntags: [a, b]\n---\n\n# Title\n\n> Desc\n\nBody."

    fm, title, description, body = parse_md_with_frontmatter(text)

    assert fm == {"type": "ref", "tags": ["a", "b"]}
    assert title == "Title"
    assert description == "Desc"
    assert body == "# Title\n\n> Desc\n\nBody."


def test_parse_md_with_frontmatter_no_frontmatter():
    text = "# Title\n\n> Desc\n\nBody."

    fm, title, description, body = parse_md_with_frontmatter(text)

    assert fm == {}
    assert title == "Title"
    assert description == "Desc"
    assert body == text


def test_parse_md_with_frontmatter_title_override():
    text = "---\ntitle: Frontmatter Title\n---\n\n# Body Title\n\n> Desc\n\nBody."

    fm, title, description, body = parse_md_with_frontmatter(text)

    assert fm == {"title": "Frontmatter Title"}
    assert title == "Body Title"
    assert description == "Desc"
    assert body == "# Body Title\n\n> Desc\n\nBody."


def test_parse_md_with_frontmatter_empty_frontmatter():
    text = "---\n---\n\n# Title\n\n> Desc\n\nBody."

    fm, title, description, body = parse_md_with_frontmatter(text)

    assert fm == {}
    assert title == "Title"


def test_parse_md_with_frontmatter_malformed_normal_fallback():
    text = "---\ntype: [unclosed\n---\n\n# Title\n\n> Desc\n\nBody."

    fm, title, description, body = parse_md_with_frontmatter(text)

    assert fm == {}
    assert "---" in body


def test_parse_md_with_frontmatter_malformed_strict_raises():
    text = "---\ntype: [unclosed\n---\n\n# Title\n\n> Desc\n\nBody."

    with pytest.raises(ValueError, match="Malformed YAML frontmatter"):
        parse_md_with_frontmatter(text, strict=True)


def test_parse_md_with_frontmatter_unclosed_strict_raises():
    text = "---\ntype: ref\n\n# Title\n\nBody."

    with pytest.raises(ValueError, match="Unclosed frontmatter"):
        parse_md_with_frontmatter(text, strict=True)


def test_parse_md_with_frontmatter_non_dict_strict_raises():
    text = "---\n- one\n- two\n---\n\nBody."

    with pytest.raises(ValueError, match="YAML mapping"):
        parse_md_with_frontmatter(text, strict=True)
