"""Client helpers for talking to an okf-server."""

from __future__ import annotations

import os
import re
import tarfile
import tempfile
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

DEFAULT_SERVER_URL = "https://okf.com"

SLUG_RE = re.compile(r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?$")


def validate_slug(value: str) -> None:
    """Raise ValueError if value is not a valid OKF slug."""
    if not value or not SLUG_RE.match(value):
        raise ValueError(f"invalid slug: {value!r}")


def server_url(url: str | None) -> str:
    """Resolve explicit URL -> OKF_URL env -> default."""
    if url:
        return url.rstrip("/")
    return os.environ.get("OKF_URL", DEFAULT_SERVER_URL).rstrip("/")


def parse_ref(ref: str, base_url: str) -> tuple[str, str, str]:
    """Return (base_url, username, bundle) for a username/bundle ref or full URL."""
    ref = ref.strip()
    parsed = urlparse(ref)
    if parsed.scheme in {"http", "https"}:
        path = parsed.path.strip("/")
        parts = path.split("/")
        if len(parts) != 2:
            raise ValueError(f"URL must end in /<username>/<bundle>: {ref}")
        return (
            f"{parsed.scheme}://{parsed.netloc}",
            parts[0],
            parts[1],
        )

    parts = ref.split("/")
    if len(parts) != 2:
        raise ValueError(f"ref must be <username>/<bundle> or a full URL: {ref}")
    return base_url, parts[0], parts[1]


def _auth_header(token: str | None) -> dict[str, str]:
    headers: dict[str, str] = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def http_get(url: str, token: str | None = None) -> bytes:
    """GET url and return response body."""
    req = urllib.request.Request(url, headers=_auth_header(token))
    with urllib.request.urlopen(req) as resp:
        return resp.read()


def http_post(
    url: str,
    *,
    fields: dict[str, str] | None = None,
    files: dict[str, tuple[str, bytes]] | None = None,
    token: str | None = None,
) -> bytes:
    """POST multipart/form-data and return response body."""
    boundary = "----okfBoundary"
    body_parts: list[bytes] = []

    for name, value in (fields or {}).items():
        body_parts.append(f"--{boundary}\r\n".encode())
        body_parts.append(
            f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode()
        )
        body_parts.append(value.encode())
        body_parts.append(b"\r\n")

    for name, (filename, data) in (files or {}).items():
        body_parts.append(f"--{boundary}\r\n".encode())
        disposition = (
            f'Content-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'
        )
        body_parts.append(disposition.encode())
        body_parts.append(b"Content-Type: application/gzip\r\n\r\n")
        body_parts.append(data)
        body_parts.append(b"\r\n")

    body_parts.append(f"--{boundary}--\r\n".encode())
    body = b"".join(body_parts)

    headers = _auth_header(token)
    headers["Content-Type"] = f"multipart/form-data; boundary={boundary}"

    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    with urllib.request.urlopen(req) as resp:
        return resp.read()


def tar_directory(src_dir: Path) -> Path:
    """Create a tar.gz of src_dir's contents and return the temp archive path."""
    fd, archive_path = tempfile.mkstemp(suffix=".tar.gz")
    os.close(fd)
    with tarfile.open(archive_path, "w:gz") as tar:
        for child in src_dir.iterdir():
            tar.add(child, arcname=child.name)
    return Path(archive_path)


def extract_archive(archive_path: Path, dest_dir: Path) -> None:
    """Extract a tar.gz archive into dest_dir."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive_path, "r:gz") as tar:
        if hasattr(tarfile, "data_filter"):
            tar.extractall(dest_dir, filter="data")
        else:
            tar.extractall(dest_dir)
