# AGENTS.md — okf-cli contributor context

This file is for AI agents (and humans) picking up work on `okf-cli`.

## OpenWiki (read first)

This repository has documentation in `openwiki/`.

Start here:

- [OpenWiki quickstart](openwiki/quickstart.md)

Then follow links to architecture, workflows, domain model, operations, and testing notes relevant to task.

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
│   └── commands/
│       ├── bundle.py        # thin wrapper → api.bundle()
│       ├── list.py          # thin wrapper → api.list_concepts()
│       ├── read.py          # thin wrapper → api.show_concept()
│       └── validate.py      # thin wrapper → api.validate()
└── tests/
    ├── test_api.py          # API unit/integration tests
    ├── test_cli.py          # CLI exit code/error message tests
    └── test_core.py         # core helper unit tests
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
