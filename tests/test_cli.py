"""Tests for okf bundle CLI."""

from pathlib import Path

from typer.testing import CliRunner

from okf.cli import app
from okf.core import build_frontmatter, parse_frontmatter, parse_md

runner = CliRunner()


# --- parse_md ---


def test_parse_basic():
    text = "# Orders\n\n> One row per order.\n\nBody here."
    title, desc, body = parse_md(text)
    assert title == "Orders"
    assert desc == "One row per order."
    assert body == "Body here."


def test_parse_multiline_desc():
    text = "# Orders\n\n> Line one\n> Line two\n\nBody."
    title, desc, body = parse_md(text)
    assert title == "Orders"
    assert desc == "Line one Line two"
    assert body == "Body."


def test_parse_no_blank_after_title():
    text = "# Orders\n> Desc\n\nBody."
    title, desc, body = parse_md(text)
    assert title == "Orders"
    assert desc == "Desc"
    assert body == "Body."


def test_parse_missing_title():
    text = "No hash\n> Desc\n\nBody."
    try:
        parse_md(text)
        assert False, "Should raise"
    except ValueError as e:
        assert "Line 1 must be" in str(e)


def test_parse_missing_desc():
    text = "# Orders\n\nBody no desc."
    try:
        parse_md(text)
        assert False, "Should raise"
    except ValueError as e:
        assert "description" in str(e)


def test_parse_empty_title():
    text = "# \n> Desc\n\nBody."
    try:
        parse_md(text)
        assert False, "Should raise"
    except ValueError as e:
        assert "empty" in str(e)


def test_parse_only_title_and_desc():
    text = "# Orders\n> Just a description"
    title, desc, body = parse_md(text)
    assert title == "Orders"
    assert desc == "Just a description"
    assert body == ""


def test_parse_no_trailing_newline():
    text = "# Orders\n> Desc\n\nBody\n"
    title, desc, body = parse_md(text)
    assert title == "Orders"
    assert desc == "Desc"
    assert body == "Body\n"


# --- build_frontmatter ---


def test_frontmatter_basic():
    fm = build_frontmatter("tables", "Orders", "One row.", "2026-07-04T12:00:00")
    assert 'type: "tables"' in fm
    assert 'title: "Orders"' in fm
    assert 'description: "One row."' in fm
    assert 'timestamp: "2026-07-04T12:00:00"' in fm
    assert fm.startswith("---")
    assert fm.endswith("---")


def test_frontmatter_special_chars():
    fm = build_frontmatter("ref", "Thing: A", 'Has: colons and "quotes"', "")
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

    result = runner.invoke(
        app, ["bundle", str(src), str(dst), "--default-type", "reference"]
    )
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

    result = runner.invoke(app, ["bundle", str(src), str(dst), "--force"])
    assert result.exit_code == 0, result.output
    assert "Removed existing" in result.output
    assert (dst / "tables" / "a.md").exists()
    assert not (dst / "leftover.txt").exists()


def test_bundle_refuses_overwrite_without_force(tmp_path: Path):
    """bundle errors if output exists and --force not given."""
    src = tmp_path / "notes"
    dst = tmp_path / "bundle"
    src.mkdir()
    dst.mkdir()
    _write_fixture(src, {"tables/a.md": "# A\n\n> Desc.\n"})

    result = runner.invoke(app, ["bundle", str(src), str(dst)])
    assert result.exit_code == 1, result.output
    assert "exists" in result.output
    assert "--force" in result.output


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


