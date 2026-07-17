# Plan: OKF hosted server + remote commands (v3 — namespaced)

## Motivation

Currently `okf` operates only on local filesystem bundles. User wants:

- `okf publish` — upload local OKF bundle to hosted service
- `okf list --remote` / `okf show --remote` — browse remote bundle without download
- `okf clone` — download remote bundle to local

HTTP REST API chosen — supports `list`/`show` without full download, zero new deps on the client side (stdlib `urllib` + `tarfile`).

Server is part of this repo — `okf-server` binary shipped alongside `okf` CLI, reusing `okf.core` and `okf.api` so conformance logic stays in one place.

---

## Architecture

Two binaries, one package:

```
pyproject.toml
├── [project.scripts]
│   ├── okf         = "okf.cli:app"           ← existing, unchanged
│   └── okf-server  = "okf.server.cli:app"    ← NEW
├── [project.optional-dependencies]
│   └── server = ["fastapi>=0.115", "python-multipart>=0.0.20", "uvicorn[standard]>=0.30"]
```

```
src/okf/
├── core.py                    ← +OKF_VERSION constant only
├── api.py                     ← unchanged
├── cli.py                     ← unchanged
├── commands/                  ← unchanged
│   ├── bundle.py, list.py, show.py, validate.py
└── server/                    ← NEW
    ├── __init__.py
    ├── storage.py             ← FileStore class (seam for future backends)
    ├── app.py                 ← FastAPI app + routes + auth dependency
    └── cli.py                 ← typer app for okf-server serve
```

---

## Storage design

**Format on disk:** extracted directory tree at `<store_root>/<token_hash>/<bundle-name>/`.

Why directory, not stored-as-tar:
- `list`/`show` are hot path — direct filesystem reads, no unpacking
- Server reuses `okf.api.list_concepts` / `okf.api.show_concept` directly — they operate on `Path` directories
- `archive` is cold path — tar.gz created on-the-fly when `GET /archive` is hit

### MVP: `FileStore` (local disk)

`FileStore` works fine for MVP: single server, few users, tiny bundles (KB each). 10k bundles × 50KB = 500MB — disk lasts long time.

### Seam for future backends

`FileStore` class wraps all disk access. Route handlers call `store.list_concepts(owner_hash, name)`, not raw `os.listdir`. When the service grows, write a new class with same method signatures, swap one line in `cli.py`. No interface/ABC — just a concrete class. YAGNI on the abstraction until it's needed.

| Phase | Backend | When |
|-------|---------|------|
| MVP | `FileStore` (local disk) | Now. Single server, few users. |
| Growth | `S3Store` (S3/R2) | Disk fills up, need HA. Concepts stored as individual objects. Archive = precomputed or on-the-fly tar. |
| Big | `DBStore` (Postgres + blob store) | Need search, metadata queries, per-user stats. |

### Namespace & Ownership model

Bundle names are unique **per token namespace** — `user1/my-bundle` and `user2/my-bundle` are independent. The "user" identifier is the token hash: `sha256(token)[:16]`.

```
store/
├── abc123def0123456/              ← token hash (16 chars)
│   ├── my-bundle/
│   │   ├── .owner          ← "abc123def0123456" (metadata, survives backend swap)
│   │   ├── tables/
│   │   │   └── orders.md
│   │   └── ...
│   └── other-bundle/
│       ├── .owner          ← "abc123def0123456"
│       └── ...
└── fed987cba0987654/              ← different token
    └── my-bundle/                 ← same name, different namespace, no conflict
        ├── .owner          ← "fed987cba0987654"
        └── ...
```

- **Token hash** = `sha256(token.encode()).hexdigest()[:16]`
- **No token (auth disabled)** → namespace = `public/` (shared, anyone can read/write)
- **Auth required (POST)** → namespace derived from token in `Authorization` header
- **Auth optional (GET)** → if `public_read=true` and no token, use `public/` namespace; if token provided, use that token's namespace
- **Force-replace** → only replaces bundles in **your** namespace (no cross-namespace access possible)
- **`.owner` file** = metadata written on publish (same value as namespace). Redundant for `FileStore` but useful for backend swaps where path conventions differ.

