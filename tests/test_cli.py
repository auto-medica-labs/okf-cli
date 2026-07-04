"""Tests for okf bundle CLI."""

import json
from pathlib import Path

from typer.testing import CliRunner

from okf.cli import app, _parse_md, _build_frontmatter

runner = CliRunner()


# --- _parse_md ---


def test_parse_basic():
    text = "# Orders\n\n> One row per order.\n\nBody here."
    title, desc, body = _parse_md(text)
    assert title == "Orders"
    assert desc == "One row per order."
    assert body == "Body here."


def test_parse_multiline_desc():
    text = "# Orders\n\n> Line one\n> Line two\n\nBody."
    title, desc, body = _parse_md(text)
    assert title == "Orders"
    assert desc == "Line one Line two"
    assert body == "Body."


def test_parse_no_blank_after_title():
    text = "# Orders\n> Desc\n\nBody."
    title, desc, body = _parse_md(text)
    assert title == "Orders"
    assert desc == "Desc"
    assert body == "Body."


def test_parse_missing_title():
    text = "No hash\n> Desc\n\nBody."
    try:
        _parse_md(text)
        assert False, "Should raise"
    except ValueError as e:
        assert "Line 1 must be" in str(e)


def test_parse_missing_desc():
    text = "# Orders\n\nBody no desc."
    try:
        _parse_md(text)
        assert False, "Should raise"
    except ValueError as e:
        assert "description" in str(e)


def test_parse_empty_title():
    text = "# \n> Desc\n\nBody."
    try:
        _parse_md(text)
        assert False, "Should raise"
    except ValueError as e:
        assert "empty" in str(e)


def test_parse_only_title_and_desc():
    text = "# Orders\n> Just a description"
    title, desc, body = _parse_md(text)
    assert title == "Orders"
    assert desc == "Just a description"
    assert body == ""


def test_parse_no_trailing_newline():
    text = "# Orders\n> Desc\n\nBody\n"
    title, desc, body = _parse_md(text)
    assert title == "Orders"
    assert desc == "Desc"
    assert body == "Body\n"


# --- _build_frontmatter ---


def test_frontmatter_basic():
    fm = _build_frontmatter("tables", "Orders", "One row.", "2026-07-04T12:00:00")
    assert 'type: "tables"' in fm
    assert 'title: "Orders"' in fm
    assert 'description: "One row."' in fm
    assert 'timestamp: "2026-07-04T12:00:00"' in fm
    assert fm.startswith("---")
    assert fm.endswith("---")


def test_frontmatter_special_chars():
    fm = _build_frontmatter("ref", "Thing: A", 'Has: colons and "quotes"', "")
    assert 'title: "Thing: A"' in fm
    assert 'description: "Has: colons and \\"quotes\\""' in fm
    # json.dumps escapes everything properly
    import json

    assert json.loads(fm.split("\n")[1].split(": ", 1)[1]) == "ref"


# --- CLI integration ---


def _write_fixture(dir: Path, files: dict[str, str]):
    for path, content in files.items():
        p = dir / path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)


def test_bundle_basic(tmp_path: Path):
    src = tmp_path / "notes"
    dst = tmp_path / "bundle"
    src.mkdir()
    _write_fixture(
        src,
        {
            "tables/orders.md": "# Orders\n\n> One row per order.\n\nBody content.",
            "tables/customers.md": "# Customers\n\n> All customers.\n\nMore body.",
        },
    )

    result = runner.invoke(app, ["bundle", str(src), str(dst)])
    assert result.exit_code == 0, result.output

    # Check output structure
    assert (dst / "tables" / "orders.md").exists()
    assert (dst / "tables" / "customers.md").exists()
    assert (dst / "tables" / "index.md").exists()

    # Check frontmatter in orders.md
    orders = (dst / "tables" / "orders.md").read_text()
    assert 'type: "tables"' in orders
    assert 'title: "Orders"' in orders
    assert 'description: "One row per order."' in orders
    assert "Body content." in orders

    # Check index
    index = (dst / "tables" / "index.md").read_text()
    assert "[Orders](orders.md)" in index
    assert "[Customers](customers.md)" in index

    # Root index should list subdirectory
    root_idx = (dst / "index.md").read_text()
    assert "[tables](tables/)" in root_idx


def test_bundle_root_file_with_default_type(tmp_path: Path):
    src = tmp_path / "notes"
    dst = tmp_path / "bundle"
    src.mkdir()
    _write_fixture(
        src,
        {
            "standalone.md": "# Standalone\n\n> A root file.\n\nBody.",
            "tables/data.md": "# Data\n\n> A table.\n\nBody.",
        },
    )

    result = runner.invoke(app, ["bundle", str(src), str(dst), "--default-type", "reference"])
    assert result.exit_code == 0, result.output

    stand = (dst / "standalone.md").read_text()
    assert 'type: "reference"' in stand

    data = (dst / "tables" / "data.md").read_text()
    assert 'type: "tables"' in data

    # Root index should list subdir + root file
    root_idx = (dst / "index.md").read_text()
    assert "[tables](tables/)" in root_idx
    assert "[Standalone](standalone.md)" in root_idx


