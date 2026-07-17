"""Integration tests for okf.server.app via FastAPI TestClient."""

from __future__ import annotations

import io
import tarfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from okf.core import OKF_VERSION
from okf.server.app import OKF_SERVER_VERSION, create_app
from okf.server.auth import UserStore
from okf.server.storage import FileStore


def _make_tar_bytes(src: Path) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for child in src.iterdir():
            tar.add(child, arcname=child.name)
    return buf.getvalue()


@pytest.fixture
def app(tmp_path):
    store = FileStore(tmp_path / "store")
    users = UserStore(tmp_path / "users.db")
    return create_app(store, users, allow_register=True)


@pytest.fixture
def client(app):
    return TestClient(app)


def _register(client, username, password):
    resp = client.post(
        "/api/v1/auth/register", json={"username": username, "password": password}
    )
    assert resp.status_code == 201
    return resp.json()["token"]


def test_health(client):
    resp = client.get("/api/v1/")
    assert resp.status_code == 200
    assert resp.json() == {
        "okf_server": OKF_SERVER_VERSION,
        "okf_version": OKF_VERSION,
    }


def test_register(client):
    resp = client.post(
        "/api/v1/auth/register", json={"username": "alice", "password": "secret"}
    )
    assert resp.status_code == 201
    assert resp.json()["username"] == "alice"
    assert "token" in resp.json()


def test_login(client):
    _register(client, "alice", "secret")
    resp = client.post(
        "/api/v1/auth/login", json={"username": "alice", "password": "secret"}
    )
    assert resp.status_code == 200
    assert "token" in resp.json()


