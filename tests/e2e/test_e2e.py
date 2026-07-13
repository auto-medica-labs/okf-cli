"""End-to-end smoke tests covering every CLI feature."""

from pathlib import Path

from typer.testing import CliRunner

from okf.cli import app

runner = CliRunner()


def _write(dir: Path, files: dict[str, str]):
    for path, content in files.items():
        p = dir / path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)


# ---------------------------------------------------------------------------
# bundle
# ---------------------------------------------------------------------------


def test_bundle_basic(tmp_path: Path):
    src = tmp_path / "src"
    dst = tmp_path / "out"
    src.mkdir()
    _write(
        src,
        {
            "tables/orders.md": "# Orders\n\n> One row per order.\n\nBody.",
            "tables/customers.md": "# Customers\n\n> All customers.\n\nBody.",
        },
    )

    result = runner.invoke(app, ["bundle", str(src), str(dst)])
    assert result.exit_code == 0, result.output
    assert (dst / "tables" / "orders.md").exists()
    assert (dst / "tables" / "customers.md").exists()
    assert (dst / "tables" / "index.md").exists()
    assert (dst / "index.md").exists()


def test_bundle_default_type_includes_root_files(tmp_path: Path):
    src = tmp_path / "src"
    dst = tmp_path / "out"
    src.mkdir()
    _write(
        src,
        {
            "domain.md": "# Domain\n\n> Our domain.\n\nBody.",
            "tables/data.md": "# Data\n\n> A table.\n\nBody.",
        },
    )

    result = runner.invoke(
        app, ["bundle", str(src), str(dst), "--default-type", "reference"]
    )
    assert result.exit_code == 0, result.output
    assert (dst / "domain.md").exists()
    content = (dst / "domain.md").read_text()
    assert 'type: "reference"' in content


def test_bundle_root_files_get_type_from_input_dir(tmp_path: Path):
    """Root-level files get type from input directory name when --default-type omitted."""
    src = tmp_path / "src"
    dst = tmp_path / "out"
    src.mkdir()
    _write(
        src,
        {
            "domain.md": "# Domain\n\n> Our domain.\n\nBody.",
            "tables/data.md": "# Data\n\n> A table.\n\nBody.",
        },
    )

    result = runner.invoke(app, ["bundle", str(src), str(dst)])
    assert result.exit_code == 0, result.output
    assert (dst / "domain.md").exists()
    content = (dst / "domain.md").read_text()
    assert 'type: "src"' in content


def test_bundle_force_overwrites(tmp_path: Path):
    src = tmp_path / "src"
    dst = tmp_path / "out"
    src.mkdir()
    dst.mkdir()
    (dst / "old.txt").write_text("gone")
    _write(src, {"tables/a.md": "# A\n\n> Desc.\n"})

    result = runner.invoke(app, ["bundle", str(src), str(dst), "--force"])
    assert result.exit_code == 0, result.output
    assert "Removed existing" in result.output
    assert not (dst / "old.txt").exists()


def test_bundle_refuses_overwrite_without_force(tmp_path: Path):
    src = tmp_path / "src"
    dst = tmp_path / "out"
    src.mkdir()
    dst.mkdir()
    _write(src, {"tables/a.md": "# A\n\n> Desc.\n"})

    result = runner.invoke(app, ["bundle", str(src), str(dst)])
    assert result.exit_code == 1
    assert "--force" in result.output


def test_bundle_missing_input_dir():
    result = runner.invoke(app, ["bundle", "/nonexistent/"])
    assert result.exit_code == 1
    assert "not found" in result.output


def test_bundle_no_md_files(tmp_path: Path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "readme.txt").write_text("hello")

    result = runner.invoke(app, ["bundle", str(src), str(tmp_path / "out")])
    assert result.exit_code == 1
    assert "No markdown files" in result.output


# ---------------------------------------------------------------------------
# bundle — reserved filenames
# ---------------------------------------------------------------------------