def test_bundle_indexmd_warning(tmp_path: Path):
    src = tmp_path / "notes"
    dst = tmp_path / "bundle"
    src.mkdir()
    (src / "index.md").write_text("# Index\n\n> Some index entry.\n")
    (src / "tables").mkdir()
    (src / "tables/orders.md").write_text("# Orders\n\n> One row.\n\nBody.")

    result = runner.invoke(app, ["bundle", str(src), str(dst)])
    assert result.exit_code == 0, result.output
    assert "reserved filename" in result.output
    assert "index.md" in result.output
    # input index.md was skipped; output index.md is generated, not copied
    assert "Some index entry" not in (dst / "index.md").read_text()
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
    (src / "tables/orders.md").write_text("# Orders\n\n> One row.\n\nBody.")

    result = runner.invoke(app, ["bundle", str(src), str(dst)])
    assert result.exit_code == 0, result.output
    assert "reserved filename" in result.output
    assert "README.md" in result.output
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


# --- parse_frontmatter ---


def test_parse_frontmatter_basic():
    text = "---\ntype: table\ntitle: Orders\n---\n\nBody."
    fm = parse_frontmatter(text)
    assert fm is not None
    assert fm["type"] == "table"
    assert fm["title"] == "Orders"


def test_parse_frontmatter_missing_opening():
    text = "type: table\n---\nBody."
    assert parse_frontmatter(text) is None


def test_parse_frontmatter_missing_closing():
    text = "---\ntype: table\nBody."
    assert parse_frontmatter(text) is None


def test_parse_frontmatter_empty():
    text = "---\n---\nBody."
    fm = parse_frontmatter(text)
    assert fm is not None
    assert fm == {}


def test_parse_frontmatter_empty_file():
    assert parse_frontmatter("") is None


def test_parse_frontmatter_yaml_list():
    text = "---\ntype: table\ntags: [sales, orders]\n---\n\nBody."
    fm = parse_frontmatter(text)
    assert fm is not None
    assert fm["type"] == "table"
    assert fm["tags"] == ["sales", "orders"]


def test_parse_frontmatter_malformed_yaml():
    text = '---\ntype: table\ntitle: "unclosed\n---\n\nBody.'
    assert parse_frontmatter(text) is None


def test_parse_frontmatter_non_dict():
    text = "---\n- just\n- a\n- list\n---\n\nBody."
    assert parse_frontmatter(text) is None


# --- CLI validate ---


def test_validate_valid_bundle(tmp_path: Path):
    src = tmp_path / "bundle"
    src.mkdir()
    (src / "tables").mkdir()
    (src / "tables" / "orders.md").write_text(
        "---\ntype: BigQuery Table\ntitle: Orders\n---\n\nBody."
    )

    result = runner.invoke(app, ["validate", str(src)])
    assert result.exit_code == 0, result.output
    assert "1 files: 1 ok" in result.output


def test_validate_missing_frontmatter(tmp_path: Path):
    src = tmp_path / "bundle"
    src.mkdir()
    (src / "bad.md").write_text("# Just a heading\n\nNo frontmatter.")

    result = runner.invoke(app, ["validate", str(src)])
    assert result.exit_code == 1
    assert "missing or unparseable" in result.output
    assert "0 ok" in result.output


def test_validate_missing_type(tmp_path: Path):
    src = tmp_path / "bundle"
    src.mkdir()
    (src / "notype.md").write_text("---\ntitle: Something\n---\n\nBody.")

    result = runner.invoke(app, ["validate", str(src)])
    assert result.exit_code == 1
    assert "missing non-empty 'type'" in result.output


def test_validate_empty_type(tmp_path: Path):
    src = tmp_path / "bundle"
    src.mkdir()
    (src / "emptytype.md").write_text("---\ntype:\n---\n\nBody.")

    result = runner.invoke(app, ["validate", str(src)])
    assert result.exit_code == 1
    assert "missing non-empty 'type'" in result.output


def test_validate_index_md_no_frontmatter_ok(tmp_path: Path):
    src = tmp_path / "bundle"
    src.mkdir()
    (src / "tables").mkdir()
    (src / "tables" / "orders.md").write_text("---\ntype: table\n---\n\nBody.")
    (src / "index.md").write_text("# Contents\n\n* [Orders](tables/orders.md)")

    result = runner.invoke(app, ["validate", str(src)])
    assert result.exit_code == 0, result.output


