# Plan: OKF hosted server + remote commands (v4 — GitHub-style URLs)

## Motivation

Currently `okf` operates only on local filesystem bundles. The goal is to turn
`okf` into a public knowledge repository where:

- Anyone can browse knowledge bundles at `okf.com/<username>/<bundle>`.
- Registered users can publish OKF bundles with `okf publish`.
- Anyone can clone/download a bundle with `okf clone <username>/<bundle>`.
- Browsing a bundle lands on its root `index.md`.
- All published bundles are public by default; private bundles are a future add-on.

This plan replaces the previous token-hash namespace design with a real
username namespace, SQLite-backed auth, and GitHub-style URLs.

---

## Architecture

Two binaries, one package:

```text
pyproject.toml
├── [project.scripts]
│   ├── okf         = "okf.cli:app"           ← existing, extended with remote commands
│   └── okf-server  = "okf.server.cli:app"    ← NEW
├── [project.optional-dependencies]
│   └── server = ["fastapi>=0.115", "python-multipart>=0.0.20", "uvicorn[standard]>=0.30"]
```

```text
src/okf/
├── core.py                     ← +OKF_VERSION constant only
├── api.py                      ← unchanged
├── cli.py                      ← registers publish, clone, --remote flags
├── commands/
│   ├── bundle.py, list.py, show.py, validate.py  ← list/show gain --remote
│   ├── publish.py              ← NEW
│   └── clone.py                ← NEW
└── server/                     ← NEW
    ├── __init__.py
    ├── auth.py                 ← SQLite user store, password hashing, tokens
    ├── storage.py              ← FileStore class
    ├── app.py                  ← FastAPI app + routes
    └── cli.py                  ← typer app for okf-server serve
```

---

## Auth model

Real user accounts backed by SQLite (`sqlite3` from the stdlib, no new
dependency).

### Schema

```sql
CREATE TABLE users (
    username TEXT PRIMARY KEY,
    password_hash BLOB,
    salt BLOB,
    token TEXT UNIQUE,
    created_at TEXT
);
```

- Passwords hashed with `hashlib.scrypt` + random salt.
- Tokens generated with `secrets.token_urlsafe(32)`.
- `Authorization: Bearer <token>` is used for all authenticated endpoints.

### Endpoints

```text
POST /api/v1/auth/register
  body: {"username": "...", "password": "..."}
  → 201 {"username": "...", "token": "..."}
  → 409 if username is taken
  → 400 if username/bundle-slug rules violated

POST /api/v1/auth/login
  body: {"username": "...", "password": "..."}
  → 200 {"username": "...", "token": "..."}
  → 401 if credentials are invalid
```

Registration is open by default. The server can disable it with
`--allow-register false`.

### Reserved usernames

These are reserved to avoid route collisions:

```text
api, static, health, www, default
```

---

## Storage design

**Format on disk:** extracted directory tree at
`<store_root>/<username>/<bundle-name>/`.

Why directories:

- `list`/`show` are hot path — direct filesystem reads.
- The server reuses `okf.api.list_concepts` / `okf.api.show_concept`.
- `archive` is cold path — tar.gz created on-the-fly.

```text
store/
├── alice/
│   └── widgets/
│       ├── .owner          ← "alice"
│       ├── index.md
│       ├── tables/
│       │   ├── orders.md
│       │   └── customers.md
│       └── ...
└── bob/
    └── api-docs/
        └── ...
```

- Username = namespace.
- Bundle names and usernames share the slug regex:
  `^[a-z0-9]([a-z0-9-]*[a-z0-9])?$`.
- `.owner` file stores the publishing username for portability.

---

## API contract

### Public routes (no auth)

```text
GET /api/v1/                              → healthcheck
  200  { "okf_server": "0.1.0", "okf_version": "0.1" }

GET /api/v1/catalog                       → all public bundles
  200  [{ "username": "alice", "name": "widgets" }, ...]

GET /{username}                           → user's bundles
  200  ["widgets", "api-docs"]
  404  if user has no bundles

GET /{username}/{bundle}                  → root index.md
  200  text/markdown; charset=utf-8
  404  if bundle or root index.md not found

GET /{username}/{bundle}/concepts         → concept IDs
  200  ["tables/orders", "tables/customers", "playbooks/oncall"]
  404  if bundle not found

GET /{username}/{bundle}/concepts/{id:path}
                                          → raw concept markdown
  200  text/markdown; charset=utf-8
  404  if bundle or concept not found

GET /{username}/{bundle}/archive          → tar.gz download
  200  application/gzip
  404  if bundle not found
```

`:id` uses the `:path` FastAPI converter to allow slashes (e.g.
`tables/orders`).

### Authenticated routes

