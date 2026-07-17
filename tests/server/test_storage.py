"""Tests for okf.server.storage."""

from __future__ import annotations

import tarfile
from pathlib import Path

import pytest

from okf.server.storage import FileStore, StorageError, TraversalError


def _make_bundle_tar(src: Path) -> Path:
    """Tar the contents of src into a temp archive."""
    archive = src.with_suffix(".tar.gz")
    with tarfile.open(archive, "w:gz") as tar:
        for child in src.iterdir():
            tar.add(child, arcname=child.name)
    return archive


@pytest.fixture
def file_store(tmp_path):
    return FileStore(tmp_path / "store")


def _conformant_bundle(path: Path) -> None:
    (path / "tables").mkdir(parents=True)
    (path / "tables" / "orders.md").write_text(
        "---\ntype: table\n---\n\n# Orders", encoding="utf-8"
    )
    (path / "index.md").write_text("# Contents", encoding="utf-8")


def test_store_conformant_bundle(file_store, tmp_path):
    src = tmp_path / "bundle"
    src.mkdir()
    _conformant_bundle(src)
    archive = _make_bundle_tar(src)

    errors, warnings = file_store.store_bundle("alice", "widgets", archive)

    assert errors == []
    assert file_store.bundle_exists("alice", "widgets")
    assert (
        file_store.bundle_path("alice", "widgets") / "tables" / "orders.md"
    ).is_file()
    assert "tables/orders" in file_store.list_concepts("alice", "widgets")


def test_store_nonconformant_bundle(file_store, tmp_path):
    src = tmp_path / "bundle"
    src.mkdir()
    (src / "bad.md").write_text("No frontmatter.", encoding="utf-8")
    archive = _make_bundle_tar(src)

    errors, warnings = file_store.store_bundle("alice", "widgets", archive)

    assert errors
    assert not file_store.bundle_exists("alice", "widgets")


def test_store_replace_with_force(file_store, tmp_path):
    src = tmp_path / "bundle"
    src.mkdir()
    _conformant_bundle(src)
    archive = _make_bundle_tar(src)
    file_store.store_bundle("alice", "widgets", archive)

    src2 = tmp_path / "bundle2"
    src2.mkdir()
    (src2 / "index.md").write_text("# Updated", encoding="utf-8")
    (src2 / "other.md").write_text("---\ntype: ref\n---\n", encoding="utf-8")
    archive2 = _make_bundle_tar(src2)

    errors, warnings = file_store.store_bundle("alice", "widgets", archive2, force=True)
    assert errors == []
    assert (file_store.bundle_path("alice", "widgets") / "other.md").is_file()


def test_store_replace_without_force(file_store, tmp_path):
    src = tmp_path / "bundle"
    src.mkdir()
    _conformant_bundle(src)
    archive = _make_bundle_tar(src)
    file_store.store_bundle("alice", "widgets", archive)

    with pytest.raises(FileExistsError):
        file_store.store_bundle("alice", "widgets", archive)


def test_username_namespace_isolation(file_store, tmp_path):
    src = tmp_path / "bundle"
    src.mkdir()
    _conformant_bundle(src)
    archive = _make_bundle_tar(src)

    file_store.store_bundle("alice", "widgets", archive)
    file_store.store_bundle("bob", "widgets", archive)

    assert file_store.list_bundles("alice") == ["widgets"]
    assert file_store.list_bundles("bob") == ["widgets"]


def test_read_concept_traversal(file_store, tmp_path):
    src = tmp_path / "bundle"
    src.mkdir()
    _conformant_bundle(src)
    archive = _make_bundle_tar(src)
    file_store.store_bundle("alice", "widgets", archive)

    with pytest.raises((StorageError, TraversalError)):
        file_store.read_concept("alice", "widgets", "../../etc/passwd")


def test_archive_roundtrip(file_store, tmp_path):
    src = tmp_path / "bundle"
    src.mkdir()
    _conformant_bundle(src)
    archive = _make_bundle_tar(src)
    file_store.store_bundle("alice", "widgets", archive)

    archive_path = file_store.archive_bundle("alice", "widgets")
    dest = tmp_path / "roundtrip"
    dest.mkdir()
    with tarfile.open(archive_path, "r:gz") as tar:
        if hasattr(tarfile, "data_filter"):
            tar.extractall(dest, filter="data")
        else:
            tar.extractall(dest)

    # The archive stores the bundle under the "widgets" directory name.
    extracted = dest / "widgets"
    assert (extracted / "tables" / "orders.md").is_file()


def test_owner_file_written(file_store, tmp_path):
    src = tmp_path / "bundle"
    src.mkdir()
    _conformant_bundle(src)
    archive = _make_bundle_tar(src)
    file_store.store_bundle("alice", "widgets", archive)

    owner = (file_store.bundle_path("alice", "widgets") / ".owner").read_text(
        encoding="utf-8"
    )
    assert owner == "alice"


def test_list_bundles(file_store, tmp_path):
    src = tmp_path / "bundle"
    src.mkdir()
    _conformant_bundle(src)
    archive = _make_bundle_tar(src)

    file_store.store_bundle("alice", "widgets", archive)
    file_store.store_bundle("alice", "api-docs", archive)

    assert file_store.list_bundles("alice") == ["api-docs", "widgets"]
    assert file_store.list_bundles("bob") == []