def test_bundle_skips_readme(tmp_path: Path):
    src = tmp_path / "src"
    dst = tmp_path / "out"
    src.mkdir()
    _write(
        src,
        {
            "README.md": "# Readme\n\n> Top level.\n\nBody.",
            "tables/orders.md": "# Orders\n\n> One row.\n\nBody.",
        },
    )

    result = runner.invoke(app, ["bundle", str(src), str(dst)])
    assert result.exit_code == 0, result.output
    assert "reserved filename" in result.output
    assert not (dst / "README.md").exists()


def test_bundle_skips_indexmd(tmp_path: Path):
    src = tmp_path / "src"
    dst = tmp_path / "out"
    src.mkdir()
    _write(
        src,
        {
            "index.md": "# Index\n\n> Custom index.\n",
            "tables/orders.md": "# Orders\n\n> One row.\n\nBody.",
        },
    )

    result = runner.invoke(app, ["bundle", str(src), str(dst)])
    assert result.exit_code == 0, result.output
    assert "reserved filename" in result.output
    # output index.md is generated, not copied
    assert "Custom index" not in (dst / "index.md").read_text()


def test_bundle_skips_logmd(tmp_path: Path):
    src = tmp_path / "src"
    dst = tmp_path / "out"
    src.mkdir()
    _write(
        src,
        {
            "log.md": "# Log\n\n> Entry.\n",
            "tables/orders.md": "# Orders\n\n> One row.\n\nBody.",
        },
    )

    result = runner.invoke(app, ["bundle", str(src), str(dst)])
    assert result.exit_code == 0, result.output
    assert "reserved filename" in result.output
    assert not (dst / "log.md").exists()


# ---------------------------------------------------------------------------
# bundle — .okfignore
# ---------------------------------------------------------------------------


def test_bundle_okfignore_skips_files(tmp_path: Path):
    src = tmp_path / "src"
    dst = tmp_path / "out"
    src.mkdir()
    _write(
        src,
        {
            "tables/orders.md": "# Orders\n\n> One row.\n\nBody.",
            "tables/customers.md": "# Customers\n\n> All.\n\nBody.",
            ".okfignore": "tables/orders.md\n",
        },
    )

    result = runner.invoke(app, ["bundle", str(src), str(dst)])
    assert result.exit_code == 0, result.output
    assert "matched .okfignore" in result.output
    assert not (dst / "tables" / "orders.md").exists()
    assert (dst / "tables" / "customers.md").exists()


def test_bundle_okfignore_non_utf8_fails(tmp_path: Path):
    src = tmp_path / "src"
    dst = tmp_path / "out"
    src.mkdir()
    _write(src, {"tables/a.md": "# A\n\n> Desc.\n"})
    (src / ".okfignore").write_bytes(b"\xff\xfe")

    result = runner.invoke(app, ["bundle", str(src), str(dst)])
    assert result.exit_code == 1
    assert ".okfignore is not valid UTF-8" in result.output


def test_bundle_okfignore_all_ignored(tmp_path: Path):
    src = tmp_path / "src"
    dst = tmp_path / "out"
    src.mkdir()
    _write(
        src,
        {
            "tables/orders.md": "# Orders\n\n> One row.\n\nBody.",
            ".okfignore": "tables/orders.md\n",
        },
    )

    result = runner.invoke(app, ["bundle", str(src), str(dst)])
    assert result.exit_code == 1
    assert "No markdown files found" in result.output


# ---------------------------------------------------------------------------
# bundle — link checking
# ---------------------------------------------------------------------------


def test_bundle_warns_broken_link(tmp_path: Path):
    src = tmp_path / "src"
    dst = tmp_path / "out"
    src.mkdir()
    _write(
        src,
        {
            "tables/orders.md": (
                "# Orders\n\n> One row.\n\nSee [Customers](customers.md)."
            ),
        },
    )

    result = runner.invoke(app, ["bundle", str(src), str(dst)])
    assert result.exit_code == 0, result.output
    assert "not found in bundle" in result.output


