# Plan: OKF hosted server + remote commands

## Motivation

Currently `okf` operates only on local filesystem bundles. User wants:

- `okf publish` — upload local OKF bundle to hosted service
- `okf list --remote` / `okf show --remote` — browse remote bundle without download
- `okf clone` — download remote bundle to local

Three hosting options considered (HTTP API, S3, Git). HTTP REST API chosen — it's the only option that cleanly supports `list`/`show` without full download, and requires zero new dependencies on the client side (stdlib `urllib` + `tarfile`).

The server is also part of this repo — `okf-server` binary shipped alongside `okf` CLI, reusing `okf.core` for validation so conformance logic stays in one place.

---

## Architecture overview

Two binaries, one package:

```
pyproject.toml
├── [project.scripts]
│   ├── okf         = "okf.cli:app"           ← existing, unchanged
│   └── okf-server  = "okf.server.cli:app"    ← NEW
├── [project.optional-dependencies]
│   └── server = ["fastapi>=0.115", "python-multipart>=0.0.20"]
```

```
src/okf/
├── core.py                    ← unchanged (shared validation)
├── cli.py                     ← unchanged (existing okf CLI)
├── commands/                  ← unchanged for now
│   ├── bundle.py
│   ├── list.py
│   ├── show.py
│   └── validate.py
└── server/                    ← NEW
    ├── __init__.py
    ├── app.py                 ← FastAPI app + 4 routes + auth middleware
    ├── storage.py             ← bundle read/write/validate on disk
    └── cli.py                 ← typer app for okf-server serve command
```

Server reuses `check_conformance` and `parse_frontmatter` from `okf.core` — no validation code duplicated.

---

## API contract

```
POST   /api/v1/bundles/:name
  Auth:   Bearer <token>
  Body:   multipart form, field "bundle" = tar.gz file
  OK 201  { "name": "...", "concepts": 42 }
  ERR 400  { "error": "not conformant", "details": ["path: missing type", ...] }
  ERR 409  { "error": "bundle already exists, use ?force=true" }

GET    /api/v1/bundles/:name/concepts
  Auth:   Bearer <token> (optional, server may disable)
  OK 200  ["tables/orders", "tables/customers", "playbooks/oncall"]

GET    /api/v1/bundles/:name/concepts/:id
  Auth:   Bearer <token> (optional)
  OK 200  raw markdown (Content-Type: text/markdown; charset=utf-8)
  ERR 404  { "error": "concept not found" }

GET    /api/v1/bundles/:name/archive
  Auth:   Bearer <token> (optional)
  OK 200  application/gzip tar archive
  ERR 404  { "error": "bundle not found" }
```

- `:name` — bundle name slug (alphanumeric + hyphens, e.g. `my-kb`)
- `:id` — concept ID exactly as `list` returns (e.g. `tables/orders`)
- Auth: single server-wide token via `--token` flag. No user model or token-per-bundle (YAGNI — one server, one team). If `--token` is empty string, auth is disabled.
- `?force=true` query param on POST to replace existing bundle

---

## Phase 1: Server

### `src/okf/server/storage.py`

Thin filesystem layer over `~/.okf/store/<bundle-name>/`.

```python
STORE_ROOT = Path.home() / ".okf" / "store"

def bundle_path(name: str) -> Path          # STORE_ROOT / name
def bundle_exists(name: str) -> bool
def list_bundles() -> list[str]
def list_concepts(name: str) -> list[str]   # walks .md files, skips SPEC_RESERVED
def read_concept(name: str, cid: str) -> str # reads .md file, validates path traversal
def archive_bundle(name: str) -> Path        # creates temp tar.gz, returns path
def store_bundle(name: str, tar_path: Path) -> tuple[list[str], list[str]]
    # 1. unpack tar to temp dir
    # 2. run check_conformance(temp_dir)
    # 3. if errors → return (errors, [])
    # 4. if clean → move to bundle_path(name), return ([], [])
def delete_bundle(name: str)
```

- `read_concept` guards path traversal (concept ID must not escape bundle)
- `store_bundle` cleans up temp dir on failure
- All paths use `Path`, all text is UTF-8

### `src/okf/server/app.py`

FastAPI app with dependency-injected config:

```python
app = FastAPI(title="okf-server")

# Dependency
def get_config():
    # reads from app.state set during startup

# Routes
POST   /api/v1/bundles/{name}       → publish_bundle()
GET    /api/v1/bundles/{name}/concepts/{id:path} → get_concept()  # :path for slashes
GET    /api/v1/bundles/{name}/concepts           → list_concepts()
GET    /api/v1/bundles/{name}/archive            → download_bundle()
```