```text
GET /api/v1/bundles                       → list your bundles
  Auth: Bearer <token>
  200  ["widgets", "api-docs"]

POST /api/v1/bundles/{name}
  Auth:   Bearer <token>
  Body:   multipart form, field "bundle" = tar.gz file
  Query:  ?force=true
  201  { "username": "...", "name": "...", "concepts": 42 }
  400  { "error": "not conformant", "details": [...] }
  409  { "error": "bundle already exists, use ?force=true" }
```

### Publish flow

1. Client tars the local OKF bundle directory.
2. `POST /api/v1/bundles/{name}` uploads the tar.gz.
3. Server unpacks to a temp directory.
4. Server runs `okf.core.check_conformance(temp_dir)`.
5. Non-conformant bundles are rejected with a `400` and the conformance errors.
6. Conformant bundles are moved to `store/<username>/<name>/`.
7. If the bundle exists and `?force=true` is not set, return `409`.
8. Write `.owner` containing the username.

Because all published bundles are public by default, the public routes can read
any stored bundle.

---

## Client commands

Default server URL is defined in code and can be overridden with `--url` or an
`OKF_URL` environment variable.

```python
DEFAULT_SERVER_URL = "https://okf.com"  # patch for your own domain
```

### Commands

```text
okf publish <bundle-dir> [<name>] --token <token> [--url <url>] [--force]
  - Default <name> is the bundle directory name.
  - Tars the directory and POSTs to /api/v1/bundles/{name}.

okf clone <ref> [local-dir] [--token <token>] [--url <url>]
  - <ref> is either username/bundle or a full URL.
  - Downloads /{username}/{bundle}/archive and extracts it.
  - Default local-dir is the bundle name.

okf list --remote <ref> [--token <token>] [--url <url>]
  - GET /{username}/{bundle}/concepts.

okf show --remote <ref> <concept-id> [--token <token>] [--url <url>]
  - GET /{username}/{bundle}/concepts/{id}.
```

Client uses stdlib `urllib` + `tarfile` only — no new CLI dependencies.

---

## Server files

### `src/okf/server/auth.py`

```python
class UserStore:
    def __init__(self, db_path: str | Path): ...

    def register(self, username: str, password: str) -> str: ...  # returns token
    def login(self, username: str, password: str) -> str: ...      # returns token
    def username_for_token(self, token: str) -> str | None: ...
    def username_exists(self, username: str) -> bool: ...
```

Password hashing:

```python
salt = secrets.token_bytes(32)
hash = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1)
```

### `src/okf/server/storage.py`

```python
class FileStore:
    def __init__(self, root: str | Path): ...

    def user_path(self, username: str) -> Path
    def list_bundles(self, username: str) -> list[str]

    def bundle_path(self, username: str, name: str) -> Path
    def bundle_exists(self, username: str, name: str) -> bool

    def list_concepts(self, username: str, name: str) -> list[str]
    def read_concept(self, username: str, name: str, cid: str) -> tuple[dict, str]

    def store_bundle(self, username: str, name: str, tar_path: Path, force: bool = False)
        -> tuple[list[str], list[str]]        # (errors, warnings)
    def archive_bundle(self, username: str, name: str) -> Path
    def delete_bundle(self, username: str, name: str) -> None
```

All path construction validates slugs and guards against traversal.

### `src/okf/server/app.py`

```python
@dataclass
class AuthInfo:
    username: str

def create_app(store: FileStore, user_store: UserStore, allow_register: bool) -> FastAPI: ...
```

Routes:

```python
@app.get("/api/v1/")
def health(): ...

@app.post("/api/v1/auth/register")
def register(credentials: RegisterRequest): ...

@app.post("/api/v1/auth/login")
def login(credentials: LoginRequest): ...

@app.get("/api/v1/bundles")
def list_my_bundles(auth: AuthInfo = Depends(require_auth)): ...

@app.post("/api/v1/bundles/{name}")
def publish_bundle(name: str, bundle: UploadFile, force: bool = False,
                   auth: AuthInfo = Depends(require_auth)): ...

@app.get("/api/v1/catalog")
def catalog(): ...

@app.get("/{username}")
def user_bundles(username: str): ...

@app.get("/{username}/{bundle}")
def bundle_landing(username: str, bundle: str): ...

@app.get("/{username}/{bundle}/concepts")
def list_concepts(username: str, bundle: str): ...

@app.get("/{username}/{bundle}/concepts/{cid:path}")
def get_concept(username: str, bundle: str, cid: str): ...

@app.get("/{username}/{bundle}/archive")
def download_bundle(username: str, bundle: str): ...
```

### `src/okf/server/cli.py`

