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
- Python API: `from okf.api import bundle, convert_file, convert_content, list_concepts, reindex, show_concept, validate`
- Runtime deps: `typer`, `pyyaml`, `rich`
- Dev deps include `pytest`, `ruff`, and FastMCP for MCP integration tests
- Optional `mcp` extra installs FastMCP for `okf serve-mcp` (`uv sync --extra mcp`)

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

GitHub Actions workflows:

- `.github/workflows/test.yml` runs on pushes and pull requests: checkout, setup `uv` with Python 3.11, `uv sync`, Ruff checks, and `uv run pytest -q`.
- `.github/workflows/publish.yml` runs for tags matching `v0.*.*`. It verifies the tag is a plain `v0.x.x` version matching `project.version` in `pyproject.toml`, then runs `uv build` and `uv publish`.

### PyPI publishing setup

The publish workflow uses PyPI trusted publishing (GitHub Actions OIDC), so no long-lived PyPI API token is stored in GitHub. In the existing `okf-cli` project on PyPI, configure a trusted publisher with this repository's owner and name, workflow filename `publish.yml`, and no environment (unless the workflow is updated to use one).

To release, update `project.version` in `pyproject.toml`, commit that change, then push the matching tag, for example:

```bash
git tag v0.8.1
git push origin v0.8.1
```

## Repo artifacts and hygiene

- `example/` contains sample source markdown.
- Default output (`<input>_knowledge_base`) is git-ignored local artifact (`.gitignore`).

When changing command behavior, update sample docs/output only if behavior change is intentional and tested.

## Release-facing notes

Recent history shows production hardening and feature additions were shipped via small incremental commits (validate/list/read, YAML conformance gate, lenient parsing, `.okfignore`).

Operational takeaway: keep releases narrow and test-backed; avoid large unverified refactors.
