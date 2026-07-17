"""FastAPI application for okf-server."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from tempfile import NamedTemporaryFile

from fastapi import (
    Depends,
    FastAPI,
    HTTPException,
    Request,
    Response,
    UploadFile,
    status,
)
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from okf.core import OKF_VERSION
from okf.server.auth import (
    AuthenticationError,
    DuplicateUserError,
    InvalidUsernameError,
    UserStore,
)
from okf.server.storage import FileStore, StorageError, TraversalError

OKF_SERVER_VERSION = "0.1.0"


class RegisterRequest(BaseModel):
    username: str
    password: str


class LoginRequest(BaseModel):
    username: str
    password: str


@dataclass
class AuthInfo:
    username: str


def create_app(
    store: FileStore, user_store: UserStore, allow_register: bool = True
) -> FastAPI:
    app = FastAPI(title="okf-server")

    def require_auth(request: Request) -> AuthInfo:
        auth = request.headers.get("Authorization", "")
        if not auth.lower().startswith("bearer "):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="missing bearer token",
            )
        token = auth[7:].strip()
        username = user_store.username_for_token(token)
        if username is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="invalid token",
            )
        return AuthInfo(username=username)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @app.get("/api/v1/")
    def health() -> dict[str, str]:
        return {
            "okf_server": OKF_SERVER_VERSION,
            "okf_version": OKF_VERSION,
        }

    @app.get("/api/v1/catalog")
    def catalog() -> list[dict[str, str]]:
        result: list[dict[str, str]] = []
        for username_dir in sorted(store.root.iterdir()):
            if not username_dir.is_dir():
                continue
            for bundle_dir in sorted(username_dir.iterdir()):
                if bundle_dir.is_dir() and (bundle_dir / ".owner").is_file():
                    result.append(
                        {"username": username_dir.name, "name": bundle_dir.name}
                    )
        return result

    @app.post("/api/v1/auth/register", status_code=status.HTTP_201_CREATED)
    def register(credentials: RegisterRequest) -> dict[str, str]:
        if not allow_register:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="registration is disabled",
            )
        try:
            token = user_store.register(credentials.username, credentials.password)
        except (InvalidUsernameError, ValueError) as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(exc),
            ) from exc
        except DuplicateUserError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=str(exc),
            ) from exc
        return {"username": credentials.username, "token": token}

    @app.post("/api/v1/auth/login")
    def login(credentials: LoginRequest) -> dict[str, str]:
        try:
            token = user_store.login(credentials.username, credentials.password)
        except AuthenticationError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=str(exc),
            ) from exc
        return {"username": credentials.username, "token": token}

    # ------------------------------------------------------------------
    # Authenticated API
    # ------------------------------------------------------------------

    @app.get("/api/v1/bundles")
    def list_my_bundles(auth: AuthInfo = Depends(require_auth)) -> list[str]:
        return store.list_bundles(auth.username)

    @app.post("/api/v1/bundles/{name}")
    def publish_bundle(
        name: str,
        bundle: UploadFile,
        force: bool = False,
        auth: AuthInfo = Depends(require_auth),
    ) -> JSONResponse:
        try:
            store.bundle_path(auth.username, name)
        except StorageError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(exc),
            ) from exc

        with NamedTemporaryFile(suffix=".tar.gz", delete=False) as tmp:
            tmp_path = Path(tmp.name)
            for chunk in bundle.file:
                tmp.write(chunk)

        try:
            errors, _warnings = store.store_bundle(
                auth.username, name, tmp_path, force=force
            )
        except FileExistsError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=str(exc),
            ) from exc
        except StorageError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(exc),
            ) from exc
        finally:
            tmp_path.unlink(missing_ok=True)

        if errors:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"error": "not conformant", "details": errors},
            )

        try:
            concepts = store.list_concepts(auth.username, name)
        except StorageError:
            concepts = []

        return JSONResponse(
            status_code=status.HTTP_201_CREATED,
            content={
                "username": auth.username,
                "name": name,
                "concepts": len(concepts),
            },
        )

    # ------------------------------------------------------------------
    # Public user-facing routes
    # ------------------------------------------------------------------

    def _bundle_or_404(username: str, name: str) -> Path:
        try:
            path = store.bundle_path(username, name)
        except StorageError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(exc),
            ) from exc
        if not path.is_dir():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="bundle not found",
            )
        return path

    @app.get("/{username}")
    def user_bundles(username: str) -> list[str]:
        try:
            bundles = store.list_bundles(username)
        except StorageError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(exc),
            ) from exc
        if not bundles:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="user has no bundles",
            )
        return bundles

    @app.get("/{username}/{bundle}")
    def bundle_landing(username: str, bundle: str) -> Response:
        path = _bundle_or_404(username, bundle)
        index = path / "index.md"
        if not index.is_file():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="bundle root index.md not found",
            )
        return Response(
            content=index.read_text(encoding="utf-8"),
            media_type="text/markdown; charset=utf-8",
        )

    @app.get("/{username}/{bundle}/concepts")
    def list_concepts(username: str, bundle: str) -> list[str]:
        _bundle_or_404(username, bundle)
        try:
            return store.list_concepts(username, bundle)
        except StorageError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(exc),
            ) from exc

    @app.get("/{username}/{bundle}/concepts/{cid:path}")
    def get_concept(username: str, bundle: str, cid: str) -> Response:
        _bundle_or_404(username, bundle)
        try:
            _frontmatter, raw = store.read_concept(username, bundle, cid)
        except (StorageError, TraversalError) as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(exc),
            ) from exc
        except FileNotFoundError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="concept not found",
            ) from exc
        return Response(
            content=raw,
            media_type="text/markdown; charset=utf-8",
        )

    @app.get("/{username}/{bundle}/archive")
    def download_bundle(username: str, bundle: str) -> Response:
        _bundle_or_404(username, bundle)
        try:
            archive_path = store.archive_bundle(username, bundle)
        except StorageError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(exc),
            ) from exc
        try:
            data = archive_path.read_bytes()
        finally:
            archive_path.unlink(missing_ok=True)
        return Response(
            content=data,
            media_type="application/gzip",
        )

    return app