```python
app = typer.Typer(name="okf-server")

@app.command()
def serve(
    host: str = typer.Option("0.0.0.0"),
    port: int = typer.Option(8080),
    store: str = typer.Option("~/.okf/store"),
    database: str = typer.Option("~/.okf/server.db"),
    allow_register: bool = typer.Option(True, help="Allow new user registration"),
):
    ...
```

---

## What changes in existing code

### `src/okf/core.py` — one line

```python
OKF_VERSION = "0.1"
```

### `src/okf/cli.py`

Register new commands and extend `list`/`show`:

```python
app.command("publish")(publish)
app.command("clone")(clone)
```

`list` and `show` gain a `--remote` option.

### `pyproject.toml`

```toml
[project.scripts]
okf-server = "okf.server.cli:app"

[project.optional-dependencies]
server = ["fastapi>=0.115", "python-multipart>=0.0.20", "uvicorn[standard]>=0.30"]
```

### Everything else

- `okf.api`, `okf.commands.bundle`, `okf.commands.validate` — untouched.
- No new deps for the base `okf` CLI.

---

## Testing

### `tests/server/test_auth.py`

| Test | What |
|------|------|
| `test_register_and_login` | Register returns token; login returns same token |
| `test_register_duplicate_username` | Second registration with same username returns 409 |
| `test_login_wrong_password` | Bad password returns 401 |
| `test_reserved_username_rejected` | `api`, `www`, etc. cannot be registered |
| `test_invalid_username_slug` | Usernames must match slug regex |
| `test_username_for_token` | Token lookup returns correct username |

### `tests/server/test_storage.py`

| Test | What |
|------|------|
| `test_store_conformant_bundle` | Valid tar → stored, listed, readable |
| `test_store_nonconformant_bundle` | Invalid tar → errors, nothing stored |
| `test_store_replace_with_force` | Force publish replaces existing bundle |
| `test_store_replace_without_force` | Second publish without force → error |
| `test_username_namespace_isolation` | Same bundle name under different users is independent |
| `test_read_concept_traversal` | `../../etc/passwd` → rejected |
| `test_archive_roundtrip` | Store → archive → unpack → same content |
| `test_owner_file_written` | `.owner` contains username |
| `test_list_bundles` | Returns only bundles for the given username |

### `tests/server/test_api.py`

Integration tests via FastAPI `TestClient`.

| Test | What |
|------|------|
| `test_health` | GET /api/v1/ returns versions |
| `test_register` | POST /api/v1/auth/register creates user |
| `test_login` | POST /api/v1/auth/login returns token |
| `test_publish_valid_201` | Authenticated publish stores bundle |
| `test_publish_no_auth_401` | Publish without token fails |
| `test_publish_nonconformant_400` | Bad bundle rejected with details |
| `test_publish_force` | Force replaces bundle |
| `test_publish_same_name_different_users` | Two users publish same name; both succeed |
| `test_list_my_bundles` | /api/v1/bundles returns authenticated user's bundles |
| `test_catalog_lists_public_bundles` | /api/v1/catalog lists all bundles |
| `test_user_bundles` | /{username} returns that user's bundles |
| `test_bundle_landing` | /{username}/{bundle} returns root index.md |
| `test_list_concepts` | /concepts returns JSON IDs |
| `test_get_concept` | /concepts/{id} returns raw markdown |
| `test_download_archive` | /archive returns tar.gz |
| `test_invalid_slug_404` | Bad username/bundle names return 404 |

### `tests/test_cli.py`

| Test | What |
|------|------|
| `test_publish_invokes_api` | Exit code 0, uploads tar |
| `test_clone_downloads_archive` | Exit code 0, directory created |
| `test_list_remote` | `--remote` hits concepts endpoint |
| `test_show_remote` | `--remote` hits concept endpoint |
| `test_url_override` | `--url` changes target server |

---

## Implementation phases

1. **Auth + user store** — SQLite schema, register/login, token lookup, tests.
2. **Storage + publish** — `FileStore`, authenticated upload, conformance check,
   force replace, tests.
3. **Public read routes** — `/{username}`, `/{username}/{bundle}`, `/concepts`,
   `/concepts/{id}`, `/archive`, `/api/v1/catalog`, tests.
4. **Client commands** — `publish`, `clone`, `--remote` for `list`/`show`, CLI tests.
5. **Future** — private bundles, token rotation, password reset, search,
   HTML landing pages.

---

## Open questions resolved

1. **Landing page:** `/{username}/{bundle}` returns the root `index.md` as
   `text/markdown`.
2. **Visibility:** All bundles are public by default; private bundles are a
   future add-on.
3. **Auth:** SQLite-backed registration, login, and bearer-token API access.
4. **Default domain:** CLI defaults to a configurable `DEFAULT_SERVER_URL`;
   `--url` and `OKF_URL` override it.