def test_bundle_accepts_valid_links(tmp_path: Path):
    src = tmp_path / "src"
    dst = tmp_path / "out"
    src.mkdir()
    _write(
        src,
        {
            "tables/orders.md": (
                "# Orders\n\n> One row.\n\nSee [Customers](./customers.md)."
            ),
            "tables/customers.md": "# Customers\n\n> All.\n\nBody.",
        },
    )

    result = runner.invoke(app, ["bundle", str(src), str(dst)])
    assert result.exit_code == 0, result.output
    assert "not found in bundle" not in result.output


def test_bundle_ignores_external_links(tmp_path: Path):
    src = tmp_path / "src"
    dst = tmp_path / "out"
    src.mkdir()
    _write(
        src,
        {
            "tables/orders.md": (
                "# Orders\n\n> One row.\n\n"
                "See [Site](https://example.com).\n"
                "See [Mail](mailto:a@b.com).\n"
                "See [Section](#schema)."
            ),
        },
    )

    result = runner.invoke(app, ["bundle", str(src), str(dst)])
    assert result.exit_code == 0, result.output
    assert "not found" not in result.output
    assert "outside bundle" not in result.output


def test_bundle_warns_link_outside_bundle(tmp_path: Path):
    src = tmp_path / "src"
    dst = tmp_path / "out"
    src.mkdir()
    _write(
        src,
        {
            "tables/orders.md": "# Orders\n\n> One row.\n\nSee [X](../../secret.md).",
        },
    )

    result = runner.invoke(app, ["bundle", str(src), str(dst)])
    assert result.exit_code == 0, result.output
    assert "points outside bundle" in result.output


def test_bundle_strict_links_fails(tmp_path: Path):
    src = tmp_path / "src"
    dst = tmp_path / "out"
    src.mkdir()
    _write(
        src,
        {
            "tables/orders.md": "# Orders\n\n> One row.\n\nSee [C](customers.md).",
        },
    )

    result = runner.invoke(app, ["bundle", str(src), str(dst), "--strict-links"])
    assert result.exit_code == 1
    assert "strict link check failed" in result.output


def test_bundle_strict_links_passes(tmp_path: Path):
    src = tmp_path / "src"
    dst = tmp_path / "out"
    src.mkdir()
    _write(
        src,
        {
            "tables/orders.md": "# Orders\n\n> One row.\n\nSee [C](./customers.md).",
            "tables/customers.md": "# Customers\n\n> All.\n\nBody.",
        },
    )

    result = runner.invoke(app, ["bundle", str(src), str(dst), "--strict-links"])
    assert result.exit_code == 0, result.output


# ---------------------------------------------------------------------------
# bundle — lenient parsing
# ---------------------------------------------------------------------------


def test_bundle_lenient_no_desc(tmp_path: Path):
    src = tmp_path / "src"
    dst = tmp_path / "out"
    src.mkdir()
    _write(src, {"tables/a.md": "# Has Title\n\nBody without description block.\n"})

    result = runner.invoke(app, ["bundle", str(src), str(dst)])
    assert result.exit_code == 0, result.output
    content = (dst / "tables" / "a.md").read_text()
    assert 'title: "Has Title"' in content
    assert "description:" in content


def test_bundle_lenient_no_title(tmp_path: Path):
    src = tmp_path / "src"
    dst = tmp_path / "out"
    src.mkdir()
    _write(src, {"tables/a.md": "No heading here.\n> Desc.\n"})

    result = runner.invoke(app, ["bundle", str(src), str(dst)])
    assert result.exit_code == 0, result.output
    content = (dst / "tables" / "a.md").read_text()
    assert "title:" not in content
    assert 'type: "tables"' in content


