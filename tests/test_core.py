"""Unit tests for shared OKF parsing, formatting, and conformance helpers."""

import json
from pathlib import Path

from okf.core import (
    build_frontmatter,
    check_conformance,
    parse_frontmatter,
    parse_md,
    yaml_val,
)

# --- yaml_val ---


def test_yaml_val_returns_json_string():
    value = 'Has: colons and "quotes"'
    encoded = yaml_val(value)

    assert json.loads(encoded) == value


# --- build_frontmatter ---


def test_build_frontmatter_basic():
    fm = build_frontmatter("tables", "Orders", "One row.", "2026-07-04T12:00:00")

    assert fm == (
        "---\n"
        'type: "tables"\n'
        'title: "Orders"\n'
        'description: "One row."\n'
        'timestamp: "2026-07-04T12:00:00"\n'
        "---"
    )


def test_build_frontmatter_escapes_special_characters():
    fm = build_frontmatter("ref", "Thing: A", 'Has: colons and "quotes"', "")

    assert 'title: "Thing: A"' in fm
    assert 'description: "Has: colons and \\"quotes\\""' in fm
    assert "timestamp:" not in fm


def test_build_frontmatter_omits_empty_title():
    fm = build_frontmatter("ref", "", "Desc here.", "2026-07-04T12:00:00")

    assert "title:" not in fm
    assert 'type: "ref"' in fm
    assert 'description: "Desc here."' in fm
    assert 'timestamp: "2026-07-04T12:00:00"' in fm


# --- parse_md ---


def test_parse_md_basic():
    text = "# Orders\n\n> One row per order.\n\nBody here."

    assert parse_md(text) == ("Orders", "One row per order.", "Body here.")


def test_parse_md_multiline_description():
    text = "# Orders\n\n> Line one\n> Line two\n\nBody."

    assert parse_md(text) == ("Orders", "Line one Line two", "Body.")


def test_parse_md_no_blank_after_title():
    assert parse_md("# Orders\n> Desc\n\nBody.") == ("Orders", "Desc", "Body.")


def test_parse_md_missing_title_uses_lenient_fallback():
    text = "No hash\n> Desc\n\nBody."

    assert parse_md(text) == ("", "No hash > Desc Body.", text)


def test_parse_md_missing_description_uses_body():
    assert parse_md("# Orders\n\nBody no desc.") == (
        "Orders",
        "Body no desc.",
        "Body no desc.",
    )


def test_parse_md_empty_title_uses_lenient_fallback():
    assert parse_md("# \n> Desc\n\nBody.") == ("", "> Desc Body.", "> Desc\n\nBody.")


def test_parse_md_only_title_and_description():
    assert parse_md("# Orders\n> Just a description") == (
        "Orders",
        "Just a description",
        "",
    )


def test_parse_md_preserves_trailing_newline_in_body():
    assert parse_md("# Orders\n> Desc\n\nBody\n") == ("Orders", "Desc", "Body\n")


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
    (tmp_path / "index.md").write_text('---\nokf_version: "0.1"\n---\n\n# Contents')

    assert check_conformance(tmp_path) == ([], [])


def test_check_conformance_reports_non_utf8_files(tmp_path: Path):
    (tmp_path / "bad.md").write_bytes(b"\xff\xfe")

    errors, warnings = check_conformance(tmp_path)

    assert warnings == []
    assert errors == ["bad.md: file is not valid UTF-8"]
