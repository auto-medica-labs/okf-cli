# AGENTS.md — okf-cli contributor context

This file is for AI agents (and humans) picking up work on `okf-cli`.

## OpenWiki

This repository has documentation located in the /openwiki directory.

Start here:

- [OpenWiki quickstart](openwiki/quickstart.md)

OpenWiki includes repository overview, architecture notes, workflows, domain concepts, operations, integrations, testing guidance, and source maps.

When working in this repository, read the OpenWiki quickstart first, then follow its links to the relevant architecture, workflow, domain, operation, and testing notes.

## Tech stack

- Python 3.11+
- Package/venv manager: **uv**
- CLI framework: **typer**
- YAML parsing: **pyyaml**
- Tests: **pytest**
- Lint/format: **ruff** (via `uvx ruff check .` / `uvx ruff format .`)
- Build: hatchling (configured in `pyproject.toml`)

Always use `uv` for dependency sync and running commands:

```bash
uv sync                  # install/sync deps
uv run pytest -q           # run tests
uv run okf --help          # run CLI
```

## Project layout

```
okf-cli
├── .github/workflows/test.yml # CI (pytest on 3.11)
├── OKF_SPEC.md              # OKF v0.1 specification
├── pyproject.toml           # project metadata + deps
├── uv.lock                  # uv lockfile
├── src/okf/
│   ├── cli.py               # Typer entrypoint, registers commands
│   ├── api.py               # programmatic Python API (all business logic)
│   ├── core.py              # shared parsing/formatting/conformance
│   ├── remote.py            # HTTP client helpers for remote commands
│   ├── commands/
│   │   ├── bundle.py        # thin wrapper → api.bundle()
│   │   ├── clone.py         # thin wrapper → remote clone
│   │   ├── list.py          # thin wrapper → api.list_concepts() or remote list
│   │   ├── publish.py       # thin wrapper → remote publish
│   │   ├── show.py          # thin wrapper → api.show_concept() or remote show
│   │   └── validate.py      # thin wrapper → api.validate()
│   └── server/              # okf-server FastAPI app, auth, storage
│       ├── app.py           # FastAPI route definitions
│       ├── auth.py          # SQLite-backed user/token store
│       ├── cli.py           # okf-server Typer entrypoint
│       ├── storage.py       # filesystem bundle store
│       └── _common.py       # slug validation, reserved usernames
└── tests/
    ├── test_api.py          # API unit/integration tests
    ├── test_cli.py          # CLI exit code/error message tests (includes remote)
    ├── test_core.py         # core helper unit tests
    └── server/              # server subsystem tests
        ├── test_auth.py     # user store tests
        ├── test_server_api.py  # FastAPI route tests
        └── test_storage.py  # FileStore tests
```

## Common tasks

### Regenerate the example bundle

```bash
uv run okf bundle example bundled --default-type reference --force
uv run okf validate bundled
```

`bundled/` is gitignored. Use `--force` for re-runs.

### Add a new CLI command

1. Create `src/okf/commands/<name>.py` with a function taking `typer` arguments.
1. Import and register it in `src/okf/cli.py` with `app.command()(fn)`.
1. Add tests in `tests/test_cli.py`.

### Modify conformance behavior

Update `check_conformance()` in `src/okf/core.py`, then ensure `validate`, `list`, and `show` all behave consistently.

## Style guidelines

- Keep changes minimal. Prefer stdlib/installed dependencies over new ones.
- Do not add abstractions "for later".
- Use `Path` from `pathlib`, not string path manipulation.
- Use `uv` for all package/runtime commands.