def test_bundle_lenient_no_heading(tmp_path: Path):
    src = tmp_path / "src"
    dst = tmp_path / "out"
    src.mkdir()
    _write(src, {"tables/a.md": "Just plain text.\n"})

    result = runner.invoke(app, ["bundle", str(src), str(dst)])
    assert result.exit_code == 0, result.output
    assert (dst / "tables" / "a.md").exists()


def test_bundle_index_uses_stem_when_no_title(tmp_path: Path):
    src = tmp_path / "src"
    dst = tmp_path / "out"
    src.mkdir()
    _write(src, {"tables/bad.md": "No heading.\n> Desc.\n"})

    result = runner.invoke(app, ["bundle", str(src), str(dst)])
    assert result.exit_code == 0, result.output
    index = (dst / "tables" / "index.md").read_text()
    assert "[bad](bad.md)" in index
    assert "[](" not in index


# ---------------------------------------------------------------------------
# bundle — generated files
# ---------------------------------------------------------------------------


def test_bundle_generates_agents_md(tmp_path: Path):
    src = tmp_path / "src"
    dst = tmp_path / "my-kb"
    src.mkdir()
    _write(src, {"tables/a.md": "# A\n\n> Desc.\n"})

    result = runner.invoke(app, ["bundle", str(src), str(dst)])
    assert result.exit_code == 0, result.output
    assert (dst / "AGENTS.md").exists()
    content = (dst / "AGENTS.md").read_text()
    assert "my-kb" in content
    assert "index.md" in content


def test_bundle_generates_subdirectory_indexes(tmp_path: Path):
    src = tmp_path / "src"
    dst = tmp_path / "out"
    src.mkdir()
    _write(
        src,
        {
            "tables/orders.md": "# Orders\n\n> One row.\n\nBody.",
            "tables/customers.md": "# Customers\n\n> All.\n\nBody.",
        },
    )

    result = runner.invoke(app, ["bundle", str(src), str(dst)])
    assert result.exit_code == 0, result.output
    index = (dst / "tables" / "index.md").read_text()
    assert "[Orders](orders.md)" in index
    assert "[Customers](customers.md)" in index


def test_bundle_frontmatter_is_valid_yaml(tmp_path: Path):
    src = tmp_path / "src"
    dst = tmp_path / "out"
    src.mkdir()
    _write(src, {"tables/a.md": "# A\n\n> Desc.\n\nBody."})

    result = runner.invoke(app, ["bundle", str(src), str(dst)])
    assert result.exit_code == 0, result.output

    import yaml

    content = (dst / "tables" / "a.md").read_text()
    fm_text = content.split("---\n", 1)[1].split("\n---", 1)[0]
    fm = yaml.safe_load(fm_text)
    assert isinstance(fm, dict)
    assert fm["type"] == "tables"
    assert fm["title"] == "A"


# ---------------------------------------------------------------------------
# validate
# ---------------------------------------------------------------------------


def test_validate_conformant_bundle(tmp_path: Path):
    d = tmp_path / "bundle"
    d.mkdir()
    _write(d, {"tables/a.md": "---\ntype: ref\n---\n\nBody."})

    result = runner.invoke(app, ["validate", str(d)])
    assert result.exit_code == 0
    assert "1 ok" in result.output


def test_validate_missing_frontmatter(tmp_path: Path):
    d = tmp_path / "bundle"
    d.mkdir()
    _write(d, {"bad.md": "# Title\n\nNo frontmatter."})

    result = runner.invoke(app, ["validate", str(d)])
    assert result.exit_code == 1
    assert "missing or unparseable" in result.output


def test_validate_empty_type(tmp_path: Path):
    d = tmp_path / "bundle"
    d.mkdir()
    _write(d, {"bad.md": '---\ntype: ""\n---\n\nBody.'})

    result = runner.invoke(app, ["validate", str(d)])
    assert result.exit_code == 1
    assert "missing non-empty 'type'" in result.output


