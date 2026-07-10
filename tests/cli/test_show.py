"""CLI integration tests for okf show."""

from pathlib import Path

from typer.testing import CliRunner

from okf.cli import app

runner = CliRunner()


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
