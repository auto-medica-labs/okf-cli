"""Tests for the okf Python API."""

from pathlib import Path

import pytest
import yaml

from okf.api import (
    Bundle,
    BundleResult,
    ConceptContent,
    ValidateResult,
    bundle,
    convert_content,
    convert_file,
    list_concepts,
    list_entries,
    reindex,
    search,
    show_concept,
    validate,
    validate_concept,
    write_concept,
)
from okf.core import parse_frontmatter

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write(dir_path: Path, files: dict[str, str]) -> None:
    for rel, content in files.items():
        p = dir_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")


def _read_frontmatter(path: Path) -> dict:
    return parse_frontmatter(path.read_text(encoding="utf-8")) or {}


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
        fm = _read_frontmatter(dst / "tables" / "a.md")

        assert fm["type"] == "tables"
        assert fm["title"] == "A"
        assert fm["description"] == "Desc A."
        assert isinstance(fm["generated"], dict)
        assert "by" in fm["generated"]
        assert "at" in fm["generated"]

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

    def test_frontmatter_yaml_parseable(self, tmp_path: Path):
        src = tmp_path / "src"
        dst = tmp_path / "out"
        src.mkdir()
        _write(
            src, {"data.md": ("# True/False\n\n> Yes, no, true, false values\n\nBody.")}
        )

        bundle(src, dst, default_type="ref")

        content = (dst / "data.md").read_text()
        fm_text = content.split("---\n", 1)[1].split("\n---", 1)[0]
        fm = yaml.safe_load(fm_text)

        assert isinstance(fm, dict)
        assert fm["type"] == "ref"
        assert fm["title"] == "True/False"
        assert isinstance(fm["generated"], dict)
        assert "by" in fm["generated"]
        assert "at" in fm["generated"]

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
        assert any("Replaced existing" in w for w in result.warnings)

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

    def test_output_inside_input(self, tmp_path: Path):
        src = tmp_path / "src"
        src.mkdir()
        with pytest.raises(ValueError, match="inside input"):
            bundle(src, src / "out")

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
        assert _read_frontmatter(dst / "domain.md")["type"] == "reference"
        assert _read_frontmatter(dst / "tables" / "data.md")["type"] == "tables"

    def test_root_type_from_input_dir(self, tmp_path: Path):
        src = tmp_path / "notes"
        dst = tmp_path / "out"
        src.mkdir()
        _write(src, {"domain.md": "# Domain\n\n> Our domain.\n\nBody."})

        bundle(src, dst)

        assert _read_frontmatter(dst / "domain.md")["type"] == "notes"

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

    def test_strict_fails(self, tmp_path: Path):
        src = tmp_path / "src"
        dst = tmp_path / "out"
        src.mkdir()
        _write(
            src,
            {"tables/orders.md": "# Orders\n\n> One row.\n\nSee [C](customers.md)."},
        )

        result = bundle(src, dst, strict=True)

        assert result.files_written == 0
        assert any("strict link check failed" in e.lower() for e in result.errors)

    def test_force_strict_failure_preserves_existing_output(self, tmp_path: Path):
        src = tmp_path / "src"
        dst = tmp_path / "out"
        src.mkdir()
        dst.mkdir()
        (dst / "important.txt").write_text("keep this bundle")
        _write(
            src,
            {
                "tables/orders.md": (
                    "# Orders\n\n> One row.\n\nSee [C](customers.md)."
                ),
            },
        )

        result = bundle(src, dst, force=True, strict=True)

        assert result.errors
        assert (dst / "important.txt").read_text() == "keep this bundle"
        assert not list(tmp_path.glob(".out.staging-*"))

    def test_force_write_failure_preserves_existing_output(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        import okf.api as api

        src = tmp_path / "src"
        dst = tmp_path / "out"
        src.mkdir()
        dst.mkdir()
        (dst / "important.txt").write_text("keep this bundle")
        _write(src, {"tables/a.md": "# A\n\n> Desc.\n"})

        def fail_write(*args, **kwargs):
            raise ValueError("simulated write failure")

        monkeypatch.setattr(api, "_write_concept", fail_write)
        result = bundle(src, dst, force=True)

        assert result.errors == ["tables/a.md: simulated write failure"]
        assert (dst / "important.txt").read_text() == "keep this bundle"
        assert not list(tmp_path.glob(".out.staging-*"))

    def test_strict_passes(self, tmp_path: Path):
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

        result = bundle(src, dst, strict=True)

        assert result.files_written == 2
        assert result.errors == []
        assert not (dst / "AGENTS.md").exists()

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

        fm = _read_frontmatter(dst / "tables" / "a.md")
        assert fm["title"] == "Has Title"
        assert "description" in fm

    def test_lenient_no_title(self, tmp_path: Path):
        src = tmp_path / "src"
        dst = tmp_path / "out"
        src.mkdir()
        _write(src, {"tables/a.md": "No heading here.\n> Desc.\n"})

        bundle(src, dst)

        fm = _read_frontmatter(dst / "tables" / "a.md")
        assert "title" not in fm
        assert fm["type"] == "tables"

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

    def test_dry_run_no_writes(self, tmp_path: Path):
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

        result = bundle(src, dst, dry_run=True)

        assert result.files_written == 2
        assert result.errors == []
        assert not dst.exists()

    def test_dry_run_reports_warnings(self, tmp_path: Path):
        src = tmp_path / "src"
        dst = tmp_path / "out"
        src.mkdir()
        _write(
            src,
            {"tables/orders.md": "# Orders\n\n> One row.\n\nSee [C](customers.md)."},
        )

        result = bundle(src, dst, dry_run=True)

        assert result.files_written == 1
        assert any("not found in bundle" in w for w in result.warnings)
        assert not dst.exists()

    def test_dry_run_force_does_not_delete_existing(self, tmp_path: Path):
        src = tmp_path / "src"
        dst = tmp_path / "out"
        src.mkdir()
        dst.mkdir()
        (dst / "old.txt").write_text("preserve me")
        _write(src, {"tables/a.md": "# A\n\n> Desc.\n"})

        result = bundle(src, dst, force=True, dry_run=True)

        assert result.files_written == 1
        assert any("Would replace existing" in w for w in result.warnings)
        assert (dst / "old.txt").exists()
        assert (dst / "old.txt").read_text() == "preserve me"

    def test_dry_run_no_force_when_output_exists(self, tmp_path: Path):
        src = tmp_path / "src"
        dst = tmp_path / "out"
        src.mkdir()
        dst.mkdir()
        (dst / "old.txt").write_text("preserve me")
        _write(src, {"tables/a.md": "# A\n\n> Desc.\n"})

        result = bundle(src, dst, dry_run=True)

        assert result.files_written == 1
        assert result.errors == []
        assert not any("Would replace existing" in w for w in result.warnings)
        assert (dst / "old.txt").exists()

    def test_dry_run_strict_still_fails(self, tmp_path: Path):
        src = tmp_path / "src"
        dst = tmp_path / "out"
        src.mkdir()
        _write(
            src,
            {"tables/orders.md": "# Orders\n\n> One row.\n\nSee [C](customers.md)."},
        )

        result = bundle(src, dst, strict=True, dry_run=True)

        assert result.files_written == 0
        assert any("strict link check failed" in e.lower() for e in result.errors)
        assert not dst.exists()

    def test_preserves_input_frontmatter_fields(self, tmp_path: Path):
        src = tmp_path / "src"
        dst = tmp_path / "out"
        src.mkdir()
        _write(
            src,
            {
                "tables/orders.md": (
                    "---\n"
                    "tags: [sales, orders]\n"
                    "resource: https://example.com/orders\n"
                    "---\n\n"
                    "# Orders\n\n> One row.\n\nBody."
                )
            },
        )

        bundle(src, dst)

        fm = _read_frontmatter(dst / "tables" / "orders.md")
        assert fm["type"] == "tables"
        assert fm["tags"] == ["sales", "orders"]
        assert fm["resource"] == "https://example.com/orders"

    def test_preserves_provenance_trust_lifecycle_fields(self, tmp_path: Path):
        src = tmp_path / "src"
        dst = tmp_path / "out"
        src.mkdir()
        _write(
            src,
            {
                "tables/orders.md": (
                    "---\n"
                    "sources:\n"
                    "  - id: policy\n"
                    "    resource: https://example.com/policy\n"
                    "verified:\n"
                    "  by: human:ahormati\n"
                    '  at: "2026-06-25T09:00:00Z"\n'
                    "status: stable\n"
                    'stale_after: "2026-09-23"\n'
                    'usage_window: {from: "2026-06-01", to: "2026-06-30"}\n'
                    "---\n\n"
                    "# Orders\n\n> One row.\n\nBody."
                )
            },
        )

        bundle(src, dst)

        fm = _read_frontmatter(dst / "tables" / "orders.md")
        assert fm["sources"] == [
            {"id": "policy", "resource": "https://example.com/policy"}
        ]
        assert fm["verified"] == {"by": "human:ahormati", "at": "2026-06-25T09:00:00Z"}
        assert fm["status"] == "stable"
        assert fm["stale_after"] == "2026-09-23"
        assert fm["usage_window"] == {"from": "2026-06-01", "to": "2026-06-30"}

    def test_preserves_attested_computation_fields(self, tmp_path: Path):
        src = tmp_path / "src"
        dst = tmp_path / "out"
        src.mkdir()
        _write(
            src,
            {
                "computations/revenue.md": (
                    "---\n"
                    "runtime: bigquery\n"
                    "parameters:\n"
                    "  - {name: year, type: integer, required: true}\n"
                    "computation: references/computations/revenue.sql\n"
                    "executor:\n"
                    "  resource: references/skills/run-on-bq.md\n"
                    "  receipt: [job_id, executed_sql, result]\n"
                    "attester:\n"
                    "  resource: references/attesters/revenue.py\n"
                    "---\n\n"
                    "# Revenue\n\n> Compute revenue.\n\nSELECT 1."
                )
            },
        )

        bundle(src, dst)

        fm = _read_frontmatter(dst / "computations" / "revenue.md")
        assert fm["type"] == "computations"
        assert fm["runtime"] == "bigquery"
        assert fm["parameters"] == [
            {"name": "year", "type": "integer", "required": True}
        ]
        assert fm["computation"] == "references/computations/revenue.sql"
        assert fm["executor"] == {
            "resource": "references/skills/run-on-bq.md",
            "receipt": ["job_id", "executed_sql", "result"],
        }
        assert fm["attester"] == {"resource": "references/attesters/revenue.py"}

    def test_input_title_description_override_parsed_body(self, tmp_path: Path):
        src = tmp_path / "src"
        dst = tmp_path / "out"
        src.mkdir()
        _write(
            src,
            {
                "tables/orders.md": (
                    "---\n"
                    "title: Frontmatter Title\n"
                    "description: Frontmatter description.\n"
                    "---\n\n"
                    "# Body Title\n\n> Body description.\n\nBody."
                )
            },
        )

        bundle(src, dst)

        fm = _read_frontmatter(dst / "tables" / "orders.md")
        assert fm["title"] == "Frontmatter Title"
        assert fm["description"] == "Frontmatter description."

    def test_cli_type_overrides_input_type(self, tmp_path: Path):
        src = tmp_path / "src"
        dst = tmp_path / "out"
        src.mkdir()
        _write(
            src,
            {
                "tables/orders.md": (
                    "---\ntype: ignored\n---\n\n# Orders\n\n> One row.\n\nBody."
                )
            },
        )

        bundle(src, dst)

        fm = _read_frontmatter(dst / "tables" / "orders.md")
        assert fm["type"] == "tables"

    def test_generated_is_always_overwritten(self, tmp_path: Path):
        src = tmp_path / "src"
        dst = tmp_path / "out"
        src.mkdir()
        _write(
            src,
            {
                "tables/orders.md": (
                    "---\n"
                    "generated: {by: old/actor, at: 2020-01-01T00:00:00Z}\n"
                    "---\n\n"
                    "# Orders\n\n> One row.\n\nBody."
                )
            },
        )

        bundle(src, dst)

        fm = _read_frontmatter(dst / "tables" / "orders.md")
        assert fm["generated"]["by"].startswith("okf-cli/")
        assert "2020-01-01" not in fm["generated"]["at"]

    def test_okf_version_dropped_from_concept_files(self, tmp_path: Path):
        src = tmp_path / "src"
        dst = tmp_path / "out"
        src.mkdir()
        _write(
            src,
            {
                "tables/orders.md": (
                    "---\n"
                    "okf_version: '0.2'\n"
                    "tags: [sales]\n"
                    "---\n\n"
                    "# Orders\n\n> One row.\n\nBody."
                )
            },
        )

        bundle(src, dst)

        fm = _read_frontmatter(dst / "tables" / "orders.md")
        assert "okf_version" not in fm
        assert fm["tags"] == ["sales"]

    def test_malformed_frontmatter_normal_mode_fallback(self, tmp_path: Path):
        src = tmp_path / "src"
        dst = tmp_path / "out"
        src.mkdir()
        _write(
            src,
            {
                "tables/orders.md": (
                    "---\ntype: [unclosed\n---\n\n# Orders\n\n> One row.\n\nBody."
                )
            },
        )

        result = bundle(src, dst)

        assert result.errors == []
        assert result.files_written == 1
        text = (dst / "tables" / "orders.md").read_text()
        assert "type: tables" in text

    def test_malformed_frontmatter_strict_mode_fails(self, tmp_path: Path):
        src = tmp_path / "src"
        dst = tmp_path / "out"
        src.mkdir()
        _write(
            src,
            {
                "tables/orders.md": (
                    "---\ntype: [unclosed\n---\n\n# Orders\n\n> One row.\n\nBody."
                )
            },
        )

        result = bundle(src, dst, strict=True)

        assert result.files_written == 0
        assert any("Malformed YAML frontmatter" in e for e in result.errors)

    def test_frontmatter_body_links_still_checked(self, tmp_path: Path):
        src = tmp_path / "src"
        dst = tmp_path / "out"
        src.mkdir()
        _write(
            src,
            {
                "tables/orders.md": (
                    "---\n"
                    "tags: [sales]\n"
                    "---\n\n"
                    "# Orders\n\n> One row.\n\nSee [C](customers.md)."
                )
            },
        )

        result = bundle(src, dst)

        assert any("not found in bundle" in w for w in result.warnings)


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
# list_entries()
# ---------------------------------------------------------------------------


class TestListEntries:
    def test_lists_with_metadata(self, tmp_path: Path):
        src = tmp_path / "src"
        dst = tmp_path / "out"
        src.mkdir()
        _write(
            src,
            {
                "tables/orders.md": "# Orders\n\n> Customer orders.\n\nBody.",
                "datasets/sales.md": "# Sales\n\n> Sales dataset.\n\nBody.",
            },
        )
        bundle(src, dst)

        entries = list_entries(dst)

        assert isinstance(entries, list)
        assert all(isinstance(e, dict) for e in entries)
        keys = ("id", "type", "title", "description")
        assert all(k in e for e in entries for k in keys)
        assert {"tables/orders", "datasets/sales"} == {e["id"] for e in entries}

    def test_entries_have_types(self, tmp_path: Path):
        src = tmp_path / "src"
        dst = tmp_path / "out"
        src.mkdir()
        _write(
            src,
            {
                "tables/a.md": "# A\n\n> Desc.\n\nBody.",
                "playbooks/b.md": "# B\n\n> Playbook.\n\nBody.",
            },
        )
        bundle(src, dst)

        entries = list_entries(dst)
        by_id = {e["id"]: e for e in entries}

        assert by_id["tables/a"]["type"] == "tables"
        assert by_id["playbooks/b"]["type"] == "playbooks"

    def test_missing_title_shows_empty(self, tmp_path: Path):
        src = tmp_path / "src"
        dst = tmp_path / "out"
        src.mkdir()
        _write(src, {"tables/bad.md": "No heading.\n> Desc.\n"})
        bundle(src, dst)

        entries = list_entries(dst)
        assert entries[0]["title"] == ""

    def test_missing_description_shows_empty(self, tmp_path: Path):
        # Construct a bundle manually so description is truly absent.
        d = tmp_path / "bundle"
        d.mkdir()
        (d / "tables").mkdir()
        (d / "tables" / "minimal.md").write_text(
            "---\ntype: tables\ntitle: Minimal\n---\n\nJust body."
        )

        entries = list_entries(d)
        assert entries[0]["description"] == ""

    def test_excludes_reserved(self, tmp_path: Path):
        src = tmp_path / "src"
        dst = tmp_path / "out"
        src.mkdir()
        _write(src, {"tables/a.md": "# A\n\n> Desc.\n"})
        bundle(src, dst)

        entries = list_entries(dst)
        ids = {e["id"] for e in entries}
        assert "index" not in ids

    def test_sorted_order(self, tmp_path: Path):
        src = tmp_path / "src"
        dst = tmp_path / "out"
        src.mkdir()
        _write(
            src,
            {
                "tables/orders.md": "# Orders\n\n> One row.\n",
                "playbooks/incident.md": "# Incident\n\n> Playbook.\n",
            },
        )
        bundle(src, dst)

        entries = list_entries(dst)
        ids = [e["id"] for e in entries]
        assert ids == sorted(ids)

    def test_not_conformant(self, tmp_path: Path):
        d = tmp_path / "raw"
        d.mkdir()
        _write(d, {"plain.md": "# Title\n\n> Desc.\n\nBody."})

        with pytest.raises(ValueError, match="not an OKF-conformant"):
            list_entries(d)

    def test_not_a_dir(self, tmp_path: Path):
        with pytest.raises(NotADirectoryError):
            list_entries(tmp_path / "nope")


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
        (d / "index.md").write_text('---\nokf_version: "0.2"\n---\n\n# Contents')

        result = validate(d)
        assert result.ok

    def test_root_index_md_extra_fields_fails(self, tmp_path: Path):
        d = tmp_path / "bundle"
        d.mkdir()
        _write(d, {"tables/a.md": "---\ntype: ref\n---\n\nBody."})
        (d / "index.md").write_text('---\nokf_version: "0.2"\ntitle: Extra\n---')

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
# reindex()
# ---------------------------------------------------------------------------


class TestReindex:
    def test_updates_stale_root_index(self, tmp_path: Path):
        src = tmp_path / "src"
        dst = tmp_path / "out"
        src.mkdir()
        _write(src, {"tables/orders.md": "# Orders\n\n> One row.\n\nBody."})
        bundle(src, dst)
        convert_content(
            "# Fresh Concept\n\n> New root concept.\n\nBody.",
            dst / "fresh.md",
            type_="reference",
        )
        assert "Fresh Concept" not in (dst / "index.md").read_text()

        result = reindex(dst)

        assert isinstance(result, BundleResult)
        assert result.output_dir == dst
        assert "[Fresh Concept](fresh.md)" in (dst / "index.md").read_text()

    def test_updates_subdir_index(self, tmp_path: Path):
        src = tmp_path / "src"
        dst = tmp_path / "out"
        src.mkdir()
        _write(src, {"tables/orders.md": "# Orders\n\n> One row.\n\nBody."})
        bundle(src, dst)
        convert_content(
            "# Extra\n\n> Extra table.\n\nBody.",
            dst / "tables" / "extra.md",
            type_="tables",
        )

        reindex(dst)

        assert "[Extra](extra.md)" in (dst / "tables" / "index.md").read_text()

    def test_adds_subdir_to_root_index(self, tmp_path: Path):
        src = tmp_path / "src"
        dst = tmp_path / "out"
        src.mkdir()
        _write(src, {"tables/orders.md": "# Orders\n\n> One row.\n\nBody."})
        bundle(src, dst)
        convert_content(
            "# Q1\n\n> First quarter.\n\nBody.",
            dst / "reports" / "q1.md",
            type_="reports",
        )

        reindex(dst)

        assert "[reports](reports/)" in (dst / "index.md").read_text()

    def test_idempotent(self, tmp_path: Path):
        src = tmp_path / "src"
        dst = tmp_path / "out"
        src.mkdir()
        _write(
            src,
            {
                "tables/orders.md": "# Orders\n\n> One row.\n\nBody.",
                "root.md": "# Root\n\n> Root concept.\n\nBody.",
            },
        )
        bundle(src, dst)

        first = reindex(dst)
        root_first = (dst / "index.md").read_text()
        sub_first = (dst / "tables" / "index.md").read_text()

        second = reindex(dst)

        assert first.files_written == second.files_written
        assert (dst / "index.md").read_text() == root_first
        assert (dst / "tables" / "index.md").read_text() == sub_first

    def test_keeps_root_okf_version(self, tmp_path: Path):
        src = tmp_path / "src"
        dst = tmp_path / "out"
        src.mkdir()
        _write(src, {"tables/a.md": "# A\n\n> Desc.\n"})
        bundle(src, dst)

        reindex(dst)

        assert _read_frontmatter(dst / "index.md") == {"okf_version": "0.2"}

    def test_passes_validate(self, tmp_path: Path):
        src = tmp_path / "src"
        dst = tmp_path / "out"
        src.mkdir()
        _write(src, {"tables/orders.md": "# Orders\n\n> One row.\n\nBody."})
        bundle(src, dst)
        convert_content(
            "# Fresh\n\n> New.\n\nBody.", dst / "tables" / "fresh.md", type_="tables"
        )

        reindex(dst)

        assert validate(dst).ok

    def test_rejects_non_conformant_bundle(self, tmp_path: Path):
        d = tmp_path / "raw"
        d.mkdir()
        _write(d, {"plain.md": "# Title\n\n> Desc.\n\nBody."})

        with pytest.raises(ValueError, match="not an OKF-conformant"):
            reindex(d)

    def test_files_written_count(self, tmp_path: Path):
        src = tmp_path / "src"
        dst = tmp_path / "out"
        src.mkdir()
        _write(src, {"tables/a.md": "# A\n\n> Desc.\n"})
        bundle(src, dst)

        result = reindex(dst)

        # Root index plus one subdirectory index.
        assert result.files_written == 2

    def test_not_a_dir(self, tmp_path: Path):
        with pytest.raises(NotADirectoryError):
            reindex(tmp_path / "nope")


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

    def test_bundle_then_read(self, tmp_path: Path):
        src = tmp_path / "src"
        dst = tmp_path / "out"
        src.mkdir()
        _write(src, {"tables/orders.md": "# Orders\n\n> One row.\n\nBody."})

        bundle(src, dst)
        content = show_concept(dst, "tables/orders")

        assert "Body." in content.body


# ---------------------------------------------------------------------------
# convert_file()
# ---------------------------------------------------------------------------


class TestConvertFile:
    def test_basic(self, tmp_path: Path):
        src = tmp_path / "input.md"
        dst = tmp_path / "output.md"
        src.write_text("# Orders\n\n> One row per order.\n\nBody.", encoding="utf-8")

        result = convert_file(src, dst, type_="tables")

        assert isinstance(result, BundleResult)
        assert result.files_written == 1
        assert result.errors == []
        assert dst.exists()

    def test_frontmatter_content(self, tmp_path: Path):
        src = tmp_path / "input.md"
        dst = tmp_path / "output.md"
        src.write_text("# Orders\n\n> One row per order.\n\nBody.", encoding="utf-8")

        convert_file(src, dst, type_="tables")
        fm = _read_frontmatter(dst)

        assert fm["type"] == "tables"
        assert fm["title"] == "Orders"
        assert fm["description"] == "One row per order."
        assert isinstance(fm["generated"], dict)
        assert "by" in fm["generated"]
        assert "at" in fm["generated"]

    def test_frontmatter_valid_yaml(self, tmp_path: Path):
        src = tmp_path / "input.md"
        dst = tmp_path / "output.md"
        src.write_text("# A\n\n> Desc.\n\nBody.", encoding="utf-8")

        convert_file(src, dst, type_="ref")
        text = dst.read_text()

        fm_str = text.split("---\n")[1]
        fm = yaml.safe_load(fm_str)
        assert isinstance(fm, dict)
        assert fm["type"] == "ref"

    def test_body_preserved(self, tmp_path: Path):
        src = tmp_path / "input.md"
        dst = tmp_path / "output.md"
        src.write_text("# X\n\n> Desc.\n\nBody content.", encoding="utf-8")

        convert_file(src, dst, type_="ref")
        text = dst.read_text()

        assert "Body content." in text

    def test_missing_input(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError, match="not found"):
            convert_file(tmp_path / "nope.md", tmp_path / "out.md", type_="ref")

    def test_creates_parent_dirs(self, tmp_path: Path):
        src = tmp_path / "input.md"
        dst = tmp_path / "sub" / "dir" / "output.md"
        src.write_text("# X\n\n> Desc.\n\nBody.", encoding="utf-8")

        convert_file(src, dst, type_="ref")

        assert dst.exists()

    def test_lenient_parse(self, tmp_path: Path):
        src = tmp_path / "input.md"
        dst = tmp_path / "output.md"
        src.write_text("Just some text.", encoding="utf-8")

        convert_file(src, dst, type_="ref")
        text = dst.read_text()

        assert _read_frontmatter(dst)["type"] == "ref"
        assert "Just some text." in text

    def test_preserves_input_frontmatter(self, tmp_path: Path):
        src = tmp_path / "input.md"
        dst = tmp_path / "output.md"
        src.write_text(
            "---\n"
            "tags: [a, b]\n"
            "resource: https://example.com\n"
            "---\n\n"
            "# Title\n\n> Desc.\n\nBody.",
            encoding="utf-8",
        )

        convert_file(src, dst, type_="ref")
        fm = _read_frontmatter(dst)

        assert fm["type"] == "ref"
        assert fm["tags"] == ["a", "b"]
        assert fm["resource"] == "https://example.com"
        assert "generated" in fm

    def test_overwrites_input_generated(self, tmp_path: Path):
        src = tmp_path / "input.md"
        dst = tmp_path / "output.md"
        src.write_text(
            "---\n"
            "generated: {by: old, at: 2020-01-01T00:00:00Z}\n"
            "---\n\n"
            "# Title\n\n> Desc.\n\nBody.",
            encoding="utf-8",
        )

        convert_file(src, dst, type_="ref")
        fm = _read_frontmatter(dst)

        assert fm["generated"]["by"].startswith("okf-cli/")


# ---------------------------------------------------------------------------
# convert_content()
# ---------------------------------------------------------------------------


class TestConvertContent:
    def test_basic(self, tmp_path: Path):
        dst = tmp_path / "output.md"
        content = "# Orders\n\n> One row per order.\n\nBody."

        result = convert_content(content, dst, type_="tables")

        assert isinstance(result, BundleResult)
        assert result.files_written == 1
        assert dst.exists()

    def test_frontmatter_content(self, tmp_path: Path):
        dst = tmp_path / "output.md"
        content = "# Orders\n\n> One row per order.\n\nBody."

        convert_content(content, dst, type_="tables")
        fm = _read_frontmatter(dst)

        assert fm["type"] == "tables"
        assert fm["title"] == "Orders"
        assert fm["description"] == "One row per order."
        assert "generated" not in fm

    def test_body_preserved(self, tmp_path: Path):
        dst = tmp_path / "output.md"
        content = "# X\n\n> Desc.\n\nBody content."

        convert_content(content, dst, type_="ref")
        text = dst.read_text()

        assert "Body content." in text

    def test_creates_parent_dirs(self, tmp_path: Path):
        dst = tmp_path / "sub" / "dir" / "output.md"

        convert_content("# X\n\n> Desc.\n\nBody.", dst, type_="ref")

        assert dst.exists()

    def test_lenient_parse(self, tmp_path: Path):
        dst = tmp_path / "output.md"

        convert_content("Just some text.", dst, type_="ref")
        text = dst.read_text()

        assert _read_frontmatter(dst)["type"] == "ref"
        assert "Just some text." in text

    def test_preserves_input_frontmatter(self, tmp_path: Path):
        dst = tmp_path / "output.md"
        content = (
            "---\n"
            "tags: [a, b]\n"
            "resource: https://example.com\n"
            "---\n\n"
            "# Title\n\n> Desc.\n\nBody."
        )

        convert_content(content, dst, type_="ref")
        fm = _read_frontmatter(dst)

        assert fm["type"] == "ref"
        assert fm["tags"] == ["a", "b"]
        assert fm["resource"] == "https://example.com"
        assert "generated" not in fm

    def test_drops_input_generated(self, tmp_path: Path):
        dst = tmp_path / "output.md"
        content = (
            "---\n"
            "generated: {by: old, at: 2020-01-01T00:00:00Z}\n"
            "---\n\n"
            "# Title\n\n> Desc.\n\nBody."
        )

        convert_content(content, dst, type_="ref")
        fm = _read_frontmatter(dst)

        assert "generated" not in fm


# ---------------------------------------------------------------------------
# Loaded bundle, search, sections, links, writing
# ---------------------------------------------------------------------------

_SAMPLE_FILES = {
    "entities/import/im-dec.md": (
        "---\ntype: Entity\ntitle: ImDec\n"
        "description: Import declaration header.\n"
        "tags: [import]\nsymbols: [CDS.iXIMPLE.BC.ImDec]\n"
        "---\n\n# Card\n\nHeader row.\n\n# Schema\n\n| Column |\n"
    ),
    "features/import/declaration-entry.md": (
        "---\ntype: Feature\ntitle: Import declaration entry\n"
        "description: Create and submit an import declaration.\n"
        "tags: [import, declaration]\n"
        "ui_text:\n  - ใบขนสินค้าขาเข้า\n"
        "generated: {by: kb-gen/model-x, at: '2026-11-18'}\n"
        "---\n\n# Card\n\nEntry screen to BL.\n\n## Detail\n\nMore.\n\n"
        "# Rules\n\n```\n# not a heading\n```\n\nR1.\n"
    ),
    "features/export/declaration-entry.md": (
        "---\ntype: Feature\ntitle: Export declaration entry\n"
        "description: Create an export declaration.\n"
        "tags: [export, declaration]\nstale_after: 2026-12-31\n"
        "---\n\nBody.\n"
    ),
}


def _sample(tmp_path: Path) -> Path:
    d = tmp_path / "kb"
    _write(d, _SAMPLE_FILES)
    return d


class TestBundleOpen:
    def test_ids_and_entries_match_module_functions(self, tmp_path: Path):
        d = _sample(tmp_path)

        assert Bundle.open(d).ids() == list_concepts(d)
        assert Bundle.open(d).entries() == list_entries(d)
        assert Bundle.open(d).ids() == [
            "entities/import/im-dec",
            "features/export/declaration-entry",
            "features/import/declaration-entry",
        ]

    def test_rejects_nonconformant(self, tmp_path: Path):
        d = _sample(tmp_path)
        _write(d, {"broken.md": "no frontmatter\n"})

        with pytest.raises(ValueError, match="not an OKF-conformant bundle"):
            Bundle.open(d)

    def test_missing_directory(self, tmp_path: Path):
        with pytest.raises(NotADirectoryError):
            Bundle.open(tmp_path / "missing")

    def test_empty_directory_is_a_valid_bundle(self, tmp_path: Path):
        d = tmp_path / "kb"
        d.mkdir()

        assert Bundle.open(d).ids() == []

    def test_refresh_picks_up_add_and_remove(self, tmp_path: Path):
        d = _sample(tmp_path)
        bundle = Bundle.open(d)
        assert bundle.refresh() is False

        _write(d, {"tables/new.md": "---\ntype: Table\ntitle: New\n---\n\nBody."})
        (d / "features" / "export" / "declaration-entry.md").unlink()

        assert bundle.refresh() is True
        assert "tables/new" in bundle.ids()
        assert "features/export/declaration-entry" not in bundle.ids()

    def test_failed_refresh_keeps_previous_state(self, tmp_path: Path):
        d = _sample(tmp_path)
        bundle = Bundle.open(d)
        before = bundle.ids()
        _write(d, {"broken.md": "no frontmatter\n"})

        with pytest.raises(ValueError, match="broken.md"):
            bundle.refresh()

        assert bundle.ids() == before
        (d / "broken.md").unlink()
        assert bundle.refresh() is False

    def test_bundle_refresh_picks_up_in_place_edits(self, tmp_path: Path):
        d = _sample(tmp_path)
        bundle = Bundle.open(d)
        target = d / "entities" / "import" / "im-dec.md"
        target.write_text(
            target.read_text().replace("ImDec", "ImDecHeader"), encoding="utf-8"
        )

        assert bundle.refresh() is True
        assert bundle.entries()[0]["title"] == "ImDecHeader"


class TestSearch:
    def test_ranks_by_matching_words(self, tmp_path: Path):
        bundle = Bundle.open(_sample(tmp_path))

        found = bundle.search("import declaration")

        assert found[0]["id"] == "features/import/declaration-entry"
        assert {entry["id"] for entry in found} == {
            "features/import/declaration-entry",
            "features/export/declaration-entry",
            "entities/import/im-dec",
        }

    def test_matches_thai_and_symbols(self, tmp_path: Path):
        bundle = Bundle.open(_sample(tmp_path))

        assert [e["id"] for e in bundle.search("ใบขนสินค้า")] == [
            "features/import/declaration-entry"
        ]
        assert [e["id"] for e in bundle.search("cds.iximple.bc.imdec")] == [
            "entities/import/im-dec"
        ]

    def test_matches_date_and_number_scalars(self, tmp_path: Path):
        bundle = Bundle.open(_sample(tmp_path))

        assert [e["id"] for e in bundle.search("2026-12-31")] == [
            "features/export/declaration-entry"
        ]

    def test_ignores_generated_provenance(self, tmp_path: Path):
        bundle = Bundle.open(_sample(tmp_path))

        assert bundle.search("kb-gen") == []

    def test_type_is_case_insensitive(self, tmp_path: Path):
        bundle = Bundle.open(_sample(tmp_path))

        assert [e["id"] for e in bundle.search(type_="entity")] == [
            "entities/import/im-dec"
        ]

    def test_filters_are_case_insensitive(self, tmp_path: Path):
        bundle = Bundle.open(_sample(tmp_path))

        assert [e["id"] for e in bundle.search(filters={"tags": "EXPORT"})] == [
            "features/export/declaration-entry"
        ]

    def test_filters_on_list_values(self, tmp_path: Path):
        bundle = Bundle.open(_sample(tmp_path))

        found = bundle.search(filters={"ui_text": "ใบขนสินค้าขาเข้า"})

        assert [e["id"] for e in found] == ["features/import/declaration-entry"]

    def test_exact_whole_value_bonus(self, tmp_path: Path):
        bundle = Bundle.open(_sample(tmp_path))

        assert bundle.search("export declaration entry")[0]["title"] == (
            "Export declaration entry"
        )

    def test_limit(self, tmp_path: Path):
        bundle = Bundle.open(_sample(tmp_path))

        assert len(bundle.search("declaration", limit=1)) == 1
        assert len(bundle.search("", limit=None)) == 3
        assert bundle.search("", limit=0) == []

    def test_module_level_search(self, tmp_path: Path):
        d = _sample(tmp_path)

        assert search(d, "imdec")[0]["id"] == "entities/import/im-dec"


class TestReadSection:
    def test_section_until_same_level_heading(self, tmp_path: Path):
        d = _sample(tmp_path)
        content = show_concept(d, "features/import/declaration-entry", section="Card")

        assert content.body == "# Card\n\nEntry screen to BL.\n\n## Detail\n\nMore.\n"

    def test_section_ignores_headings_in_code_fences(self, tmp_path: Path):
        d = _sample(tmp_path)
        content = show_concept(
            d, "features/import/declaration-entry", section="# Rules"
        )

        assert "R1." in content.body

    def test_missing_section_lists_available_headings(self, tmp_path: Path):
        d = _sample(tmp_path)

        with pytest.raises(ValueError, match="Available sections: Card, Detail, Rules"):
            show_concept(d, "features/import/declaration-entry", section="Nope")

    def test_rejects_unsafe_and_reserved_ids(self, tmp_path: Path):
        d = _sample(tmp_path)
        bundle = Bundle.open(d)

        with pytest.raises(ValueError):
            bundle.read("../escape")
        with pytest.raises(ValueError):
            bundle.read("index")

    def test_accepts_link_style_ids(self, tmp_path: Path):
        bundle = Bundle.open(_sample(tmp_path))

        assert bundle.read("/entities/import/im-dec.md").id == "entities/import/im-dec"

    def test_missing_concept(self, tmp_path: Path):
        bundle = Bundle.open(_sample(tmp_path))

        with pytest.raises(FileNotFoundError):
            bundle.read("tables/missing")


class TestReadLinks:
    def test_links_are_resolved_and_deduplicated(self, tmp_path: Path):
        d = tmp_path / "kb"
        _write(
            d,
            {
                "a/x.md": "---\ntype: T\ntitle: X\n---\n\n"
                "[y](y.md) [y again](./y.md) [z](../b/z.md) [gone](/a/gone.md) "
                "[gone again](gone.md) [web](https://example.com) [anchor](#top)\n",
                "a/y.md": "---\ntype: T\ntitle: Y\n---\n\nBody.\n",
                "b/z.md": "---\ntype: T\ntitle: Z\n---\n\nBody.\n",
            },
        )
        bundle = Bundle.open(d)

        # "gone.md" resolves to the same target as "/a/gone.md"; the second
        # occurrence is dropped.
        assert bundle.read("a/x").links == [
            {"target": "y.md", "id": "a/y", "exists": True},
            {"target": "../b/z.md", "id": "b/z", "exists": True},
            {"target": "/a/gone.md", "id": "a/gone", "exists": False},
        ]

    def test_reserved_and_outside_targets_are_omitted(self, tmp_path: Path):
        d = tmp_path / "kb"
        _write(
            d,
            {
                "a/x.md": "---\ntype: T\ntitle: X\n---\n\n"
                "[index](../index.md) [escape](../../outside.md)\n",
            },
        )
        bundle = Bundle.open(d)

        assert bundle.read("a/x").links == []

    def test_links_are_scoped_to_the_returned_section(self, tmp_path: Path):
        d = tmp_path / "kb"
        _write(
            d,
            {
                "a/x.md": "---\ntype: T\ntitle: X\n---\n\n"
                "# Card\n\n[y](y.md)\n\n# Rules\n\n[z](z.md)\n",
                "a/y.md": "---\ntype: T\ntitle: Y\n---\n\nBody.\n",
                "a/z.md": "---\ntype: T\ntitle: Z\n---\n\nBody.\n",
            },
        )
        bundle = Bundle.open(d)

        assert bundle.read("a/x", section="Rules").links == [
            {"target": "z.md", "id": "a/z", "exists": True}
        ]


class TestListdir:
    def test_lists_concepts_and_subdirectories(self, tmp_path: Path):
        bundle = Bundle.open(_sample(tmp_path))

        assert bundle.listdir("") == {
            "path": "",
            "concepts": [],
            "directories": ["entities", "features"],
        }
        listing = bundle.listdir("features/import")
        assert [c["id"] for c in listing["concepts"]] == [
            "features/import/declaration-entry"
        ]
        assert listing["directories"] == []

    def test_dot_segments_are_normalized(self, tmp_path: Path):
        bundle = Bundle.open(_sample(tmp_path))

        assert bundle.listdir("features/../features/import") == bundle.listdir(
            "features/import"
        )

    def test_errors(self, tmp_path: Path):
        bundle = Bundle.open(_sample(tmp_path))

        with pytest.raises(FileNotFoundError):
            bundle.listdir("nothing")
        with pytest.raises(FileNotFoundError, match="is a concept"):
            bundle.listdir("entities/import/im-dec")
        with pytest.raises(ValueError, match="outside"):
            bundle.listdir("../..")


class TestBrowse:
    def test_synthesizes_index_when_missing(self, tmp_path: Path):
        bundle = Bundle.open(_sample(tmp_path))

        text = bundle.browse("features/import")

        assert "[Import declaration entry](declaration-entry.md)" in text

    def test_prefers_existing_index(self, tmp_path: Path):
        d = _sample(tmp_path)
        reindex(d)

        assert Bundle.open(d).browse("features") == (
            d / "features" / "index.md"
        ).read_text(encoding="utf-8")

    def test_errors(self, tmp_path: Path):
        bundle = Bundle.open(_sample(tmp_path))

        with pytest.raises(FileNotFoundError):
            bundle.browse("nothing")
        with pytest.raises(ValueError, match="outside"):
            bundle.browse("../..")


class TestValidateConcept:
    def test_valid(self):
        result = validate_concept({"type": "Feature", "title": "X"}, "# Card\n")

        assert result.ok
        assert result.total_files == 1

    def test_requires_type(self):
        assert validate_concept({"title": "X"}, "").errors == [
            "frontmatter missing non-empty 'type' field"
        ]

    def test_rejects_non_mapping_frontmatter(self):
        assert not validate_concept(["type"], "").ok  # type: ignore[arg-type]

    def test_rejects_non_string_body(self):
        assert not validate_concept({"type": "X"}, None).ok  # type: ignore[arg-type]

    def test_rejects_unrepresentable_values(self):
        result = validate_concept({"type": "X", "obj": object()}, "")

        assert not result.ok
        assert "cannot be written as YAML" in result.errors[0]

    def test_rejects_values_that_break_the_block(self):
        assert not validate_concept({"type": "X", "note": "a\n---\nb"}, "").ok


class TestWriteConcept:
    def test_keeps_every_key(self, tmp_path: Path):
        fm = {
            "description": "Short.",
            "generated": {"by": "kb-gen/model-x", "at": "2026-11-18T10:00:00Z"},
            "type": "Feature",
            "symbols": ["A.B"],
            "title": "Entry (ใบขน)",
        }

        path = write_concept(tmp_path, "features/import/entry", fm, "# Card\n")

        assert path == tmp_path / "features" / "import" / "entry.md"
        text = path.read_text(encoding="utf-8")
        assert text.startswith("---\ntype: Feature\ntitle: Entry (ใบขน)\n")
        assert _read_frontmatter(path) == fm

    def test_replaces_existing_without_temp_files(self, tmp_path: Path):
        write_concept(tmp_path, "a", {"type": "X", "title": "One"}, "1")
        write_concept(tmp_path, "a", {"type": "X", "title": "Two"}, "2")

        assert _read_frontmatter(tmp_path / "a.md")["title"] == "Two"
        assert [p.name for p in tmp_path.iterdir()] == ["a.md"]

    def test_invalid_concept_writes_nothing(self, tmp_path: Path):
        with pytest.raises(ValueError, match="invalid concept 'a'"):
            write_concept(tmp_path, "a", {"title": "No type"}, "")

        assert list(tmp_path.iterdir()) == []

    @pytest.mark.parametrize("bad_id", ["", "../escape", "index", "dir/log", "agents"])
    def test_rejects_unsafe_or_reserved_ids(self, tmp_path: Path, bad_id: str):
        with pytest.raises(ValueError):
            write_concept(tmp_path, bad_id, {"type": "X"}, "")

    def test_bundle_write_refreshes(self, tmp_path: Path):
        bundle = Bundle.open(tmp_path)

        bundle.write("tables/orders", {"type": "Table", "title": "Orders"}, "Body.")

        assert bundle.ids() == ["tables/orders"]
        assert bundle.search("orders")[0]["title"] == "Orders"


class TestReindexStaleIndexes:
    def test_empties_stale_subdirectory_index(self, tmp_path: Path):
        d = _sample(tmp_path)
        reindex(d)
        (d / "features" / "export" / "declaration-entry.md").unlink()

        result = reindex(d)

        assert "features/export/index.md" in result.warnings[0]
        assert (d / "features" / "export" / "index.md").read_text() == ""

    def test_empties_stale_root_index_but_keeps_okf_version(self, tmp_path: Path):
        d = _sample(tmp_path)
        reindex(d)
        for f in d.rglob("*.md"):
            if f.name != "index.md":
                f.unlink()

        result = reindex(d)

        assert any("index.md" in w for w in result.warnings)
        assert (d / "index.md").read_text() == '---\nokf_version: "0.2"\n---\n\n'

    def test_clean_reindex_reports_no_emptied_files(self, tmp_path: Path):
        d = _sample(tmp_path)

        first = reindex(d)
        second = reindex(d)

        assert first.warnings == []
        assert second.warnings == []