def test_validate_whitespace_only_type(tmp_path: Path):
    d = tmp_path / "bundle"
    d.mkdir()
    _write(d, {"bad.md": '---\ntype: "   "\n---\n\nBody.'})

    result = runner.invoke(app, ["validate", str(d)])
    assert result.exit_code == 1
    assert "missing non-empty 'type'" in result.output


def test_validate_non_string_type(tmp_path: Path):
    d = tmp_path / "bundle"
    d.mkdir()
    _write(d, {"bad.md": "---\ntype: true\n---\n\nBody."})

    result = runner.invoke(app, ["validate", str(d)])
    assert result.exit_code == 1
    assert "missing non-empty 'type'" in result.output


def test_validate_malformed_yaml(tmp_path: Path):
    d = tmp_path / "bundle"
    d.mkdir()
    _write(d, {"bad.md": "---\ntype: [unclosed\n---\n\nBody."})

    result = runner.invoke(app, ["validate", str(d)])
    assert result.exit_code == 1
    assert "missing or unparseable" in result.output


def test_validate_non_dict_frontmatter(tmp_path: Path):
    d = tmp_path / "bundle"
    d.mkdir()
    _write(d, {"bad.md": "---\n- item1\n- item2\n---\n\nBody."})

    result = runner.invoke(app, ["validate", str(d)])
    assert result.exit_code == 1
    assert "missing or unparseable" in result.output


def test_validate_non_utf8_file(tmp_path: Path):
    d = tmp_path / "bundle"
    d.mkdir()
    _write(d, {"valid.md": "---\ntype: ref\n---\n\nBody."})
    (d / "bad.md").write_bytes(b"\xff\xfe# Title\n> Desc\n")

    result = runner.invoke(app, ["validate", str(d)])
    assert result.exit_code == 1
    assert "not valid UTF-8" in result.output


def test_validate_index_md_no_frontmatter_ok(tmp_path: Path):
    d = tmp_path / "bundle"
    d.mkdir()
    _write(d, {"tables/a.md": "---\ntype: ref\n---\n\nBody."})
    (d / "index.md").write_text("# Contents\n\n* [A](tables/a.md)")

    result = runner.invoke(app, ["validate", str(d)])
    assert result.exit_code == 0


def test_validate_subdir_index_md_with_frontmatter_fails(tmp_path: Path):
    d = tmp_path / "bundle"
    d.mkdir()
    _write(d, {"tables/a.md": "---\ntype: ref\n---\n\nBody."})
    (d / "tables" / "index.md").write_text("---\ntitle: Index\n---\n\n# Contents")

    result = runner.invoke(app, ["validate", str(d)])
    assert result.exit_code == 1
    assert "index.md must not contain frontmatter" in result.output


def test_validate_root_index_md_okf_version_ok(tmp_path: Path):
    d = tmp_path / "bundle"
    d.mkdir()
    _write(d, {"tables/a.md": "---\ntype: ref\n---\n\nBody."})
    (d / "index.md").write_text('---\nokf_version: "0.1"\n---\n\n# Contents')

    result = runner.invoke(app, ["validate", str(d)])
    assert result.exit_code == 0


def test_validate_root_index_md_extra_fields_fails(tmp_path: Path):
    d = tmp_path / "bundle"
    d.mkdir()
    _write(d, {"tables/a.md": "---\ntype: ref\n---\n\nBody."})
    (d / "index.md").write_text('---\nokf_version: "0.1"\ntitle: Extra\n---')

    result = runner.invoke(app, ["validate", str(d)])
    assert result.exit_code == 1
    assert "may only contain" in result.output


def test_validate_log_md_no_frontmatter_ok(tmp_path: Path):
    d = tmp_path / "bundle"
    d.mkdir()
    _write(d, {"tables/a.md": "---\ntype: ref\n---\n\nBody."})
    (d / "log.md").write_text("## 2026-01-01\n\n* Update")

    result = runner.invoke(app, ["validate", str(d)])
    assert result.exit_code == 0