No 409 conflicts between users. No 403 ownership errors. Each user isolated in their namespace.

**Flow:**

```
POST upload (tar.gz)
  → derive namespace from token → store/<namespace>/
  → unpack tar to temp dir
  → okf.core.check_conformance(temp_dir)
  → if clean: move temp_dir → store/<namespace>/<name>/
  → if not: return errors, temp dir cleaned up
  → original tar.gz discarded
  → write .owner with namespace hash

GET /archive
  → tar + gzip store/<namespace>/<name>/ → serve as application/gzip

GET /concepts
  → store.list_concepts(namespace, name) → json array

GET /concepts/:id
  → store.read_concept(namespace, name, id) → raw markdown
```

---

## API contract

```
GET    /api/v1/                              → healthcheck
  200  { "okf_server": "0.1.0", "okf_version": "0.1" }

GET    /api/v1/bundles                       → list bundles in your namespace
  Auth:   Bearer <token> (required when token set)
  200  ["my-bundle", "other-bundle"]

POST   /api/v1/bundles/:name
  Auth:   Bearer <token>
  Body:   multipart form, field "bundle" = tar.gz file
  201  { "name": "...", "concepts": 42 }
  400  { "error": "not conformant", "details": ["path: missing type", ...] }
  409  { "error": "bundle already exists, use ?force=true" }  (in your namespace)

GET    /api/v1/bundles/:name/concepts
  Auth:   Bearer <token> (optional, controlled by --public-read)
  200  ["tables/orders", "tables/customers", "playbooks/oncall"]
  404  { "error": "bundle not found" }

GET    /api/v1/bundles/:name/concepts/{id:path}
  Auth:   Bearer <token> (optional)
  200  raw markdown (Content-Type: text/markdown; charset=utf-8)
  404  { "error": "concept not found" }

GET    /api/v1/bundles/:name/archive
  Auth:   Bearer <token> (optional)
  200  application/gzip tar archive
  404  { "error": "bundle not found" }
```

- `:name` — bundle name slug: `^[a-z0-9]([a-z0-9-]*[a-z0-9])?$`.
- `:id` — concept ID exactly as `list` returns (e.g. `tables/orders`). `:path` FastAPI converter to allow slashes.
- **Auth:** single server-wide token via `--token` flag. If `--token` is empty string, auth disabled entirely — all endpoints use `public/` namespace. GET endpoints: if `--public-read` is False (default), token required. If True, missing token → `public/` namespace. POST always requires auth when token is set. No user model, no token-per-bundle, no registration.
- `?force=true` query param on POST to replace existing bundle in your namespace. No backups kept on replace (YAGNI — add `--keep-backups` flag later if needed).

### Non-conformant bundles

`api.list_concepts` and `api.show_concept` raise `ValueError` on non-conformant bundles. For a server browsing use case, we still want partial results. `FileStore.list_concepts` catches this, logs a warning, and falls back to listing all non-reserved `.md` files. `FileStore.read_concept` falls back to raw file read. Both guard against path traversal.

---

## Server files

### `src/okf/server/storage.py`

`FileStore` class — sole access point to the filesystem. No raw `Path` operations in route handlers. All methods take `owner_hash` for namespace resolution.