def test_publish_valid_201(client, tmp_path):
    token = _register(client, "alice", "secret")
    src = tmp_path / "bundle"
    src.mkdir()
    (src / "index.md").write_text("# Contents", encoding="utf-8")
    (src / "tables").mkdir()
    (src / "tables" / "orders.md").write_text(
        "---\ntype: table\n---\n\n# Orders", encoding="utf-8"
    )

    resp = client.post(
        "/api/v1/bundles/widgets",
        files={
            "bundle": (
                "widgets.tar.gz",
                io.BytesIO(_make_tar_bytes(src)),
                "application/gzip",
            )
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["username"] == "alice"
    assert data["name"] == "widgets"
    assert data["concepts"] == 1


def test_publish_no_auth_401(client, tmp_path):
    src = tmp_path / "bundle"
    src.mkdir()
    (src / "index.md").write_text("# Contents", encoding="utf-8")
    resp = client.post(
        "/api/v1/bundles/widgets",
        files={
            "bundle": (
                "widgets.tar.gz",
                io.BytesIO(_make_tar_bytes(src)),
                "application/gzip",
            )
        },
    )
    assert resp.status_code == 401


def test_publish_nonconformant_400(client, tmp_path):
    token = _register(client, "alice", "secret")
    src = tmp_path / "bundle"
    src.mkdir()
    (src / "bad.md").write_text("No frontmatter.", encoding="utf-8")

    resp = client.post(
        "/api/v1/bundles/widgets",
        files={
            "bundle": (
                "widgets.tar.gz",
                io.BytesIO(_make_tar_bytes(src)),
                "application/gzip",
            )
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 400
    assert "not conformant" in resp.json()["detail"]["error"]


def test_publish_force(client, tmp_path):
    token = _register(client, "alice", "secret")
    src = tmp_path / "bundle"
    src.mkdir()
    (src / "index.md").write_text("# Contents", encoding="utf-8")
    (src / "a.md").write_text("---\ntype: ref\n---\n", encoding="utf-8")

    client.post(
        "/api/v1/bundles/widgets",
        files={
            "bundle": (
                "widgets.tar.gz",
                io.BytesIO(_make_tar_bytes(src)),
                "application/gzip",
            )
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    src2 = tmp_path / "bundle2"
    src2.mkdir()
    (src2 / "index.md").write_text("# Updated", encoding="utf-8")
    (src2 / "b.md").write_text("---\ntype: ref\n---\n", encoding="utf-8")

    resp = client.post(
        "/api/v1/bundles/widgets?force=true",
        files={
            "bundle": (
                "widgets.tar.gz",
                io.BytesIO(_make_tar_bytes(src2)),
                "application/gzip",
            )
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201


def test_publish_same_name_different_users(client, tmp_path):
    alice_token = _register(client, "alice", "secret")
    bob_token = _register(client, "bob", "secret")
    src = tmp_path / "bundle"
    src.mkdir()
    (src / "index.md").write_text("# Contents", encoding="utf-8")
    (src / "c.md").write_text("---\ntype: ref\n---\n", encoding="utf-8")

    resp1 = client.post(
        "/api/v1/bundles/widgets",
        files={
            "bundle": (
                "widgets.tar.gz",
                io.BytesIO(_make_tar_bytes(src)),
                "application/gzip",
            )
        },
        headers={"Authorization": f"Bearer {alice_token}"},
    )
    resp2 = client.post(
        "/api/v1/bundles/widgets",
        files={
            "bundle": (
                "widgets.tar.gz",
                io.BytesIO(_make_tar_bytes(src)),
                "application/gzip",
            )
        },
        headers={"Authorization": f"Bearer {bob_token}"},
    )
    assert resp1.status_code == 201
    assert resp2.status_code == 201


def test_list_my_bundles(client, tmp_path):
    token = _register(client, "alice", "secret")
    src = tmp_path / "bundle"
    src.mkdir()
    (src / "index.md").write_text("# Contents", encoding="utf-8")
    (src / "x.md").write_text("---\ntype: ref\n---\n", encoding="utf-8")

    client.post(
        "/api/v1/bundles/widgets",
        files={
            "bundle": (
                "widgets.tar.gz",
                io.BytesIO(_make_tar_bytes(src)),
                "application/gzip",
            )
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    resp = client.get("/api/v1/bundles", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json() == ["widgets"]


def test_catalog_lists_public_bundles(client, tmp_path):
    alice_token = _register(client, "alice", "secret")
    bob_token = _register(client, "bob", "secret")
    src = tmp_path / "bundle"
    src.mkdir()
    (src / "index.md").write_text("# Contents", encoding="utf-8")
    (src / "x.md").write_text("---\ntype: ref\n---\n", encoding="utf-8")

    client.post(
        "/api/v1/bundles/widgets",
        files={
            "bundle": (
                "widgets.tar.gz",
                io.BytesIO(_make_tar_bytes(src)),
                "application/gzip",
            )
        },
        headers={"Authorization": f"Bearer {alice_token}"},
    )
    client.post(
        "/api/v1/bundles/docs",
        files={
            "bundle": (
                "docs.tar.gz",
                io.BytesIO(_make_tar_bytes(src)),
                "application/gzip",
            )
        },
        headers={"Authorization": f"Bearer {bob_token}"},
    )

    resp = client.get("/api/v1/catalog")
    assert resp.status_code == 200
    items = resp.json()
    assert {"username": "alice", "name": "widgets"} in items
    assert {"username": "bob", "name": "docs"} in items


def test_user_bundles(client, tmp_path):
    token = _register(client, "alice", "secret")
    src = tmp_path / "bundle"
    src.mkdir()
    (src / "index.md").write_text("# Contents", encoding="utf-8")
    (src / "x.md").write_text("---\ntype: ref\n---\n", encoding="utf-8")

    client.post(
        "/api/v1/bundles/widgets",
        files={
            "bundle": (
                "widgets.tar.gz",
                io.BytesIO(_make_tar_bytes(src)),
                "application/gzip",
            )
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    resp = client.get("/alice")
    assert resp.status_code == 200
    assert resp.json() == ["widgets"]


def test_bundle_landing(client, tmp_path):
    token = _register(client, "alice", "secret")
    src = tmp_path / "bundle"
    src.mkdir()
    (src / "index.md").write_text("# Welcome", encoding="utf-8")

    client.post(
        "/api/v1/bundles/widgets",
        files={
            "bundle": (
                "widgets.tar.gz",
                io.BytesIO(_make_tar_bytes(src)),
                "application/gzip",
            )
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    resp = client.get("/alice/widgets")
    assert resp.status_code == 200
    assert resp.text == "# Welcome"
    assert resp.headers["content-type"] == "text/markdown; charset=utf-8"


def test_list_concepts(client, tmp_path):
    token = _register(client, "alice", "secret")
    src = tmp_path / "bundle"
    src.mkdir()
    (src / "index.md").write_text("# Contents", encoding="utf-8")
    (src / "tables").mkdir()
    (src / "tables" / "orders.md").write_text(
        "---\ntype: table\n---\n", encoding="utf-8"
    )

    client.post(
        "/api/v1/bundles/widgets",
        files={
            "bundle": (
                "widgets.tar.gz",
                io.BytesIO(_make_tar_bytes(src)),
                "application/gzip",
            )
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    resp = client.get("/alice/widgets/concepts")
    assert resp.status_code == 200
    assert resp.json() == ["tables/orders"]


def test_get_concept(client, tmp_path):
    token = _register(client, "alice", "secret")
    src = tmp_path / "bundle"
    src.mkdir()
    (src / "index.md").write_text("# Contents", encoding="utf-8")
    (src / "tables").mkdir()
    (src / "tables" / "orders.md").write_text(
        "---\ntype: table\n---\n\n# Orders", encoding="utf-8"
    )

    client.post(
        "/api/v1/bundles/widgets",
        files={
            "bundle": (
                "widgets.tar.gz",
                io.BytesIO(_make_tar_bytes(src)),
                "application/gzip",
            )
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    resp = client.get("/alice/widgets/concepts/tables/orders")
    assert resp.status_code == 200
    assert "# Orders" in resp.text


def test_download_archive(client, tmp_path):
    token = _register(client, "alice", "secret")
    src = tmp_path / "bundle"
    src.mkdir()
    (src / "index.md").write_text("# Contents", encoding="utf-8")

    client.post(
        "/api/v1/bundles/widgets",
        files={
            "bundle": (
                "widgets.tar.gz",
                io.BytesIO(_make_tar_bytes(src)),
                "application/gzip",
            )
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    resp = client.get("/alice/widgets/archive")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/gzip"
    assert resp.content[:2] == b"\x1f\x8b"  # gzip magic


def test_invalid_slug_404(client):
    resp = client.get("/bad_name/widgets")
    assert resp.status_code == 404
