# AGENTS.md — okf-cli contributor context

## Wiki

This repository has documentation located in the /wiki directory.

Start here:

- [Wiki quickstart](wiki/quickstart.md)

Wiki includes repository overview, architecture notes, workflows, domain concepts, operations, integrations, testing guidance, and source maps.

When working in this repository, read the Wiki quickstart first, then follow its links to the relevant architecture, workflow, domain, operation, and testing notes.

## Tech stack

Python 3.11+, **uv**, **typer**, **pyyaml**, **rich**, **pytest**, **ruff**, **hatchling** (build backend).

## Project layout

- `src/okf/cli.py` — Typer entrypoint and command registration
- `src/okf/api.py` — programmatic API; all business logic lives here
- `src/okf/core.py` — shared parsing, formatting, and conformance helpers
- `src/okf/commands/` — thin CLI wrappers (`bundle`, `list`, `read`, `validate`)
- `tests/` — `test_api.py`, `test_cli.py`, `test_core.py`
- `wiki/` — architecture, workflows, domain model, operations, testing notes
- `.github/workflows/test.yml` — CI (pytest + ruff on Python 3.11)

## Common tasks

```bash
uv sync
uv run pytest -q
uvx ruff check .
uvx ruff format .
```

Regenerate the example bundle:

```bash
uv run okf bundle example bundled --default-type reference --force
uv run okf validate bundled
```

Add a CLI command:

1. Create `src/okf/commands/<name>.py`.
1. Register it in `src/okf/cli.py` with `app.command()(fn)`.
1. Add tests in `tests/test_cli.py`.

Modify conformance behavior: edit `src/okf/core.py::check_conformance`, then ensure `validate`, `list`, and `read` behave consistently.

## Style guidelines

- Keep changes minimal; prefer stdlib/installed dependencies over new ones.
- Do not add abstractions "for later".
- Use `Path` from `pathlib`, not string path manipulation.
- Use `uv` for all package/runtime commands.