def test_bundle_skip_root_file_without_default(tmp_path: Path, capsys):
    src = tmp_path / "notes"
    dst = tmp_path / "bundle"
    src.mkdir()
    _write_fixture(
        src,
        {
            "standalone.md": "# Standalone\n\n> A root file.\n\nBody.",
            "tables/data.md": "# Data\n\n> A table.\n\nBody.",
        },
    )

    result = runner.invoke(app, ["bundle", str(src), str(dst)])
    assert result.exit_code == 0, result.output

    assert not (dst / "standalone.md").exists()
    assert (dst / "tables" / "data.md").exists()
    assert "Skipping" in result.output

    # Root index should list subdir only (standalone was skipped)
    root_idx = (dst / "index.md").read_text()
    assert "[tables](tables/)" in root_idx
    assert "[Standalone" not in root_idx


def test_bundle_validation_error(tmp_path: Path):
    src = tmp_path / "notes"
    dst = tmp_path / "bundle"
    src.mkdir()
    _write_fixture(
        src,
        {
            "tables/bad.md": "No heading here.\n> Desc.\n",
        },
    )

    result = runner.invoke(app, ["bundle", str(src), str(dst)])
    assert result.exit_code == 1
    assert "Line 1 must be" in result.output


def test_bundle_replaces_existing_output(tmp_path: Path):
    src = tmp_path / "notes"
    dst = tmp_path / "bundle"
    src.mkdir()
    dst.mkdir()
    (dst / "leftover.txt").write_text("should be gone")
    _write_fixture(src, {"tables/a.md": "# A\n\n> Desc.\n"})

    result = runner.invoke(app, ["bundle", str(src), str(dst)])
    assert result.exit_code == 0, result.output
    assert "Removed existing" in result.output
    assert (dst / "tables" / "a.md").exists()
    assert not (dst / "leftover.txt").exists()


def test_bundle_no_md_files(tmp_path: Path):
    src = tmp_path / "notes"
    dst = tmp_path / "bundle"
    src.mkdir()
    # Create a non-md file
    (src / "readme.txt").write_text("hello")

    result = runner.invoke(app, ["bundle", str(src), str(dst)])
    assert result.exit_code == 1
    assert "No markdown files" in result.output


def test_bundle_logmd_warning(tmp_path: Path):
    src = tmp_path / "notes"
    dst = tmp_path / "bundle"
    src.mkdir()
    (src / "log.md").write_text("# Log\n\n> Some log entry.\n")
    (src / "tables").mkdir()
    (src / "tables/orders.md").write_text("# Orders\n\n> One row.\n\nBody.")

    result = runner.invoke(app, ["bundle", str(src), str(dst)])
    assert result.exit_code == 0, result.output
    assert "reserved filename" in result.output
    assert "log.md" in result.output
    assert not (dst / "log.md").exists()
    assert (dst / "tables" / "orders.md").exists()


def test_bundle_readme_is_reserved(tmp_path: Path):
    """README.md is reserved and skipped."""
    src = tmp_path / "notes"
    dst = tmp_path / "bundle"
    src.mkdir()
    (src / "tables").mkdir()
    (src / "tables/README.md").write_text(
        "# README\n\n> Top-level readme.\n\nDocs here."
    )
    (src / "tables/orders.md").write_text(
        "# Orders\n\n> One row.\n\nBody."
    )

    result = runner.invoke(app, ["bundle", str(src), str(dst)])
    assert result.exit_code == 0, result.output
    assert not (dst / "tables" / "README.md").exists()
    assert (dst / "tables" / "orders.md").exists()


def test_frontmatter_yaml_parseable(tmp_path: Path):
    """Verify generated frontmatter is parseable JSON/YAML for tricky values."""
    import json

    src = tmp_path / "notes"
    dst = tmp_path / "bundle"
    src.mkdir()
    (src / "data.md").write_text(
        "# True/False\n\n> Yes, no, true, false values\n\nBody."
    )

    result = runner.invoke(app, ["bundle", str(src), str(dst), "--default-type", "ref"])
    assert result.exit_code == 0, result.output

    content = (dst / "data.md").read_text()
    frontmatter = content.split("\n---\n")[0] + "\n---\n"
    # Parse each line as key: <json-string> and verify
    for line in frontmatter.strip().split("\n"):
        if line == "---":
            continue
        key, _, raw_val = line.partition(": ")
        assert json.loads(raw_val), f"Value for {key} is not valid JSON: {raw_val}"