```python
class FileStore:
    def __init__(self, root: str | Path): ...

    # Namespace
    def namespace_path(self, owner_hash: str) -> Path           # store_root / owner_hash
    def list_bundles(self, owner_hash: str) -> list[str]        # bundle names in namespace

    # Per-bundle path
    def bundle_path(self, owner_hash: str, name: str) -> Path   # namespace / name
    def bundle_exists(self, owner_hash: str, name: str) -> bool

    # Concepts — delegates to okf.api with graceful fallback
    def list_concepts(self, owner_hash: str, name: str) -> list[str]
    def read_concept(self, owner_hash: str, name: str, cid: str) -> tuple[dict, str]
        # (frontmatter, body), guards traversal

    # Import/export
    def store_bundle(self, owner_hash: str, name: str, tar_path: Path, force: bool = False)
        -> tuple[list[str], list[str]]
        # 1. if bundle_exists and not force → return (["already exists"], [])
        # 2. unpack tar to temp dir (tempfile.mkdtemp)
        # 3. run okf.core.check_conformance(temp_dir)
        # 4. if errors → return (errors, []), clean up temp
        # 5. if clean → if force: delete existing. Move temp → bundle_path
        # 6. write .owner with owner_hash
        # 7. return ([], [warnings])
    def archive_bundle(self, owner_hash: str, name: str) -> Path  # creates temp tar.gz, returns path
    def delete_bundle(self, owner_hash: str, name: str) -> None
```

### `src/okf/server/app.py`

FastAPI app factory. Auth deps return `AuthInfo` dataclass with `token_hash` field. Route handlers pass it to `FileStore` methods as `owner_hash`.

```python
from dataclasses import dataclass

@dataclass
class AuthInfo:
    token_hash: str  # sha256(token)[:16], or "public" when auth disabled

def create_app(store: FileStore, token: str, public_read: bool) -> FastAPI:
    app = FastAPI(title="okf-server")

    @app.get("/api/v1/")
    def health(): ...

    @app.get("/api/v1/bundles")
    def list_bundles(auth: AuthInfo = Depends(require_auth)): ...

    @app.post("/api/v1/bundles/{name}")
    def publish_bundle(name: str, bundle: UploadFile, force: bool = False,
                       auth: AuthInfo = Depends(require_auth)): ...

    @app.get("/api/v1/bundles/{name}/concepts")
    def list_concepts(name: str, auth: AuthInfo = Depends(optional_auth)): ...

    @app.get("/api/v1/bundles/{name}/concepts/{cid:path}")
    def get_concept(name: str, cid: str, auth: AuthInfo = Depends(optional_auth)): ...

    @app.get("/api/v1/bundles/{name}/archive")
    def download_bundle(name: str, auth: AuthInfo = Depends(optional_auth)): ...

    return app
```

Auth dependencies:
- `require_auth` — if server token set, check `Authorization: Bearer <token>`. Return `AuthInfo(token_hash)`. If no server token set, return `AuthInfo("public")`.
- `optional_auth` — if `public_read=True` and no header, return `AuthInfo("public")`. If header present, verify token and return `AuthInfo(token_hash)`. If `public_read=False`, same as `require_auth`.

### `src/okf/server/cli.py`

```python
app = typer.Typer(name="okf-server")

@app.command()
def serve(
    token: str = typer.Option("", help="Bearer token (empty disables auth)"),
    host: str = typer.Option("0.0.0.0"),
    port: int = typer.Option(8080),
    store: str = typer.Option("~/.okf/store"),
    public_read: bool = typer.Option(False, help="Allow unauthenticated GET requests"),
):
    store_path = Path(store).expanduser()
    store_path.mkdir(parents=True, exist_ok=True)
    file_store = FileStore(store_path)
    app = create_app(file_store, token=token, public_read=public_read)
    uvicorn.run(app, host=host, port=port)
```

---

## What changes in existing code

### `src/okf/core.py` — one line

```python
OKF_VERSION = "0.1"
```

### `pyproject.toml` — two additions

```toml
[project.scripts]
okf-server = "okf.server.cli:app"

[project.optional-dependencies]
server = ["fastapi>=0.115", "python-multipart>=0.0.20", "uvicorn[standard]>=0.30"]
```

### Everything else: zero changes

- `okf.cli`, `okf.api`, `okf.commands.*` — untouched
- No new deps for `okf` CLI itself

---

## Testing

### `tests/server/test_storage.py`

Unit tests against `FileStore` backed by `tmp_path`. No FastAPI.

