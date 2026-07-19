"""CLI tests — only typer-specific behavior (exit codes, error messages)."""

from pathlib import Path

from typer.testing import CliRunner

from okf.cli import app

runner = CliRunner()


def _write(dir_path: Path, files: dict[str, str]) -> None:
    for rel, content in files.items():
        p = dir_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")


# ---------------------------------------------------------------------------
# bundle — exit codes & error messages
# ---------------------------------------------------------------------------


def test_bundle_no_force_shows_flag(tmp_path: Path):
    src = tmp_path / "src"
    dst = tmp_path / "out"
    src.mkdir()
    dst.mkdir()
    _write(src, {"tables/a.md": "# A\n\n> Desc.\n"})

    result = runner.invoke(app, ["bundle", str(src), str(dst)])
    assert result.exit_code == 1
    assert "--force" in result.output


def test_bundle_same_dir_shows_different(tmp_path: Path):
    src = tmp_path / "src"
    src.mkdir()
    _write(src, {"tables/a.md": "# A\n\n> Desc.\n"})

    result = runner.invoke(app, ["bundle", str(src), str(src), "--force"])
    assert result.exit_code == 1
    assert "must be different" in result.output


def test_bundle_missing_input_shows_not_found(tmp_path: Path):
    result = runner.invoke(app, ["bundle", str(tmp_path / "nope")])
    assert result.exit_code == 1
    assert "not found" in result.output


def test_bundle_empty_dir_shows_error(tmp_path: Path):
    src = tmp_path / "src"
    src.mkdir()

    result = runner.invoke(app, ["bundle", str(src), str(tmp_path / "out")])
    assert result.exit_code == 1
    assert "No markdown files" in result.output


def test_bundle_force_shows_removed(tmp_path: Path):
    src = tmp_path / "src"
    dst = tmp_path / "out"
    src.mkdir()
    dst.mkdir()
    _write(src, {"tables/a.md": "# A\n\n> Desc.\n"})

    result = runner.invoke(app, ["bundle", str(src), str(dst), "--force"])
    assert result.exit_code == 0
    assert "Removed existing" in result.output


def test_bundle_strict_shows_error(tmp_path: Path):
    src = tmp_path / "src"
    dst = tmp_path / "out"
    src.mkdir()
    _write(
        src,
        {
            "tables/orders.md": ("# Orders\n\n> One row.\n\nSee [C](customers.md)."),
        },
    )

    result = runner.invoke(app, ["bundle", str(src), str(dst), "--strict"])
    assert result.exit_code == 1
    assert "strict link check failed" in result.output
    assert not (dst / "AGENTS.md").exists()


# ---------------------------------------------------------------------------
# validate — exit codes & error messages
# ---------------------------------------------------------------------------


def test_validate_no_md_shows_error(tmp_path: Path):
    d = tmp_path / "empty"
    d.mkdir()

    result = runner.invoke(app, ["validate", str(d)])
    assert result.exit_code == 1
    assert "No .md files" in result.output


def test_validate_not_a_dir_shows_error(tmp_path: Path):
    f = tmp_path / "file"
    f.write_text("hello")

    result = runner.invoke(app, ["validate", str(f)])
    assert result.exit_code == 1
    assert "not a directory" in result.output


def test_validate_shows_error_count(tmp_path: Path):
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


# ---------------------------------------------------------------------------
# list — exit codes & error messages
# ---------------------------------------------------------------------------


def test_list_non_conformant_shows_message(tmp_path: Path):
    d = tmp_path / "raw"
    d.mkdir()
    _write(d, {"notes.md": "# Notes\n\n> Notes.\n\nBody."})

    result = runner.invoke(app, ["list", str(d)])
    assert result.exit_code == 1
    assert "not an OKF-conformant bundle" in result.output


def test_list_empty_shows_message(tmp_path: Path):
    d = tmp_path / "bundle"
    d.mkdir()

    result = runner.invoke(app, ["list", str(d)])
    assert result.exit_code == 1
    assert "No concepts found" in result.output


# ---------------------------------------------------------------------------
# read — exit codes & error messages
# ---------------------------------------------------------------------------


def test_read_not_found_shows_path(tmp_path: Path):
    d = tmp_path / "bundle"
    d.mkdir()
    _write(d, {"tables/orders.md": "---\ntype: tables\n---\n\nBody."})

    result = runner.invoke(app, ["read", str(d), "tables/customers"])
    assert result.exit_code == 1
    assert "not found" in result.output


def test_read_reserved_shows_error(tmp_path: Path):
    d = tmp_path / "bundle"
    d.mkdir()
    _write(d, {"index.md": "# Contents"})

    result = runner.invoke(app, ["read", str(d), "index"])
    assert result.exit_code == 1
    assert "reserved filename" in result.output


def test_read_traversal_shows_error(tmp_path: Path):
    d = tmp_path / "bundle"
    d.mkdir()

    result = runner.invoke(app, ["read", str(d), "../../../etc/passwd"])
    assert result.exit_code == 1
    assert "outside the bundle directory" in result.output


def test_read_non_conformant_shows_message(tmp_path: Path):
    d = tmp_path / "raw"
    d.mkdir()
    _write(d, {"notes.md": "# Notes\n\n> Notes.\n\nBody."})

    result = runner.invoke(app, ["read", str(d), "notes"])
    assert result.exit_code == 1
    assert "not an OKF-conformant bundle" in result.output
