"""CLI tests — only typer-specific behavior (exit codes, error messages)."""

import io
import json
import tarfile
from pathlib import Path

from typer.testing import CliRunner

from okf.cli import app

runner = CliRunner()


def _tar_bytes(files: dict[str, str]) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for rel, content in files.items():
            data = content.encode("utf-8")
            info = tarfile.TarInfo(name=rel)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return buf.getvalue()


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
# show — exit codes & error messages
# ---------------------------------------------------------------------------


def test_show_not_found_shows_path(tmp_path: Path):
    d = tmp_path / "bundle"
    d.mkdir()
    _write(d, {"tables/orders.md": "---\ntype: tables\n---\n\nBody."})

    result = runner.invoke(app, ["show", str(d), "tables/customers"])
    assert result.exit_code == 1
    assert "not found" in result.output


def test_show_reserved_shows_error(tmp_path: Path):
    d = tmp_path / "bundle"
    d.mkdir()
    _write(d, {"index.md": "# Contents"})

    result = runner.invoke(app, ["show", str(d), "index"])
    assert result.exit_code == 1
    assert "reserved filename" in result.output


def test_show_traversal_shows_error(tmp_path: Path):
    d = tmp_path / "bundle"
    d.mkdir()

    result = runner.invoke(app, ["show", str(d), "../../../etc/passwd"])
    assert result.exit_code == 1
    assert "outside the bundle directory" in result.output


def test_show_non_conformant_shows_message(tmp_path: Path):
    d = tmp_path / "raw"
    d.mkdir()
    _write(d, {"notes.md": "# Notes\n\n> Notes.\n\nBody."})

    result = runner.invoke(app, ["show", str(d), "notes"])
    assert result.exit_code == 1
    assert "not an OKF-conformant bundle" in result.output


# ---------------------------------------------------------------------------
# remote commands
# ---------------------------------------------------------------------------


def test_publish_invokes_api(monkeypatch, tmp_path: Path):
    src = tmp_path / "widgets"
    src.mkdir()
    _write(src, {"index.md": "# Contents\n", "ref.md": "---\ntype: ref\n---\n\nBody."})

    calls = []

    def fake_post(url, *, files=None, token=None):
        calls.append((url, token))
        return json.dumps({"username": "alice", "name": "widgets"}).encode()

    monkeypatch.setattr("okf.commands.publish.http_post", fake_post)

    result = runner.invoke(
        app,
        ["publish", str(src), "--token", "tok", "--url", "https://example.com"],
    )

    assert result.exit_code == 0
    assert "Published https://example.com/alice/widgets" in result.output
    assert calls[0][0] == "https://example.com/api/v1/bundles/widgets"
    assert calls[0][1] == "tok"


def test_clone_downloads_archive(monkeypatch, tmp_path: Path):
    archive = _tar_bytes(
        {
            "index.md": "# Contents\n",
            "ref.md": "---\ntype: ref\n---\n\nBody.",
        }
    )
    monkeypatch.setattr("okf.commands.clone.http_get", lambda url, token=None: archive)

    dest = tmp_path / "cloned"
    result = runner.invoke(
        app,
        ["clone", "alice/widgets", str(dest), "--url", "https://example.com"],
    )

    assert result.exit_code == 0
    assert f"Cloned into {dest}" in result.output
    assert (dest / "ref.md").read_text(
        encoding="utf-8"
    ) == "---\ntype: ref\n---\n\nBody."


def test_list_remote(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(
        "okf.commands.list.http_get",
        lambda url, token=None: json.dumps(["tables/orders"]).encode(),
    )

    result = runner.invoke(
        app,
        ["list", "--remote", "alice/widgets", "--url", "https://example.com"],
    )

    assert result.exit_code == 0
    assert "tables/orders" in result.output


def test_show_remote(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(
        "okf.commands.show.http_get",
        lambda url, token=None: b"# Concept\n\nBody.",
    )

    result = runner.invoke(
        app,
        [
            "show",
            "--remote",
            "alice/widgets",
            "--concept-id",
            "ref",
            "--url",
            "https://example.com",
        ],
    )

    assert result.exit_code == 0
    assert "# Concept" in result.output


def test_url_override(monkeypatch, tmp_path: Path):
    captured = []

    def fake_post(url, *, files=None, token=None):
        captured.append(url)
        return json.dumps({"username": "alice", "name": "widgets"}).encode()

    monkeypatch.setattr("okf.commands.publish.http_post", fake_post)

    src = tmp_path / "widgets"
    src.mkdir()
    _write(src, {"index.md": "# Contents\n"})

    result = runner.invoke(
        app,
        [
            "publish",
            str(src),
            "--token",
            "tok",
            "--url",
            "https://custom.example",
        ],
    )

    assert result.exit_code == 0
    assert captured[0].startswith("https://custom.example/api/v1/bundles/widgets")
