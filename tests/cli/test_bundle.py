"""CLI integration tests for okf bundle."""

from pathlib import Path

from typer.testing import CliRunner

from okf.cli import app

runner = CliRunner()


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


def test_bundle_lenient_parse(tmp_path: Path):
    """Files without strict format are bundled leniently."""
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
    assert result.exit_code == 0, result.output
    assert (dst / "tables" / "bad.md").exists()
    content = (dst / "tables" / "bad.md").read_text()
    assert 'type: "tables"' in content
    # No title in frontmatter since it wasn't found
    assert "title:" not in content


def test_bundle_no_title_index_fallback(tmp_path: Path):
    """Index uses filename stem when concept has no title."""
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
    assert result.exit_code == 0, result.output

    index = (dst / "tables" / "index.md").read_text()
    # Should use filename stem "bad" as link text, not empty brackets
    assert "[bad](bad.md)" in index
    assert "[](" not in index


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


def test_bundle_refuses_same_input_and_output_dir(tmp_path: Path):
    src = tmp_path / "notes"
    src.mkdir()
    _write_fixture(src, {"tables/a.md": "# A\n\n> Desc.\n"})

    result = runner.invoke(app, ["bundle", str(src), str(src), "--force"])
    assert result.exit_code == 1, result.output
    assert "must be different" in result.output


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


def test_bundle_okfignore_skips_matching_files(tmp_path: Path):
    src = tmp_path / "notes"
    dst = tmp_path / "bundle"
    src.mkdir()
    _write_fixture(
        src,
        {
            "tables/orders.md": "# Orders\n\n> One row per order.\n\nBody.",
            "tables/customers.md": "# Customers\n\n> All customers.\n\nBody.",
            ".okfignore": "# ignore one file\n\ntables/orders.md\n",
        },
    )

    result = runner.invoke(app, ["bundle", str(src), str(dst)])
    assert result.exit_code == 0, result.output
    assert "matched .okfignore" in result.output
    assert not (dst / "tables" / "orders.md").exists()
    assert (dst / "tables" / "customers.md").exists()


def test_bundle_okfignore_skips_root_file_before_default_type_check(tmp_path: Path):
    src = tmp_path / "notes"
    dst = tmp_path / "bundle"
    src.mkdir()
    _write_fixture(
        src,
        {
            "standalone.md": "# Standalone\n\n> Root file.\n\nBody.",
            "tables/data.md": "# Data\n\n> A table.\n\nBody.",
            ".okfignore": "standalone.md\n",
        },
    )

    result = runner.invoke(app, ["bundle", str(src), str(dst)])
    assert result.exit_code == 0, result.output
    assert "root-level file needs --default-type" not in result.output
    assert not (dst / "standalone.md").exists()
    assert (dst / "tables" / "data.md").exists()


def test_bundle_okfignore_non_utf8_fails(tmp_path: Path):
    src = tmp_path / "notes"
    dst = tmp_path / "bundle"
    src.mkdir()
    _write_fixture(src, {"tables/data.md": "# Data\n\n> A table.\n\nBody."})
    (src / ".okfignore").write_bytes(b"\xff\xfe")

    result = runner.invoke(app, ["bundle", str(src), str(dst)])
    assert result.exit_code == 1
    assert ".okfignore is not valid UTF-8" in result.output


def test_bundle_okfignore_all_markdown_ignored(tmp_path: Path):
    src = tmp_path / "notes"
    dst = tmp_path / "bundle"
    src.mkdir()
    _write_fixture(
        src,
        {
            "tables/orders.md": "# Orders\n\n> One row.\n\nBody.",
            ".okfignore": "tables/orders.md\n",
        },
    )

    result = runner.invoke(app, ["bundle", str(src), str(dst)])
    assert result.exit_code == 1
    assert "No markdown files found" in result.output


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


