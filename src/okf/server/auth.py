"""SQLite-backed user store for okf-server."""

from __future__ import annotations

import hashlib
import secrets
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from okf.server._common import RESERVED_USERNAMES, validate_slug


class DuplicateUserError(Exception):
    """Raised when registering an already-taken username."""


class AuthenticationError(Exception):
    """Raised when credentials are invalid."""


class InvalidUsernameError(Exception):
    """Raised when a username violates slug or reserved-name rules."""


class UserStore:
    """Manage users, password hashes, and bearer tokens in SQLite."""

    _SCHEMA = """
    CREATE TABLE IF NOT EXISTS users (
        username TEXT PRIMARY KEY,
        password_hash BLOB,
        salt BLOB,
        token TEXT UNIQUE,
        created_at TEXT
    );
    """

    def __init__(self, db_path: str | Path) -> None:
        self._db = Path(db_path)
        self._db.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._db), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(self._SCHEMA)
        self._conn.commit()

    def _hash(self, password: str, salt: bytes) -> bytes:
        return hashlib.scrypt(
            password.encode("utf-8"),
            salt=salt,
            n=2**14,
            r=8,
            p=1,
        )

    def _row(self, username: str) -> sqlite3.Row | None:
        cur = self._conn.execute("SELECT * FROM users WHERE username = ?", (username,))
        return cur.fetchone()

    def username_exists(self, username: str) -> bool:
        return self._row(username) is not None

    def _validate_username(self, username: str) -> None:
        try:
            validate_slug(username)
        except ValueError as exc:
            raise InvalidUsernameError(str(exc)) from exc
        if username in RESERVED_USERNAMES:
            raise InvalidUsernameError(f"username {username!r} is reserved")

    def register(self, username: str, password: str) -> str:
        """Create a user and return their bearer token."""
        self._validate_username(username)
        if not password:
            raise ValueError("password cannot be empty")

        if self.username_exists(username):
            raise DuplicateUserError(f"username {username!r} is taken")

        salt = secrets.token_bytes(32)
        password_hash = self._hash(password, salt)
        token = secrets.token_urlsafe(32)
        created_at = datetime.now(UTC).isoformat()

        try:
            self._conn.execute(
                "INSERT INTO users (username, password_hash, salt, token, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (username, password_hash, salt, token, created_at),
            )
            self._conn.commit()
        except sqlite3.IntegrityError as exc:
            if "token" in str(exc).lower():
                # Token collision is extremely unlikely; retry once.
                return self.register(username, password)
            raise DuplicateUserError(f"username {username!r} is taken") from exc

        return token

    def login(self, username: str, password: str) -> str:
        """Validate credentials and return the user's bearer token."""
        row = self._row(username)
        if row is None:
            raise AuthenticationError("invalid credentials")

        expected_hash = self._hash(password, row["salt"])
        if not secrets.compare_digest(expected_hash, row["password_hash"]):
            raise AuthenticationError("invalid credentials")

        return row["token"]

    def username_for_token(self, token: str) -> str | None:
        cur = self._conn.execute("SELECT username FROM users WHERE token = ?", (token,))
        row = cur.fetchone()
        return row["username"] if row else None

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> UserStore:
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()