| Test | What |
|------|------|
| `test_namespace_isolation` | Two tokens, same bundle name → stored in separate namespaces |
| `test_store_conformant` | Valid tar → stored in namespace, listed, readable |
| `test_store_nonconformant` | Invalid tar → errors returned, nothing stored |
| `test_store_replace_with_force` | Second publish with force in same namespace → replaces |
| `test_store_replace_without_force` | Second publish without force → error |
| `test_read_concept_traversal` | `../../etc/passwd` → ValueError |
| `test_archive_roundtrip` | Store → archive → unpack → same content |
| `test_list_concepts_nonconformant` | Non-conformant bundle → still returns .md files (graceful fallback) |
| `test_list_concepts_empty` | Empty bundle → [] |
| `test_list_bundles` | Returns only bundles in given namespace |
| `test_owner_file_written` | After publish, `.owner` matches namespace hash |
| `test_public_namespace` | owner_hash="public" → stored in `public/` |

### `tests/server/test_api.py`

Integration tests via `TestClient` against `create_app()` with a `tmp_path`-backed `FileStore`.

| Test | What |
|------|------|
| `test_health` | GET / → 200, version fields |
| `test_publish_no_token_401` | No token when server has token → 401 |
| `test_publish_wrong_token_401` | Wrong token → 401 |
| `test_publish_valid_201` | Correct token → 201, stored in token namespace, .owner written |
| `test_publish_no_auth_disabled` | Server with empty token → 201, stored in `public/` |
| `test_publish_same_name_different_tokens` | Two tokens publish same name → both succeed, isolated |
| `test_publish_force_same_namespace` | Force-replace in same namespace → 201, content replaced |
| `test_list_bundles_200` | GET /bundles → returns bundles in authenticated namespace |
| `test_list_concepts_200` | GET /concepts → JSON array |
| `test_get_concept_200` | GET /concept → raw markdown, correct Content-Type |
| `test_get_concept_404` | Unknown ID → 404 |
| `test_get_archive_200` | GET /archive → tar.gz, Content-Type |
| `test_get_archive_404` | Unknown bundle → 404 |
| `test_public_read_blocked` | `--public-read` false, no token on GET → 401 |
| `test_public_read_allowed` | `--public-read` true, no token on GET → 200 (from `public/`) |

---

## Phase 2: Multi-user SaaS (future, not implemented now)

- Token-per-user or OAuth2 registration
- Rate limiting
- Multi-worker locking for concurrent publish race window

## Phase 3: Client commands (future, not implemented now)

After server is built and tested:

- `okf publish <bundle-dir> --url <url> --token <token> [--force]` — validate locally, tar.gz, POST multipart
- `okf clone <url> <local-dir> [--token <token>]` — GET /archive, stream-unpack
- `okf list --remote <url> <bundle-name> [--token <token>]` — GET /concepts
- `okf show --remote <url> <bundle-name> <concept-id> [--token <token>]` — GET /concepts/:id

Client uses stdlib `urllib` + `tarfile` — no new dependencies.

---

## Open questions resolved

1. **Auth:** Bearer token only. `--token ""` disables auth. GET auth configurable via `--public-read`.
2. **Namespace:** `sha256(token)[:16]` directory per user. Bundles unique per namespace.
3. **Bundle name:** Slug regex `^[a-z0-9]([a-z0-9-]*[a-z0-9])?$`.
4. **Storage:** `<store_root>/<namespace>/<bundle-name>/` directory trees. Default `~/.okf/store`, overridable.
5. **Ownership:** `.owner` file for metadata. No 403 errors — namespace isolation prevents cross-user access.
6. **Backups:** No. `?force=true` replaces in place in your namespace. YAGNI.
7. **Multiple bundles:** Yes — one server, many bundles per namespace.
8. **List bundles:** `GET /api/v1/bundles` returns bundles in authenticated namespace.
9. **Healthcheck:** `GET /api/v1/` returns version info.
10. **Storage seam:** `FileStore` class — route handlers never touch disk directly.