def test_validate_index_md_with_frontmatter_fails(tmp_path: Path):
    """Non-root index.md with frontmatter is a conformance error per §6."""
    src = tmp_path / "bundle"
    src.mkdir()
    (src / "tables").mkdir()
    (src / "tables" / "orders.md").write_text("---\ntype: table\n---\n\nBody.")
    (src / "tables" / "index.md").write_text("---\ntitle: Index\n---\n\n# Contents")

    result = runner.invoke(app, ["validate", str(src)])
    assert result.exit_code == 1, result.output
    assert "index.md must not contain frontmatter" in result.output


def test_validate_log_md_is_skipped(tmp_path: Path):
    src = tmp_path / "bundle"
    src.mkdir()
    (src / "tables").mkdir()
    (src / "tables" / "orders.md").write_text("---\ntype: table\n---\n\nBody.")
    (src / "log.md").write_text("## 2026-01-01\n\n* **Update**: stuff")

    result = runner.invoke(app, ["validate", str(src)])
    assert result.exit_code == 0, result.output


def test_validate_not_a_directory(tmp_path: Path):
    f = tmp_path / "notadir"
    f.write_text("hello")

    result = runner.invoke(app, ["validate", str(f)])
    assert result.exit_code == 1
    assert "not a directory" in result.output


def test_validate_no_md_files(tmp_path: Path):
    src = tmp_path / "empty"
    src.mkdir()

    result = runner.invoke(app, ["validate", str(src)])
    assert result.exit_code == 1
    assert "No .md files" in result.output


def test_validate_root_index_md_okf_version_ok(tmp_path: Path):
    """Root index.md with only okf_version is permitted per §11."""
    src = tmp_path / "bundle"
    src.mkdir()
    (src / "tables").mkdir()
    (src / "tables" / "orders.md").write_text("---\ntype: table\n---\n\nBody.")
    (src / "index.md").write_text(
        '---\nokf_version: "0.1"\n---\n\n# Contents\n\n* [Orders](tables/orders.md)'
    )

    result = runner.invoke(app, ["validate", str(src)])
    assert result.exit_code == 0, result.output


def test_validate_root_index_md_extra_fields_fails(tmp_path: Path):
    """Root index.md with fields other than okf_version is an error."""
    src = tmp_path / "bundle"
    src.mkdir()
    (src / "tables").mkdir()
    (src / "tables" / "orders.md").write_text("---\ntype: table\n---\n\nBody.")
    (src / "index.md").write_text(
        '---\nokf_version: "0.1"\ntitle: Extra\n---\n\n# Contents'
    )

    result = runner.invoke(app, ["validate", str(src)])
    assert result.exit_code == 1, result.output
    assert "index.md frontmatter may only contain" in result.output


def test_validate_log_md_with_frontmatter_fails(tmp_path: Path):
    """log.md with frontmatter is a conformance error per §7."""
    src = tmp_path / "bundle"
    src.mkdir()
    (src / "tables").mkdir()
    (src / "tables" / "orders.md").write_text("---\ntype: table\n---\n\nBody.")
    (src / "log.md").write_text("---\nversion: 1\n---\n\n## 2026-01-01")

    result = runner.invoke(app, ["validate", str(src)])
    assert result.exit_code == 1, result.output
    assert "log.md must not contain frontmatter" in result.output


def test_validate_mixed_errors(tmp_path: Path):
    """Multiple conformance errors are all reported."""
    src = tmp_path / "bundle"
    src.mkdir()
    (src / "good.md").write_text("---\ntype: ref\n---\n\nBody.")
    (src / "bad.md").write_text("No frontmatter.")
    (src / "index.md").write_text("---\ntitle: Nope\n---\n\n# Index")

    result = runner.invoke(app, ["validate", str(src)])
    assert result.exit_code == 1
    assert "2 errors" in result.output
    assert "1 ok" in result.output


