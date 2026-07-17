# Workflows

## Core user workflow

### 1) Author plain markdown

Expected strict shape (best quality output):

```markdown
# Title

> One-line description

Body...
```

Lenient fallback exists for imperfect files, but strict shape gives better metadata (`src/okf/core.py::parse_md`).

### 2) Bundle to OKF

```bash
uv run okf bundle <input-dir> [output-dir] [--default-type <type>] [--force] [--strict]
# output-dir defaults to <input-dir>_knowledge_base
# --default-type defaults to input directory name
```

Important behavior:

- Root-level markdown uses input directory name as type if `--default-type` not specified.
- Reserved filenames skipped during bundling (`index.md`, `log.md`, `README.md`).
- `.okfignore` in input root can skip exact bundle-relative paths.
- `--strict` enforces strict OKF spec output: fails on broken local `.md` links and skips `AGENTS.md` generation.
- `AGENTS.md` is generated at output root with navigation guidance (unless `--strict` is used).

Source: `src/okf/commands/bundle.py`.

### 3) Validate output

```bash
uv run okf validate <output-dir>
```

Validate before downstream usage; this is same conformance gate used by reader commands.

Source: `src/okf/commands/validate.py`, `src/okf/core.py`.

### 4) Consume bundle

```bash
uv run okf list <output-dir>
uv run okf show <output-dir> <concept-id>
```

`list` returns concept IDs; `show` prints full concept markdown.

## Contributor workflow

### Change parsing/frontmatter/conformance rules

Start files:

- `src/okf/core.py`
- `tests/test_core.py`
- `tests/test_api.py` (validate/list/show tests)

Why: `check_conformance` and parsing helpers are shared dependencies across the API layer.

### Change bundling behavior

Start files:

- `src/okf/api.py` (all logic lives here)
- `tests/test_api.py` (TestBundle class)

Common pitfalls:

- keep root `index.md` generation behavior stable;
- keep reserved-name semantics (`README.md` reserved only for bundling phase);
- keep `.okfignore` exact-match behavior (no globs).

### Add new API function

1. Add function to `src/okf/api.py` with docstring and typed return.
1. Add tests in `tests/test_api.py`.
1. Optionally add CLI command: thin wrapper in `src/okf/commands/`, register in `src/okf/cli.py`, add CLI tests in `tests/test_cli.py`.

### Add new CLI command (without API change)

1. Add thin wrapper in `src/okf/commands/` that calls an `api.*` function.
1. Register in `src/okf/cli.py`.
1. Add CLI integration tests in `tests/test_cli.py`.

## Remote sharing workflow

1. **Install server extras**:

   ```bash
   uv sync --all-extras
   ```

1. **Start an okf-server** (local or hosted):

   ```bash
   okf-server serve --store ~/.okf/store --database ~/.okf/server.db
   ```

1. **Get a token**:

   ```bash
   curl -X POST http://localhost:8080/api/v1/auth/register \
     -H "Content-Type: application/json" \
     -d '{"username":"alice","password":"secret"}'
   ```

   Store the returned bearer token in `OKF_TOKEN`.

1. **Publish a local bundle**:

   ```bash
   uv run okf publish example_knowledge_base mybundle --token "$OKF_TOKEN"
   # or rely on OKF_TOKEN env var
   ```

1. **List and read remote concepts**:

   ```bash
   uv run okf list --remote alice/mybundle
   uv run okf show --remote alice/mybundle --concept-id tables/customers
   ```

1. **Clone a published bundle**:

   ```bash
   uv run okf clone alice/mybundle
   ```

Server URL resolution order: explicit `--url` → `OKF_URL` environment variable → default `https://okf.com`.

Source: `src/okf/remote.py`, `src/okf/server/app.py`.

## Server workflow

Run the server for local development:

```bash
uv sync --all-extras
okf-server serve --host 0.0.0.0 --port 8080 --store ~/.okf/store --database ~/.okf/server.db
```

Key options:

| Option | Default | Purpose |
| ------ | ------- | ------- |
| `--host` | `0.0.0.0` | Bind address |
| `--port` | `8080` | Listen port |
| `--store` | `~/.okf/store` | Filesystem root for published bundles |
| `--database` | `~/.okf/server.db` | SQLite database for user credentials/tokens |
| `--allow-register` | `true` | Allow new user registrations |

For containerized deployment the `Dockerfile` sets `--store /data/store --database /data/server.db` and exposes `8080`; mount `/data` as a volume.

Source: `src/okf/server/cli.py`, `Dockerfile`.

## Smoke workflow with repo fixtures

Repo contains:

- source sample: `example/`

Use to verify end-to-end behavior quickly:

```bash
uv run okf bundle example --default-type reference --force
uv run okf validate example_knowledge_base
uv run okf list example_knowledge_base
```

(Generated output directory is ignored by git for default `example_knowledge_base/`; see `.gitignore`.)

There is also a Docker-based smoke test for the full publish/list/show/clone cycle: `scripts/smoke.sh`.