def test_validate_log_md_with_frontmatter_fails(tmp_path: Path):
    d = tmp_path / "bundle"
    d.mkdir()
    _write(d, {"tables/a.md": "---\ntype: ref\n---\n\nBody."})
    (d / "log.md").write_text("---\nversion: 1\n---\n\n## Log")

    result = runner.invoke(app, ["validate", str(d)])
    assert result.exit_code == 1
    assert "log.md must not contain frontmatter" in result.output


def test_validate_readme_is_concept(tmp_path: Path):
    d = tmp_path / "bundle"
    d.mkdir()
    _write(d, {"README.md": "---\ntype: readme\n---\n\nReadme body."})

    result = runner.invoke(app, ["validate", str(d)])
    assert result.exit_code == 0


def test_validate_readme_missing_frontmatter_fails(tmp_path: Path):
    d = tmp_path / "bundle"
    d.mkdir()
    _write(d, {"README.md": "Just a readme."})

    result = runner.invoke(app, ["validate", str(d)])
    assert result.exit_code == 1
    assert "missing or unparseable" in result.output


def test_validate_agents_md_skipped(tmp_path: Path):
    """AGENTS.md is generated, not a concept — must not error."""
    d = tmp_path / "bundle"
    d.mkdir()
    _write(d, {"tables/a.md": "---\ntype: ref\n---\n\nBody."})
    (d / "AGENTS.md").write_text("# KB\n\nNavigation guide.")

    result = runner.invoke(app, ["validate", str(d)])
    assert result.exit_code == 0


def test_validate_not_a_directory(tmp_path: Path):
    f = tmp_path / "file"
    f.write_text("hello")

    result = runner.invoke(app, ["validate", str(f)])
    assert result.exit_code == 1
    assert "not a directory" in result.output


def test_validate_empty_dir(tmp_path: Path):
    d = tmp_path / "empty"
    d.mkdir()

    result = runner.invoke(app, ["validate", str(d)])
    assert result.exit_code == 1
    assert "No .md files" in result.output


def test_validate_multiple_errors(tmp_path: Path):
    d = tmp_path / "bundle"
    d.mkdir()
    _write(
        d,
        {
            "good.md": "---\ntype: ref\n---\n\nBody.",
            "bad1.md": "No frontmatter.",
            "bad2.md": "---\ntitle: X\n---\n\nBody.",
        },
    )

    result = runner.invoke(app, ["validate", str(d)])
    assert result.exit_code == 1
    assert "2 errors" in result.output
    assert "1 ok" in result.output


def test_validate_non_conformant_dir(tmp_path: Path):
    d = tmp_path / "raw"
    d.mkdir()
    _write(d, {"notes.md": "# Notes\n\n> Just notes.\n\nBody."})

    result = runner.invoke(app, ["validate", str(d)])
    assert result.exit_code == 1
    assert "missing or unparseable" in result.output


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------


def test_list_conformant_bundle(tmp_path: Path):
    d = tmp_path / "bundle"
    d.mkdir()
    _write(
        d,
        {
            "tables/orders.md": "---\ntype: tables\n---\n\nBody.",
            "tables/customers.md": "---\ntype: tables\n---\n\nBody.",
            "datasets/sales.md": "---\ntype: datasets\n---\n\nBody.",
        },
    )

    result = runner.invoke(app, ["list", str(d)])
    assert result.exit_code == 0
    assert "tables/orders" in result.output
    assert "tables/customers" in result.output
    assert "datasets/sales" in result.output


def test_list_non_conformant_dir(tmp_path: Path):
    d = tmp_path / "raw"
    d.mkdir()
    _write(d, {"notes.md": "# Notes\n\n> Notes.\n\nBody."})

    result = runner.invoke(app, ["list", str(d)])
    assert result.exit_code == 1
    assert "not an OKF-conformant bundle" in result.output


def test_list_empty_bundle(tmp_path: Path):
    d = tmp_path / "bundle"
    d.mkdir()

    result = runner.invoke(app, ["list", str(d)])
    assert result.exit_code == 1
    assert "No concepts found" in result.output