def test_bundle_warns_broken_local_markdown_link(tmp_path: Path):
    src = tmp_path / "notes"
    dst = tmp_path / "bundle"
    src.mkdir()
    _write_fixture(
        src,
        {
            "tables/orders.md": (
                "# Orders\n\n> One row.\n\nSee [Customers](customers.md)."
            ),
        },
    )

    result = runner.invoke(app, ["bundle", str(src), str(dst)])
    assert result.exit_code == 0, result.output
    assert "target 'tables/customers.md' not found in bundle" in result.output


def test_bundle_accepts_valid_relative_and_absolute_local_links(tmp_path: Path):
    src = tmp_path / "notes"
    dst = tmp_path / "bundle"
    src.mkdir()
    _write_fixture(
        src,
        {
            "tables/orders.md": (
                "# Orders\n\n> One row.\n\nSee [Customers](./customers.md)."
            ),
            "tables/customers.md": (
                "# Customers\n\n> All customers.\n\nSee [Orders](/tables/orders.md)."
            ),
        },
    )

    result = runner.invoke(app, ["bundle", str(src), str(dst)])
    assert result.exit_code == 0, result.output
    assert "not found in bundle" not in result.output


def test_bundle_ignores_external_and_fragment_links(tmp_path: Path):
    src = tmp_path / "notes"
    dst = tmp_path / "bundle"
    src.mkdir()
    _write_fixture(
        src,
        {
            "tables/orders.md": (
                "# Orders\n\n> One row.\n\n"
                "See [Site](https://example.com).\n"
                "See [Mail](mailto:team@example.com).\n"
                "See [Section](#schema)."
            ),
        },
    )

    result = runner.invoke(app, ["bundle", str(src), str(dst)])
    assert result.exit_code == 0, result.output
    assert "not found in bundle" not in result.output
    assert "points outside bundle" not in result.output


def test_bundle_warns_markdown_link_outside_bundle(tmp_path: Path):
    src = tmp_path / "notes"
    dst = tmp_path / "bundle"
    src.mkdir()
    _write_fixture(
        src,
        {
            "tables/orders.md": (
                "# Orders\n\n> One row.\n\nSee [Secret](../../secret.md)."
            ),
        },
    )

    result = runner.invoke(app, ["bundle", str(src), str(dst)])
    assert result.exit_code == 0, result.output
    assert "points outside bundle" in result.output


def test_bundle_strict_links_fails_on_broken_local_link(tmp_path: Path):
    src = tmp_path / "notes"
    dst = tmp_path / "bundle"
    src.mkdir()
    _write_fixture(
        src,
        {
            "tables/orders.md": (
                "# Orders\n\n> One row.\n\nSee [Customers](customers.md)."
            ),
        },
    )

    result = runner.invoke(app, ["bundle", str(src), str(dst), "--strict-links"])
    assert result.exit_code == 1, result.output
    assert "strict link check failed" in result.output


def test_bundle_strict_links_passes_with_valid_local_links(tmp_path: Path):
    src = tmp_path / "notes"
    dst = tmp_path / "bundle"
    src.mkdir()
    _write_fixture(
        src,
        {
            "tables/orders.md": (
                "# Orders\n\n> One row.\n\nSee [Customers](./customers.md)."
            ),
            "tables/customers.md": (
                "# Customers\n\n> All customers.\n\nBody."
            ),
        },
    )

    result = runner.invoke(app, ["bundle", str(src), str(dst), "--strict-links"])
    assert result.exit_code == 0, result.output


def test_bundle_creates_agents_md(tmp_path: Path):
    src = tmp_path / "notes"
    dst = tmp_path / "my-kb"
    src.mkdir()
    _write_fixture(
        src,
        {
            "tables/orders.md": "# Orders\n\n> One row.\n\nBody.",
        },
    )

    result = runner.invoke(app, ["bundle", str(src), str(dst)])
    assert result.exit_code == 0, result.output

    agents_md = dst / "AGENTS.md"
    assert agents_md.exists()
    content = agents_md.read_text()
    assert "my-kb" in content
    assert "index.md" in content