def test_validate_readme_is_concept(tmp_path: Path):
    """README.md is NOT reserved in the spec — must have frontmatter + type."""
    src = tmp_path / "bundle"
    src.mkdir()
    (src / "README.md").write_text("---\ntype: readme\n---\n\nReadme body.")

    result = runner.invoke(app, ["validate", str(src)])
    assert result.exit_code == 0, result.output


def test_validate_readme_missing_type_fails(tmp_path: Path):
    src = tmp_path / "bundle"
    src.mkdir()
    (src / "README.md").write_text("Just a readme without frontmatter.")

    result = runner.invoke(app, ["validate", str(src)])
    assert result.exit_code == 1
    assert "missing or unparseable" in result.output


def test_validate_malformed_yaml_frontmatter(tmp_path: Path):
    src = tmp_path / "bundle"
    src.mkdir()
    (src / "bad.md").write_text('---\ntype: table\ntitle: "unclosed\n---\n\nBody.')

    result = runner.invoke(app, ["validate", str(src)])
    assert result.exit_code == 1
    assert "missing or unparseable" in result.output


def test_validate_yaml_list_tag_parsed(tmp_path: Path):
    src = tmp_path / "bundle"
    src.mkdir()
    (src / "tagged.md").write_text(
        "---\ntype: table\ntags: [sales, orders]\n---\n\nBody."
    )

    result = runner.invoke(app, ["validate", str(src)])
    assert result.exit_code == 0, result.output


def test_validate_non_string_type_fails(tmp_path: Path):
    src = tmp_path / "bundle"
    src.mkdir()
    (src / "bad.md").write_text("---\ntype: true\n---\n\nBody.")

    result = runner.invoke(app, ["validate", str(src)])
    assert result.exit_code == 1
    assert "missing non-empty 'type'" in result.output


def test_validate_non_utf8_file(tmp_path: Path):
    """Non-UTF-8 files are reported cleanly, not a traceback."""
    src = tmp_path / "bundle"
    src.mkdir()
    (src / "valid.md").write_text("---\ntype: ref\n---\n\nBody.")
    (src / "bad.md").write_bytes(b"\xff\xfe# Title\n> Desc\n")

    result = runner.invoke(app, ["validate", str(src)])
    assert result.exit_code == 1
    assert "not valid UTF-8" in result.output


# --- CLI list ---


def test_list_concepts(tmp_path: Path):
    src = tmp_path / "bundle"
    src.mkdir()
    (src / "tables").mkdir(parents=True)
    (src / "playbooks").mkdir()
    (src / "tables" / "orders.md").write_text("---\ntype: table\n---\n\nBody.")
    (src / "tables" / "customers.md").write_text("---\ntype: table\n---\n\nBody.")
    (src / "playbooks" / "incident.md").write_text("---\ntype: playbook\n---\n\nBody.")
    (src / "index.md").write_text("# Contents")
    (src / "log.md").write_text("## 2026-01-01")

    result = runner.invoke(app, ["list", str(src)])
    assert result.exit_code == 0, result.output

    lines = result.output.strip().split("\n")
    assert lines == [
        "playbooks/incident",
        "tables/customers",
        "tables/orders",
    ]


def test_list_root_concept(tmp_path: Path):
    src = tmp_path / "bundle"
    src.mkdir()
    (src / "ref.md").write_text("---\ntype: ref\n---\n\nBody.")

    result = runner.invoke(app, ["list", str(src)])
    assert result.exit_code == 0, result.output
    assert result.output.strip() == "ref"


def test_list_deeply_nested(tmp_path: Path):
    src = tmp_path / "bundle"
    src.mkdir()
    (src / "a" / "b" / "c").mkdir(parents=True)
    (src / "a" / "b" / "c" / "deep.md").write_text("---\ntype: deep\n---\n\nBody.")

    result = runner.invoke(app, ["list", str(src)])
    assert result.exit_code == 0, result.output
    assert result.output.strip() == "a/b/c/deep"


