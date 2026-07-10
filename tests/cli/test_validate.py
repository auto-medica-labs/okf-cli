"""CLI integration tests for okf validate."""

from pathlib import Path

from typer.testing import CliRunner

from okf.cli import app

runner = CliRunner()


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
