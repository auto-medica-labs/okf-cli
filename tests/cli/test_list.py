"""CLI integration tests for okf list."""

from pathlib import Path

from typer.testing import CliRunner

from okf.cli import app

runner = CliRunner()


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
