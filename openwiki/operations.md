# Operations

## Local setup

Project targets Python 3.11+ with `uv` workflow.

```bash
uv sync
uv run okf --help
```

Packaging and runtime metadata: `pyproject.toml`.

Key points:

- CLI script entrypoint: `okf = "okf.cli:app"`
- Python API: `from okf.api import bundle, convert_file, convert_content, list_concepts, show_concept, validate`
- Runtime deps: `typer`, `pyyaml`, `rich`
- Dev deps include `pytest`, `ruff`

## Day-to-day commands

```bash
uv run pytest -q
uvx ruff check .
uvx ruff format .
```

For bundle smoke:

```bash
uv run okf bundle example --default-type reference --force
uv run okf validate example_knowledge_base
```

## CI/CD

GitHub Actions workflow: `.github/workflows/test.yml`

Pipeline:

1. checkout
1. setup `uv` with Python 3.11
1. `uv sync`
1. `uv run pytest -q`

No deploy pipeline in repo; CI currently focused on correctness tests.

## Repo artifacts and hygiene

- `example/` contains sample source markdown.
- Default output (`<input>_knowledge_base`) is git-ignored local artifact (`.gitignore`).

When changing command behavior, update sample docs/output only if behavior change is intentional and tested.

## Release-facing notes

Recent history shows production hardening and feature additions were shipped via small incremental commits (validate/list/read, YAML conformance gate, lenient parsing, `.okfignore`).

Operational takeaway: keep releases narrow and test-backed; avoid large unverified refactors.
