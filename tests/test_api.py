"""Tests for the okf Python API."""

from pathlib import Path

import pytest
import yaml

from okf.api import (
    BundleResult,
    ConceptContent,
    ValidateResult,
    bundle,
    list_concepts,
    show_concept,
    validate,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write(dir_path: Path, files: dict[str, str]) -> None:
    for rel, content in files.items():
        p = dir_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")


# ---------------------------------------------------------------------------
# bundle()
# ---------------------------------------------------------------------------


class TestBundle:
    def test_basic(self, tmp_path: Path):
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

        result = bundle(src, dst)

        assert isinstance(result, BundleResult)
        assert result.files_written == 2
        assert result.errors == []
        assert (dst / "tables" / "orders.md").exists()
        assert (dst / "tables" / "customers.md").exists()
        assert (dst / "tables" / "index.md").exists()
        assert (dst / "index.md").exists()
        assert (dst / "AGENTS.md").exists()

    def test_frontmatter_content(self, tmp_path: Path):
        src = tmp_path / "src"
        dst = tmp_path / "out"
        src.mkdir()
        _write(src, {"tables/a.md": "# A\n\n> Desc A.\n\nBody."})

        bundle(src, dst)
        text = (dst / "tables" / "a.md").read_text()

        assert text.startswith("---\n")
        assert 'type: "tables"' in text
        assert 'title: "A"' in text
        assert 'description: "Desc A."' in text
        assert "timestamp:" in text

    def test_frontmatter_valid_yaml(self, tmp_path: Path):
        src = tmp_path / "src"
        dst = tmp_path / "out"
        src.mkdir()
        _write(src, {"tables/a.md": "# A\n\n> Desc.\n\nBody."})

        bundle(src, dst)
        content = (dst / "tables" / "a.md").read_text()
        fm_text = content.split("---\n", 1)[1].split("\n---", 1)[0]
        fm = yaml.safe_load(fm_text)

        assert isinstance(fm, dict)
        assert fm["type"] == "tables"
        assert fm["title"] == "A"

    def test_frontmatter_yaml_parseable_tricky_values(self, tmp_path: Path):
        import json

        src = tmp_path / "src"
        dst = tmp_path / "out"
        src.mkdir()
        _write(
            src, {"data.md": ("# True/False\n\n> Yes, no, true, false values\n\nBody.")}
        )

        bundle(src, dst, default_type="ref")

        content = (dst / "data.md").read_text()
        frontmatter = content.split("\n---\n")[0] + "\n---\n"
        for line in frontmatter.strip().split("\n"):
            if line == "---":
                continue
            key, _, raw_val = line.partition(": ")
            assert json.loads(raw_val), f"Value for {key} is not valid JSON: {raw_val}"

    def test_skip_reserved(self, tmp_path: Path):
        src = tmp_path / "src"
        dst = tmp_path / "out"
        src.mkdir()
        _write(
            src,
            {
                "tables/a.md": "# A\n\n> Desc.\n",
                "index.md": "# Index\n",
                "log.md": "# Log\n",
                "README.md": "# Readme\n",
            },
        )

        result = bundle(src, dst)

        assert result.files_written == 1
        assert any("reserved" in w.lower() for w in result.warnings)

    def test_skip_okfignore(self, tmp_path: Path):
        src = tmp_path / "src"
        dst = tmp_path / "out"
        src.mkdir()
        _write(
            src,
            {
                "tables/a.md": "# A\n\n> Desc.\n",
                "tables/b.md": "# B\n\n> Desc B.\n",
                ".okfignore": "tables/b.md\n",
            },
        )

        result = bundle(src, dst)

        assert result.files_written == 1
        assert not (dst / "tables" / "b.md").exists()

    def test_okfignore_root_file(self, tmp_path: Path):
        src = tmp_path / "src"
        dst = tmp_path / "out"
        src.mkdir()
        _write(
            src,
            {
                "standalone.md": "# Standalone\n\n> Root file.\n\nBody.",
                "tables/data.md": "# Data\n\n> A table.\n\nBody.",
                ".okfignore": "standalone.md\n",
            },
        )

        bundle(src, dst)

        assert not (dst / "standalone.md").exists()
        assert (dst / "tables" / "data.md").exists()

    def test_okfignore_non_utf8_fails(self, tmp_path: Path):
        src = tmp_path / "src"
        dst = tmp_path / "out"
        src.mkdir()
        _write(src, {"tables/a.md": "# A\n\n> Desc.\n"})
        (src / ".okfignore").write_bytes(b"\xff\xfe")

        result = bundle(src, dst)
        assert result.errors
        assert ".okfignore is not valid UTF-8" in str(result.errors)

    def test_okfignore_all_ignored(self, tmp_path: Path):
        src = tmp_path / "src"
        dst = tmp_path / "out"
        src.mkdir()
        _write(
            src,
            {
                "tables/orders.md": "# Orders\n\n> One row.\n",
                ".okfignore": "tables/orders.md\n",
            },
        )

        result = bundle(src, dst)

        assert result.files_written == 0
        assert "No markdown files found" in str(result.errors)

    def test_force_overwrite(self, tmp_path: Path):
        src = tmp_path / "src"
        dst = tmp_path / "out"
        src.mkdir()
        dst.mkdir()
        (dst / "old.txt").write_text("gone")
        _write(src, {"tables/a.md": "# A\n\n> Desc.\n"})

        result = bundle(src, dst, force=True)

        assert result.files_written == 1
        assert not (dst / "old.txt").exists()
        assert any("Removed" in w for w in result.warnings)

    def test_no_force_fails(self, tmp_path: Path):
        src = tmp_path / "src"
        dst = tmp_path / "out"
        src.mkdir()
        dst.mkdir()
        _write(src, {"tables/a.md": "# A\n\n> Desc.\n"})

        with pytest.raises(FileExistsError, match="--force"):
            bundle(src, dst)

    def test_missing_input(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError):
            bundle(tmp_path / "nope", tmp_path / "out")

    def test_same_dir(self, tmp_path: Path):
        src = tmp_path / "src"
        src.mkdir()
        with pytest.raises(ValueError, match="different"):
            bundle(src, src)

    def test_empty_dir(self, tmp_path: Path):
        src = tmp_path / "src"
        src.mkdir()
        result = bundle(src, tmp_path / "out")
        assert result.errors
        assert result.files_written == 0

    def test_no_md_files(self, tmp_path: Path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "readme.txt").write_text("hello")

        result = bundle(src, tmp_path / "out")
        assert result.files_written == 0
        assert "No markdown files" in str(result.errors)

    def test_default_type(self, tmp_path: Path):
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

        result = bundle(src, dst, default_type="reference")

        assert result.files_written == 2
        assert 'type: "reference"' in (dst / "domain.md").read_text()
        assert 'type: "tables"' in (dst / "tables" / "data.md").read_text()

    def test_root_type_from_input_dir(self, tmp_path: Path):
        src = tmp_path / "notes"
        dst = tmp_path / "out"
        src.mkdir()
        _write(src, {"domain.md": "# Domain\n\n> Our domain.\n\nBody."})

        bundle(src, dst)

        assert 'type: "notes"' in (dst / "domain.md").read_text()

    def test_warns_broken_link(self, tmp_path: Path):
        src = tmp_path / "src"
        dst = tmp_path / "out"
        src.mkdir()
        _write(
            src,
            {"tables/orders.md": "# Orders\n\n> One row.\n\nSee [C](customers.md)."},
        )

        result = bundle(src, dst)

        assert any("not found in bundle" in w for w in result.warnings)

    def test_valid_links(self, tmp_path: Path):
        src = tmp_path / "src"
        dst = tmp_path / "out"
        src.mkdir()
        _write(
            src,
            {
                "tables/orders.md": (
                    "# Orders\n\n> One row.\n\nSee [C](./customers.md)."
                ),
                "tables/customers.md": "# Customers\n\n> All.\n\nBody.",
            },
        )

        result = bundle(src, dst)

        assert not any("not found in bundle" in w for w in result.warnings)

    def test_ignores_external_links(self, tmp_path: Path):
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

        result = bundle(src, dst)

        assert not any("not found" in w for w in result.warnings)
        assert not any("outside bundle" in w for w in result.warnings)

    def test_warns_link_outside_bundle(self, tmp_path: Path):
        src = tmp_path / "src"
        dst = tmp_path / "out"
        src.mkdir()
        _write(
            src,
            {"tables/orders.md": "# Orders\n\n> One row.\n\nSee [X](../../secret.md)."},
        )

        result = bundle(src, dst)

        assert any("points outside bundle" in w for w in result.warnings)

    def test_strict_links_fails(self, tmp_path: Path):
        src = tmp_path / "src"
        dst = tmp_path / "out"
        src.mkdir()
        _write(
            src,
            {"tables/orders.md": "# Orders\n\n> One row.\n\nSee [C](customers.md)."},
        )

        result = bundle(src, dst, strict_links=True)

        assert result.files_written == 0
        assert any("strict link check failed" in e.lower() for e in result.errors)

    def test_strict_links_passes(self, tmp_path: Path):
        src = tmp_path / "src"
        dst = tmp_path / "out"
        src.mkdir()
        _write(
            src,
            {
                "tables/orders.md": (
                    "# Orders\n\n> One row.\n\nSee [C](./customers.md)."
                ),
                "tables/customers.md": "# Customers\n\n> All.\n\nBody.",
            },
        )

        result = bundle(src, dst, strict_links=True)

        assert result.files_written == 2
        assert result.errors == []

    def test_agents_md(self, tmp_path: Path):
        src = tmp_path / "src"
        dst = tmp_path / "my-kb"
        src.mkdir()
        _write(src, {"tables/a.md": "# A\n\n> Desc.\n"})

        bundle(src, dst)

        assert (dst / "AGENTS.md").exists()
        content = (dst / "AGENTS.md").read_text()
        assert "my-kb" in content
        assert "index.md" in content

    def test_subdirectory_indexes(self, tmp_path: Path):
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

        bundle(src, dst)

        index = (dst / "tables" / "index.md").read_text()
        assert "[Orders](orders.md)" in index
        assert "[Customers](customers.md)" in index

    def test_root_index_lists_subdirs(self, tmp_path: Path):
        src = tmp_path / "src"
        dst = tmp_path / "out"
        src.mkdir()
        _write(src, {"tables/a.md": "# A\n\n> Desc.\n"})

        bundle(src, dst)

        root_idx = (dst / "index.md").read_text()
        assert "[tables](tables/)" in root_idx

    # -- lenient parsing --

    def test_lenient_no_desc(self, tmp_path: Path):
        src = tmp_path / "src"
        dst = tmp_path / "out"
        src.mkdir()
        _write(src, {"tables/a.md": "# Has Title\n\nBody without description block.\n"})

        bundle(src, dst)

        content = (dst / "tables" / "a.md").read_text()
        assert 'title: "Has Title"' in content
        assert "description:" in content

    def test_lenient_no_title(self, tmp_path: Path):
        src = tmp_path / "src"
        dst = tmp_path / "out"
        src.mkdir()
        _write(src, {"tables/a.md": "No heading here.\n> Desc.\n"})

        bundle(src, dst)

        content = (dst / "tables" / "a.md").read_text()
        assert "title:" not in content
        assert 'type: "tables"' in content

    def test_lenient_no_heading(self, tmp_path: Path):
        src = tmp_path / "src"
        dst = tmp_path / "out"
        src.mkdir()
        _write(src, {"tables/a.md": "Just plain text.\n"})

        bundle(src, dst)

        assert (dst / "tables" / "a.md").exists()

    def test_index_uses_stem_when_no_title(self, tmp_path: Path):
        src = tmp_path / "src"
        dst = tmp_path / "out"
        src.mkdir()
        _write(src, {"tables/bad.md": "No heading.\n> Desc.\n"})

        bundle(src, dst)

        index = (dst / "tables" / "index.md").read_text()
        assert "[bad](bad.md)" in index
        assert "[](" not in index


# ---------------------------------------------------------------------------
# list_concepts()
# ---------------------------------------------------------------------------


class TestListConcepts:
    def test_lists_concepts(self, tmp_path: Path):
        src = tmp_path / "src"
        dst = tmp_path / "out"
        src.mkdir()
        _write(
            src,
            {
                "tables/a.md": "# A\n\n> Desc.\n",
                "datasets/b.md": "# B\n\n> Desc B.\n",
            },
        )
        bundle(src, dst)

        cids = list_concepts(dst)

        assert "tables/a" in cids
        assert "datasets/b" in cids

    def test_sorted_order(self, tmp_path: Path):
        src = tmp_path / "src"
        dst = tmp_path / "out"
        src.mkdir()
        _write(
            src,
            {
                "tables/orders.md": "# Orders\n\n> One row.\n",
                "playbooks/incident.md": "# Incident\n\n> Playbook.\n",
                "tables/customers.md": "# Customers\n\n> All.\n",
            },
        )
        bundle(src, dst)

        cids = list_concepts(dst)

        assert cids == sorted(cids)

    def test_excludes_reserved(self, tmp_path: Path):
        src = tmp_path / "src"
        dst = tmp_path / "out"
        src.mkdir()
        _write(src, {"tables/a.md": "# A\n\n> Desc.\n"})
        bundle(src, dst)

        cids = list_concepts(dst)
        assert "index" not in cids

    def test_root_concept(self, tmp_path: Path):
        src = tmp_path / "src"
        dst = tmp_path / "out"
        src.mkdir()
        _write(src, {"ref.md": "# Ref\n\n> Desc.\n"})
        bundle(src, dst)

        cids = list_concepts(dst)
        assert cids == ["ref"]

    def test_deeply_nested(self, tmp_path: Path):
        src = tmp_path / "src"
        dst = tmp_path / "out"
        src.mkdir()
        _write(src, {"a/b/c/deep.md": "# Deep\n\n> Nested.\n"})
        bundle(src, dst)

        cids = list_concepts(dst)
        assert cids == ["a/b/c/deep"]

    def test_readme_is_concept(self, tmp_path: Path):
        # README.md is reserved by bundle but NOT by the OKF spec.
        # To test list sees it, we construct the bundle manually.
        d = tmp_path / "bundle"
        d.mkdir()
        (d / "README.md").write_text("---\ntype: readme\n---\n\nReadme body.")

        cids = list_concepts(d)
        assert "README" in cids

    def test_empty_bundle(self, tmp_path: Path):
        d = tmp_path / "bundle"
        d.mkdir()

        cids = list_concepts(d)
        assert cids == []

    def test_not_conformant(self, tmp_path: Path):
        d = tmp_path / "raw"
        d.mkdir()
        _write(d, {"plain.md": "# Title\n\n> Desc.\n\nBody."})

        with pytest.raises(ValueError, match="not an OKF-conformant"):
            list_concepts(d)

    def test_not_a_dir(self, tmp_path: Path):
        with pytest.raises(NotADirectoryError):
            list_concepts(tmp_path / "nope")


# ---------------------------------------------------------------------------
# show_concept()
# ---------------------------------------------------------------------------


class TestShowConcept:
    def test_shows_concept(self, tmp_path: Path):
        src = tmp_path / "src"
        dst = tmp_path / "out"
        src.mkdir()
        _write(
            src,
            {"tables/orders.md": "# Orders\n\n> Customer orders.\n\nBody text."},
        )
        bundle(src, dst)

        content = show_concept(dst, "tables/orders")

        assert isinstance(content, ConceptContent)
        assert content.frontmatter["type"] == "tables"
        assert content.frontmatter["title"] == "Orders"
        assert "Body text." in content.body

    def test_root_concept(self, tmp_path: Path):
        src = tmp_path / "src"
        dst = tmp_path / "out"
        src.mkdir()
        _write(src, {"ref.md": "# Ref\n\n> Desc.\n\nRoot body."})
        bundle(src, dst)

        content = show_concept(dst, "ref")
        assert "Root body." in content.body

    def test_deeply_nested(self, tmp_path: Path):
        src = tmp_path / "src"
        dst = tmp_path / "out"
        src.mkdir()
        _write(src, {"a/b/c/deep.md": "# Deep\n\n> Nested.\n\nDeep body."})
        bundle(src, dst)

        content = show_concept(dst, "a/b/c/deep")
        assert "Deep body." in content.body

    def test_not_found(self, tmp_path: Path):
        src = tmp_path / "src"
        dst = tmp_path / "out"
        src.mkdir()
        _write(src, {"tables/a.md": "# A\n\n> Desc.\n"})
        bundle(src, dst)

        with pytest.raises(FileNotFoundError):
            show_concept(dst, "tables/nope")

    def test_reserved_rejected(self, tmp_path: Path):
        src = tmp_path / "src"
        dst = tmp_path / "out"
        src.mkdir()
        _write(src, {"tables/a.md": "# A\n\n> Desc.\n"})
        bundle(src, dst)

        with pytest.raises(ValueError, match="reserved"):
            show_concept(dst, "index")

    def test_path_traversal(self, tmp_path: Path):
        src = tmp_path / "src"
        dst = tmp_path / "out"
        src.mkdir()
        _write(src, {"tables/a.md": "# A\n\n> Desc.\n"})
        bundle(src, dst)

        with pytest.raises(ValueError, match="outside"):
            show_concept(dst, "../secret")

    def test_not_a_dir(self, tmp_path: Path):
        with pytest.raises(NotADirectoryError):
            show_concept(tmp_path / "nope", "x")

    def test_not_conformant(self, tmp_path: Path):
        d = tmp_path / "raw"
        d.mkdir()
        _write(d, {"plain.md": "# Title\n\n> Desc.\n\nBody."})

        with pytest.raises(ValueError, match="not an OKF-conformant"):
            show_concept(d, "plain")


# ---------------------------------------------------------------------------
# validate()
# ---------------------------------------------------------------------------


class TestValidate:
    def test_valid_bundle(self, tmp_path: Path):
        src = tmp_path / "src"
        dst = tmp_path / "out"
        src.mkdir()
        _write(src, {"tables/a.md": "# A\n\n> Desc.\n"})
        bundle(src, dst)

        result = validate(dst)

        assert isinstance(result, ValidateResult)
        assert result.ok
        assert result.errors == []

    def test_non_conformant(self, tmp_path: Path):
        d = tmp_path / "raw"
        d.mkdir()
        _write(d, {"plain.md": "# Title\n\n> Desc.\n\nBody."})

        result = validate(d)

        assert not result.ok
        assert len(result.errors) > 0

    def test_empty_dir(self, tmp_path: Path):
        d = tmp_path / "empty"
        d.mkdir()

        result = validate(d)

        assert not result.ok
        assert "No .md files found" in result.errors[0]

    def test_not_a_dir(self, tmp_path: Path):
        with pytest.raises(NotADirectoryError):
            validate(tmp_path / "nope")

    def test_missing_frontmatter(self, tmp_path: Path):
        d = tmp_path / "bundle"
        d.mkdir()
        _write(d, {"bad.md": "# Title\n\nNo frontmatter."})

        result = validate(d)
        assert not result.ok
        assert any("missing or unparseable" in e for e in result.errors)

    def test_empty_type(self, tmp_path: Path):
        d = tmp_path / "bundle"
        d.mkdir()
        _write(d, {"bad.md": '---\ntype: ""\n---\n\nBody.'})

        result = validate(d)
        assert not result.ok
        assert any("missing non-empty 'type'" in e for e in result.errors)

    def test_whitespace_only_type(self, tmp_path: Path):
        d = tmp_path / "bundle"
        d.mkdir()
        _write(d, {"bad.md": '---\ntype: "   "\n---\n\nBody.'})

        result = validate(d)
        assert not result.ok
        assert any("missing non-empty 'type'" in e for e in result.errors)

    def test_non_string_type(self, tmp_path: Path):
        d = tmp_path / "bundle"
        d.mkdir()
        _write(d, {"bad.md": "---\ntype: true\n---\n\nBody."})

        result = validate(d)
        assert not result.ok
        assert any("missing non-empty 'type'" in e for e in result.errors)

    def test_malformed_yaml(self, tmp_path: Path):
        d = tmp_path / "bundle"
        d.mkdir()
        _write(d, {"bad.md": "---\ntype: [unclosed\n---\n\nBody."})

        result = validate(d)
        assert not result.ok
        assert any("missing or unparseable" in e for e in result.errors)

    def test_non_dict_frontmatter(self, tmp_path: Path):
        d = tmp_path / "bundle"
        d.mkdir()
        _write(d, {"bad.md": "---\n- item1\n- item2\n---\n\nBody."})

        result = validate(d)
        assert not result.ok
        assert any("missing or unparseable" in e for e in result.errors)

    def test_non_utf8_file(self, tmp_path: Path):
        d = tmp_path / "bundle"
        d.mkdir()
        _write(d, {"valid.md": "---\ntype: ref\n---\n\nBody."})
        (d / "bad.md").write_bytes(b"\xff\xfe# Title\n> Desc\n")

        result = validate(d)
        assert not result.ok
        assert any("not valid UTF-8" in e for e in result.errors)

    def test_index_md_no_frontmatter_ok(self, tmp_path: Path):
        d = tmp_path / "bundle"
        d.mkdir()
        _write(d, {"tables/a.md": "---\ntype: ref\n---\n\nBody."})
        (d / "index.md").write_text("# Contents\n\n* [A](tables/a.md)")

        result = validate(d)
        assert result.ok

    def test_subdir_index_md_with_frontmatter_fails(self, tmp_path: Path):
        d = tmp_path / "bundle"
        d.mkdir()
        _write(d, {"tables/a.md": "---\ntype: ref\n---\n\nBody."})
        (d / "tables" / "index.md").write_text("---\ntitle: Index\n---\n\n# Contents")

        result = validate(d)
        assert not result.ok
        assert any("index.md must not contain frontmatter" in e for e in result.errors)

    def test_root_index_md_okf_version_ok(self, tmp_path: Path):
        d = tmp_path / "bundle"
        d.mkdir()
        _write(d, {"tables/a.md": "---\ntype: ref\n---\n\nBody."})
        (d / "index.md").write_text('---\nokf_version: "0.1"\n---\n\n# Contents')

        result = validate(d)
        assert result.ok

    def test_root_index_md_extra_fields_fails(self, tmp_path: Path):
        d = tmp_path / "bundle"
        d.mkdir()
        _write(d, {"tables/a.md": "---\ntype: ref\n---\n\nBody."})
        (d / "index.md").write_text('---\nokf_version: "0.1"\ntitle: Extra\n---')

        result = validate(d)
        assert not result.ok
        assert any("may only contain" in e for e in result.errors)

    def test_log_md_no_frontmatter_ok(self, tmp_path: Path):
        d = tmp_path / "bundle"
        d.mkdir()
        _write(d, {"tables/a.md": "---\ntype: ref\n---\n\nBody."})
        (d / "log.md").write_text("## 2026-01-01\n\n* Update")

        result = validate(d)
        assert result.ok

    def test_log_md_with_frontmatter_fails(self, tmp_path: Path):
        d = tmp_path / "bundle"
        d.mkdir()
        _write(d, {"tables/a.md": "---\ntype: ref\n---\n\nBody."})
        (d / "log.md").write_text("---\nversion: 1\n---\n\n## Log")

        result = validate(d)
        assert not result.ok
        assert any("log.md must not contain frontmatter" in e for e in result.errors)

    def test_readme_is_concept(self, tmp_path: Path):
        d = tmp_path / "bundle"
        d.mkdir()
        _write(d, {"README.md": "---\ntype: readme\n---\n\nReadme body."})

        result = validate(d)
        assert result.ok

    def test_readme_missing_frontmatter_fails(self, tmp_path: Path):
        d = tmp_path / "bundle"
        d.mkdir()
        _write(d, {"README.md": "Just a readme."})

        result = validate(d)
        assert not result.ok
        assert any("missing or unparseable" in e for e in result.errors)

    def test_agents_md_skipped(self, tmp_path: Path):
        d = tmp_path / "bundle"
        d.mkdir()
        _write(d, {"tables/a.md": "---\ntype: ref\n---\n\nBody."})
        (d / "AGENTS.md").write_text("# KB\n\nNavigation guide.")

        result = validate(d)
        assert result.ok

    def test_multiple_errors(self, tmp_path: Path):
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

        result = validate(d)
        assert not result.ok
        assert len(result.errors) == 2


# ---------------------------------------------------------------------------
# cross-command: bundle → validate/list/show
# ---------------------------------------------------------------------------


class TestWorkflow:
    def test_bundle_then_validate(self, tmp_path: Path):
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

        r = bundle(src, dst)
        assert r.errors == []

        v = validate(dst)
        assert v.ok

    def test_bundle_then_list(self, tmp_path: Path):
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

        bundle(src, dst)
        cids = list_concepts(dst)

        assert "tables/orders" in cids
        assert "tables/customers" in cids

    def test_bundle_then_show(self, tmp_path: Path):
        src = tmp_path / "src"
        dst = tmp_path / "out"
        src.mkdir()
        _write(src, {"tables/orders.md": "# Orders\n\n> One row.\n\nBody."})

        bundle(src, dst)
        content = show_concept(dst, "tables/orders")

        assert "Body." in content.body
