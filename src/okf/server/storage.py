"""Filesystem storage for published OKF bundles."""

from __future__ import annotations

import os
import shutil
import tarfile
import tempfile
from pathlib import Path
from typing import Any

from okf.core import check_conformance, parse_frontmatter
from okf.server._common import validate_slug


class StorageError(Exception):
    """Base storage exception."""


class TraversalError(StorageError):
    """Raised when a path escapes its intended root."""


class FileStore:
    """Store and read OKF bundles on disk under <root>/<username>/<bundle>/."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).expanduser()
        self.root.mkdir(parents=True, exist_ok=True)

    def _validate(self, *parts: str) -> None:
        for part in parts:
            try:
                validate_slug(part)
            except ValueError as exc:
                raise StorageError(str(exc)) from exc

    def user_path(self, username: str) -> Path:
        self._validate(username)
        return self.root / username

    def bundle_path(self, username: str, name: str) -> Path:
        self._validate(username, name)
        return self.user_path(username) / name

    def bundle_exists(self, username: str, name: str) -> bool:
        return self.bundle_path(username, name).is_dir()

    def list_bundles(self, username: str) -> list[str]:
        user_dir = self.user_path(username)
        if not user_dir.is_dir():
            return []
        return sorted(
            p.name
            for p in user_dir.iterdir()
            if p.is_dir() and (p / ".owner").is_file()
        )

    def _concept_file(self, username: str, name: str, cid: str) -> Path:
        self._validate(username, name)
        bundle = self.bundle_path(username, name)
        if not bundle.is_dir():
            raise StorageError(f"bundle does not exist: {username}/{name}")

        # Concept IDs come from our own listing, but guard anyway.
        target = (bundle / f"{cid}.md").resolve()
        try:
            target.relative_to(bundle.resolve())
        except ValueError as exc:
            raise TraversalError(f"concept id outside bundle: {cid}") from exc

        if target.name.lower() in {"index.md", "log.md", "agents.md"}:
            raise StorageError(f"reserved filename: {target.name}")

        return target

    def list_concepts(self, username: str, name: str) -> list[str]:
        bundle = self.bundle_path(username, name)
        if not bundle.is_dir():
            raise StorageError(f"bundle does not exist: {username}/{name}")

        cids: list[str] = []
        for f in sorted(bundle.rglob("*.md")):
            if f.name.lower() in {"index.md", "log.md", "agents.md"}:
                continue
            rel = f.relative_to(bundle)
            cid = str(rel.parent / rel.stem) if rel.parent != Path(".") else rel.stem
            cids.append(cid)
        return cids

    def read_concept(
        self, username: str, name: str, cid: str
    ) -> tuple[dict[str, Any] | None, str]:
        target = self._concept_file(username, name, cid)
        if not target.is_file():
            raise FileNotFoundError(f"concept not found: {cid}")
        raw = target.read_text(encoding="utf-8")
        return parse_frontmatter(raw), raw

    @staticmethod
    def _safe_extract(tar: tarfile.TarFile, dest: Path) -> None:
        """Extract tar members, refusing paths that escape dest."""
        dest_resolved = dest.resolve()
        for member in tar.getmembers():
            member_path = dest_resolved / member.name
            try:
                member_path.relative_to(dest_resolved)
            except ValueError as exc:
                raise StorageError(
                    f"tar member escapes destination: {member.name}"
                ) from exc
            if hasattr(tarfile, "data_filter"):
                tar.extract(member, dest_resolved, filter="data")
            else:
                tar.extract(member, dest_resolved)

    def store_bundle(
        self, username: str, name: str, tar_path: Path, force: bool = False
    ) -> tuple[list[str], list[str]]:
        self._validate(username, name)
        bundle = self.bundle_path(username, name)

        with tempfile.TemporaryDirectory(dir=self.root) as tmp:
            tmp_path = Path(tmp) / "bundle"
            tmp_path.mkdir()

            with tarfile.open(tar_path, "r:gz") as tar:
                self._safe_extract(tar, tmp_path)

            # If the tar contained a single top-level directory, unwrap it.
            children = [p for p in tmp_path.iterdir() if p.name != ".owner"]
            if len(children) == 1 and children[0].is_dir():
                unwrapped = tmp_path / children[0].name
                for child in unwrapped.iterdir():
                    shutil.move(str(child), str(tmp_path / child.name))
                unwrapped.rmdir()

            errors, warnings = check_conformance(tmp_path)
            if errors:
                return errors, warnings

            if bundle.exists():
                if not force:
                    raise FileExistsError(f"bundle already exists: {username}/{name}")
                shutil.rmtree(bundle)

            shutil.move(str(tmp_path), str(bundle))
            (bundle / ".owner").write_text(username, encoding="utf-8")

        return [], warnings

    def archive_bundle(self, username: str, name: str) -> Path:
        bundle = self.bundle_path(username, name)
        if not bundle.is_dir():
            raise StorageError(f"bundle does not exist: {username}/{name}")

        fd, archive_path = tempfile.mkstemp(suffix=".tar.gz", dir=self.root)
        os.close(fd)

        with tarfile.open(archive_path, "w:gz") as tar:
            tar.add(bundle, arcname=name)

        return Path(archive_path)

    def delete_bundle(self, username: str, name: str) -> None:
        bundle = self.bundle_path(username, name)
        if bundle.exists():
            shutil.rmtree(bundle)