def test_list_not_a_directory(tmp_path: Path):
    f = tmp_path / "notadir"
    f.write_text("hello")

    result = runner.invoke(app, ["list", str(f)])
    assert result.exit_code == 1
    assert "not a directory" in result.output


def test_list_empty(tmp_path: Path):
    src = tmp_path / "bundle"
    src.mkdir()
    (src / "index.md").write_text("# Contents")

    result = runner.invoke(app, ["list", str(src)])
    assert result.exit_code == 1
    assert "No concepts found" in result.output


def test_list_readme_is_concept(tmp_path: Path):
    """README.md is NOT reserved by the spec — gets listed as concept."""
    src = tmp_path / "bundle"
    src.mkdir()
    (src / "README.md").write_text("---\ntype: readme\n---\n\nBody.")

    result = runner.invoke(app, ["list", str(src)])
    assert result.exit_code == 0, result.output
    assert result.output.strip() == "README"


def test_list_nonconformant_bundle_fails(tmp_path: Path):
    """list must refuse to operate on a non-OKF directory."""
    src = tmp_path / "notes"
    src.mkdir()
    (src / "plain.md").write_text("# Title\n\n> Desc.\n\nBody.")

    result = runner.invoke(app, ["list", str(src)])
    assert result.exit_code == 1
    assert "not an OKF-conformant bundle" in result.output


# --- CLI show ---


def test_show_concept(tmp_path: Path):
    src = tmp_path / "bundle"
    src.mkdir()
    (src / "tables").mkdir()
    (src / "tables" / "orders.md").write_text("---\ntype: table\n---\n\n# Schema\n")

    result = runner.invoke(app, ["show", str(src), "tables/orders"])
    assert result.exit_code == 0, result.output
    assert "type: table" in result.output
    assert "# Schema" in result.output


def test_show_root_concept(tmp_path: Path):
    src = tmp_path / "bundle"
    src.mkdir()
    (src / "ref.md").write_text("---\ntype: ref\n---\n\nRoot body.")

    result = runner.invoke(app, ["show", str(src), "ref"])
    assert result.exit_code == 0, result.output
    assert "Root body." in result.output


def test_show_not_found(tmp_path: Path):
    src = tmp_path / "bundle"
    src.mkdir()

    result = runner.invoke(app, ["show", str(src), "missing/thing"])
    assert result.exit_code == 1
    assert "not found" in result.output
    assert str(src / "missing" / "thing.md") in result.output


def test_show_reserved(tmp_path: Path):
    src = tmp_path / "bundle"
    src.mkdir()
    (src / "index.md").write_text("# Contents")

    result = runner.invoke(app, ["show", str(src), "index"])
    assert result.exit_code == 1
    assert "reserved filename" in result.output


def test_show_log_md_reserved(tmp_path: Path):
    src = tmp_path / "bundle"
    src.mkdir()
    (src / "log.md").write_text("## 2026-01-01")

    result = runner.invoke(app, ["show", str(src), "log"])
    assert result.exit_code == 1
    assert "reserved filename" in result.output


def test_show_path_traversal(tmp_path: Path):
    src = tmp_path / "bundle"
    src.mkdir()

    result = runner.invoke(app, ["show", str(src), "../../../etc/passwd"])
    assert result.exit_code == 1
    assert "outside the bundle directory" in result.output


def test_show_not_a_directory(tmp_path: Path):
    f = tmp_path / "notadir"
    f.write_text("hello")

    result = runner.invoke(app, ["show", str(f), "whatever"])
    assert result.exit_code == 1
    assert "not a directory" in result.output


def test_show_nonconformant_bundle_fails(tmp_path: Path):
    """show must refuse to operate on a non-OKF directory."""
    src = tmp_path / "notes"
    src.mkdir()
    (src / "plain.md").write_text("# Title\n\n> Desc.\n\nBody.")

    result = runner.invoke(app, ["show", str(src), "plain"])
    assert result.exit_code == 1
    assert "not an OKF-conformant bundle" in result.output