# ---------------------------------------------------------------------------
# show
# ---------------------------------------------------------------------------


def test_show_valid_concept(tmp_path: Path):
    d = tmp_path / "bundle"
    d.mkdir()
    _write(d, {"tables/orders.md": "---\ntype: tables\n---\n\nOrders body."})

    result = runner.invoke(app, ["show", str(d), "tables/orders"])
    assert result.exit_code == 0
    assert "Orders body." in result.output


def test_show_with_md_extension_appended(tmp_path: Path):
    """show always appends .md.

    Passing tables/orders.md looks for tables/orders.md.md.
    """
    d = tmp_path / "bundle"
    d.mkdir()
    _write(d, {"tables/orders.md": "---\ntype: tables\n---\n\nBody."})

    result = runner.invoke(app, ["show", str(d), "tables/orders.md"])
    assert result.exit_code == 1
    assert "not found" in result.output


def test_show_deeply_nested(tmp_path: Path):
    d = tmp_path / "bundle"
    d.mkdir()
    _write(d, {"a/b/c/deep.md": "---\ntype: c\n---\n\nDeep body."})

    result = runner.invoke(app, ["show", str(d), "a/b/c/deep"])
    assert result.exit_code == 0
    assert "Deep body." in result.output


def test_show_nonexistent_id(tmp_path: Path):
    d = tmp_path / "bundle"
    d.mkdir()
    _write(d, {"tables/orders.md": "---\ntype: tables\n---\n\nBody."})

    result = runner.invoke(app, ["show", str(d), "tables/customers"])
    assert result.exit_code == 1
    assert "not found" in result.output


def test_show_non_conformant_dir(tmp_path: Path):
    d = tmp_path / "raw"
    d.mkdir()
    _write(d, {"notes.md": "# Notes\n\n> Notes.\n\nBody."})

    result = runner.invoke(app, ["show", str(d), "notes"])
    assert result.exit_code == 1
    assert "not an OKF-conformant bundle" in result.output


# ---------------------------------------------------------------------------
# cross-command: bundle → validate/list/show
# ---------------------------------------------------------------------------


def test_bundle_then_validate(tmp_path: Path):
    src = tmp_path / "src"
    dst = tmp_path / "out"
    src.mkdir()
    _write(
        src,
        {
            "tables/orders.md": "# Orders\n\n> One row.\n\nBody.",
            "datasets/sales.md": "# Sales\n\n> Sales data.\n\nBody.",
        },
    )

    result = runner.invoke(app, ["bundle", str(src), str(dst)])
    assert result.exit_code == 0, result.output

    result = runner.invoke(app, ["validate", str(dst)])
    assert result.exit_code == 0, result.output
    assert "ok" in result.output


def test_bundle_then_list(tmp_path: Path):
    src = tmp_path / "src"
    dst = tmp_path / "out"
    src.mkdir()
    _write(
        src,
        {
            "tables/orders.md": "# Orders\n\n> One row.\n\nBody.",
            "tables/customers.md": "# Customers\n\n> All.\n\nBody.",
        },
    )

    result = runner.invoke(app, ["bundle", str(src), str(dst)])
    assert result.exit_code == 0, result.output

    result = runner.invoke(app, ["list", str(dst)])
    assert result.exit_code == 0
    assert "tables/orders" in result.output
    assert "tables/customers" in result.output


def test_bundle_then_show(tmp_path: Path):
    src = tmp_path / "src"
    dst = tmp_path / "out"
    src.mkdir()
    _write(src, {"tables/orders.md": "# Orders\n\n> One row.\n\nBody."})

    result = runner.invoke(app, ["bundle", str(src), str(dst)])
    assert result.exit_code == 0, result.output

    result = runner.invoke(app, ["show", str(dst), "tables/orders"])
    assert result.exit_code == 0
    assert "Body." in result.output
