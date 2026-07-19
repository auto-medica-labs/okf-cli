# Architecture

## Runtime shape

`okf-cli` has a layered architecture:

- **CLI layer** (`src/okf/cli.py`) — Typer app creation, command registration, `--version` callback.
- **API layer** (`src/okf/api.py`) — programmatic Python functions for local bundle operations; all local business logic lives here.
- **Core layer** (`src/okf/core.py`) — shared parsing, formatting, conformance helpers.
- **Command wrappers** (`src/okf/commands/`) — thin IO/error bridges from CLI args to API calls or remote HTTP operations.
- **Remote client** (`src/okf/remote.py`) — URL resolution, bearer-token HTTP helpers, and tar archive packing/extraction used by `publish`, `clone`, and remote `list`/`show`.
- **Server subsystem** (`src/okf/server/`) — optional FastAPI application (`app.py`), SQLite-backed user store (`auth.py`), filesystem bundle store (`storage.py`), and `okf-server` Typer entrypoint (`cli.py`).

Why this split: the API layer is the canonical home for local logic. Commands handle Typer argument parsing, error display, and exit codes; remote commands delegate HTTP details to `remote.py`. `core.py` is pure utility with no side effects. The server is an optional deployable peer, not a dependency of local CLI use.

## Key modules

### `src/okf/api.py` — programmatic API

Public functions and return types:

| Function                                       | Returns          | Key behavior                                                                  |
| ---------------------------------------------- | ---------------- | ----------------------------------------------------------------------------- |
| `bundle(input_dir, output_dir, ...)`           | `BundleResult`   | Full bundle pipeline with link checking, `.okfignore`, `AGENTS.md` generation |
| `convert_file(input_file, output_file, type_)` | `BundleResult`   | Convert single markdown file to OKF concept (timestamp from mtime)            |
| `convert_content(content, output_file, type_)` | `BundleResult`   | Convert raw markdown string to OKF concept (no timestamp)                     |
| `list_concepts(bundle_dir)`                    | `list[str]`      | Conformance-gated concept ID listing                                          |
| `show_concept(bundle_dir, concept_id)`         | `ConceptContent` | Conformance-gated concept read with path traversal guard                      |
| `validate(bundle_dir)`                         | `ValidateResult` | Conformance check with `.ok` property                                         |

Internal helpers (not public API): `_iter_links`, `_resolve_md_target`, `_load_okfignore`, `_generate_indexes`, `_write_concept`.

### `src/okf/core.py` — shared utilities

- `RESERVED` — filenames `bundle` skips: `index.md`, `log.md`, `readme.md`.
- `SPEC_RESERVED` — spec-level reserved names: `index.md`, `log.md`, `agents.md`.
- `build_frontmatter(type_, title, description, timestamp)` — YAML frontmatter via JSON-escaped values.
- `parse_md(text)` — extracts title/description/body; strict first, lenient fallback.
- `parse_frontmatter(text)` — parses YAML frontmatter, returns `None` for invalid.
- `check_conformance(directory)` — validates OKF §9, returns `(errors, warnings)`.

### Command wrappers (`src/okf/commands/`)

Thin IO/error bridges. Local commands import from `okf.api`; remote commands import from `okf.remote`. All translate exceptions to Typer exit codes. No business logic.

- `bundle`, `validate` — local API only.
- `list`, `show` — branch on `--remote` to talk to `okf-server`; otherwise call local API.
- `publish`, `clone` — HTTP wrappers around `okf.remote` helpers.

### `src/okf/remote.py` — remote client

Responsibilities:

- `server_url(url)` — explicit `--url` → `OKF_URL` env → default `https://okf.com`.
- `parse_ref(ref, base_url)` — accept `username/bundle` or full URL and return `(base_url, username, bundle)`.
- `http_get`, `http_post` — stdlib `urllib`-based requests with optional bearer token.
- `tar_directory`, `extract_archive` — tar.gz pack/unpack for publish/clone.

No third-party HTTP client; `urllib` keeps local CLI lightweight.

### `src/okf/server/` — okf-server

Modules:

| Module | Role |
| ------ | ---- |
| `app.py` | FastAPI route definitions; health, auth, authenticated publish/list, public catalog/landing/concept/archive routes. |
| `auth.py` | `UserStore`: SQLite table of scrypt password hashes, salts, and bearer tokens. |
| `storage.py` | `FileStore`: stores bundles under `<root>/<username>/<bundle>/`, validates slugs, checks OKF conformance on ingest, archives bundles on demand. |
| `_common.py` | Slug regex validation and reserved usernames (`api`, `static`, `health`, `www`, `default`). |
| `cli.py` | `okf-server serve` / `version` Typer entrypoint. |

Server routes group into:

- Public API: `GET /api/v1/`, `GET /api/v1/catalog`, `POST /api/v1/auth/register`, `POST /api/v1/auth/login`.
- Authenticated API: `GET /api/v1/bundles`, `POST /api/v1/bundles/{name}` (publish).
- Public user-facing: `GET /{username}`, `GET /{username}/{bundle}` (index), `GET /{username}/{bundle}/concepts`, `GET /{username}/{bundle}/concepts/{cid}`, `GET /{username}/{bundle}/archive`.

## Command execution flow

### `okf bundle` (via `api.bundle()`)

1. Read source directory + optional `.okfignore` (`_load_okfignore`).
1. Walk `*.md`, skipping reserved names and ignored paths.
1. Parse each markdown file via `parse_md` (strict first, lenient fallback).
1. Scan markdown body links via `_iter_links` / `_resolve_md_target` — warns on missing or out-of-bundle targets; `--strict` makes these fatal.
1. Build YAML frontmatter via `build_frontmatter`.
1. Write transformed files and generate `index.md` per directory.
1. Write `AGENTS.md` at output root with navigation guidance for the knowledge base (skipped when `--strict` is used).

### `okf validate` (via `api.validate()`)

1. Ensure target directory exists and has markdown files.
1. Call `check_conformance` once.
1. Return `ValidateResult` with file count, errors, and warnings.

### `okf list` and `okf show` (via `api.list_concepts()` / `api.show_concept()`)

Both functions first run `check_conformance`. If directory is non-conformant, they raise `ValueError`.

Reason: reading APIs should not return misleading data from broken bundles.

With `--remote`, the wrappers skip the local API entirely: they parse the ref, call the server's `/{username}/{bundle}/concepts` or `/.../concepts/{cid}` endpoint, and print the response.

### `okf publish` and `okf clone`

`publish`:

1. Validate the local bundle directory exists.
1. Resolve bundle name (positional `name` or directory name) and validate it as a slug.
1. Pack the directory into a tar.gz via `tar_directory`.
1. `POST /api/v1/bundles/{name}` with `multipart/form-data` and `Authorization: Bearer <token>`.
1. Unlink the temporary archive and print the published URL.

`clone`:

1. Parse `username/bundle` ref and optional `--url`.
1. `GET /{username}/{bundle}/archive` to download the tar.gz.
1. Extract into the destination directory, then unwrap a single top-level directory if the server wrapped the bundle that way.
1. Print the clone destination.

### `okf-server serve`

1. `FileStore` opens/creates the store root (`~/.okf/store` by default).
1. `UserStore` opens/creates the SQLite database (`~/.okf/server.db` by default).
1. `create_app(store, users, allow_register)` builds the FastAPI app.
1. `uvicorn.run(api, host, port)` starts the HTTP server.

## Shared invariants

- Reserved name handling differs by phase:
  - Bundling phase skips `index.md`, `log.md`, `README.md` (`RESERVED`).
  - Spec-conformance phase reserves `index.md`, `log.md`, `agents.md` (`SPEC_RESERVED`). `agents.md` is reserved but skipped during conformance checks (not an error).
- Non-UTF-8 markdown is a conformance error.
- `type` frontmatter is required and must be non-empty for non-reserved concept files.

Source: `src/okf/core.py` (constants), `src/okf/api.py` (enforcement).

## Evolution notes (from git history)

Major behavior shifts:

- project started bundling-focused, then added `validate`/`list`/`show` workflow;
- frontmatter parsing/conformance matured to real YAML parsing and shared conformance gating;
- markdown parsing in bundling became lenient to tolerate imperfect source docs;
- `.okfignore` added to allow selective exclusions without moving/deleting source files;
- single-file conversion (`convert_file`, `convert_content`) added for programmatic use without full directory bundling;
- `bundle()` internal logic refactored to use shared `_write_concept` helper;
- remote sharing added: `publish`/`clone` and remote `list`/`show` with `--remote`, backed by `okf-server`.

Evidence: `git log -- src/okf/core.py`, `git log -- src/okf/commands/bundle.py`, `git log -- src/okf/server/`, top-level `git log --oneline`.

## Extension points

- New local API function: add to `src/okf/api.py` with typed return, add tests in `tests/test_api.py`.
- New command: add thin wrapper in `src/okf/commands/`, register in `src/okf/cli.py`, add CLI tests in `tests/test_cli.py`.
- New conformance rule: implement in `check_conformance` (`src/okf/core.py`) and update API/validate expectations.
- New metadata field support: no schema migration required; parser already tolerates extra YAML keys.
- New server route: add to `src/okf/server/app.py`, add corresponding storage/auth support, add tests in `tests/server/test_server_api.py`.
- New remote command behavior: extend `src/okf/remote.py` and the relevant command wrapper; cover both success and HTTP error paths in `tests/test_cli.py`.
