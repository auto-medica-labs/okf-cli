"""Tests for okf.server.auth."""

from __future__ import annotations

import pytest

from okf.server.auth import (
    AuthenticationError,
    DuplicateUserError,
    InvalidUsernameError,
    UserStore,
)


@pytest.fixture
def store(tmp_path):
    db = tmp_path / "users.db"
    with UserStore(db) as s:
        yield s


def test_register_and_login(store):
    token = store.register("alice", "secret")
    assert token
    same = store.login("alice", "secret")
    assert same == token


def test_register_duplicate_username(store):
    store.register("alice", "secret")
    with pytest.raises(DuplicateUserError):
        store.register("alice", "other")


def test_login_wrong_password(store):
    store.register("alice", "secret")
    with pytest.raises(AuthenticationError):
        store.login("alice", "wrong")


def test_reserved_username_rejected(store):
    for name in ["api", "static", "health", "www", "default"]:
        with pytest.raises(InvalidUsernameError):
            store.register(name, "secret")


def test_invalid_username_slug(store):
    for name in ["", "-leading", "trailing-", "UpperCase", "under_score"]:
        with pytest.raises(InvalidUsernameError):
            store.register(name, "secret")


def test_username_for_token(store):
    token = store.register("alice", "secret")
    assert store.username_for_token(token) == "alice"
    assert store.username_for_token("nope") is None