Auth as FastAPI middleware/dependency:
- If server token is set, require `Authorization: Bearer <token>` on POST
- GET endpoints: auth optional (server configures via `--public-read` flag)
- 401 on missing/invalid token

### `src/okf/server/cli.py`

```python
@app.command()
def serve(
    token: str = typer.Option("", help="Bearer token (empty disables auth)"),
    host: str = typer.Option("0.0.0.0"),
    port: int = typer.Option(8080),
    store: str = typer.Option("~/.okf/store"),
    public_read: bool = typer.Option(False, help="Allow unauthenticated GET"),
):
    # start uvicorn
```

### `pyproject.toml` changes

Two additions:
1. `[project.optional-dependencies]` with `server` extra
2. `[project.scripts]` with `okf-server` entrypoint

No changes to existing deps.

---

## Phase 2: Client commands (future)

After server is built and tested, add client-side commands:

### `src/okf/commands/publish.py`

```
okf publish <bundle-dir> --url <url> --token <token> [--force]
```

1. Validates bundle is conformant locally first (fast-fail)
2. Creates tar.gz in memory via `tarfile`
3. POSTs to `{url}/bundles/{name}` with multipart form
4. Prints result or error details

### `src/okf/commands/clone.py`

```
okf clone <url> <local-dir> [--token <token>]
```

1. GET `{url}/archive`
2. Stream-unpack tar.gz to local dir
3. Validate result

### `src/okf/commands/list.py` — add `--remote` flag

```
okf list --remote <url> <bundle-name> [--token <token>]
```

Uses `okf list` but with `--remote` destination.

### `src/okf/commands/show.py` — add `--remote` flag

```
okf show --remote <url> <bundle-name> <concept-id> [--token <token>]
```

Uses `okf show` but with `--remote` destination.

### `src/okf/core.py` — add `okf_version` metadata

Not a new command, but server API responses should include OKF version. Add:

```python
OKF_VERSION = "0.1"  # current spec version
```

Used in server responses (`{ "okf_version": "0.1", ... }`) and future client.

---

## Testing strategy

### Server tests (`tests/server/`)

| Test | What it covers |
|------|---------------|
| `test_storage_store_conformant` | Valid bundle → stored, listable, readable |
| `test_storage_store_nonconformant` | Invalid bundle → errors returned, nothing stored |
| `test_storage_store_replaces_with_force` | Second publish replaces first |
| `test_storage_read_concept_traversal` | `../../etc/passwd` → 404 |
| `test_storage_archive_roundtrip` | Store → archive → unpack → same content |
| `test_api_publish_no_auth` | No token → 401 (when server has token) |
| `test_api_publish_auth` | Correct token → 201 |
| `test_api_list_concepts` | GET concepts → JSON array |
| `test_api_get_concept` | GET concept → raw markdown |
| `test_api_concept_not_found` | Unknown ID → 404 |
| `test_api_download_archive` | GET archive → tar.gz, unpackable |

Use FastAPI `TestClient` — no process spawning needed.

### Existing CLI tests

No changes. Server code lives in `src/okf/server/` and doesn't touch existing commands or `core.py` (except the trivial `OKF_VERSION` constant).

---

## Open questions

1. **Auth: token only, or also API-key header?** Token via `--token` flag is simplest. Can add `--api-key` later if needed.

2. **Bundle name validation?** Slug regex: `^[a-z0-9]([a-z0-9-]*[a-z0-9])?$`. Names become directory names on disk.

3. **Server storage: `~/.okf/store` or configurable?** Default `~/.okf/store`, override via `--store`. In-memory storage for tests.

4. **Backups on replace?** When `?force=true` replaces a bundle, keep old as `<name>.bak`? Or just delete? Default: just delete. Add `--keep-backups` flag to server later if needed. (YAGNI)

5. **Multiple bundles?** Yes — one server, many bundles. `/api/v1/bundles/:name` is the namespace.

6. **Server discovery?** `GET /api/v1/` returns `{ "okf_server": "0.1.0", "okf_version": "0.1" }` — healthcheck + version info.

---

## What does NOT change

- `okf bundle` — stays local. Publishing is a separate step.
- `okf validate` — stays local. Remote validation happens on server at publish time via same `check_conformance`.
- `okf list` / `okf show` — default behavior unchanged. `--remote` flag adds new code path, doesn't modify existing.
- `okf.core` — `check_conformance`, `parse_frontmatter`, `SPEC_RESERVED` all untouched. Server imports them directly.
- No new deps for `okf` CLI itself. `fastapi` + `python-multipart` are optional `[server]` extras.
