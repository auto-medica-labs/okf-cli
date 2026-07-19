# Operations

## Local setup

Project targets Python 3.11+ with `uv` workflow.

```bash
uv sync              # local CLI only
uv sync --all-extras # include okf-server dependencies
uv run okf --help
uv run okf-server --help
```

Packaging and runtime metadata: `pyproject.toml`.

Key points:

- CLI script entrypoints: `okf = "okf.cli:app"`, `okf-server = "okf.server.cli:app"`
- Python API: `from okf.api import bundle, list_concepts, show_concept, validate`
- Runtime deps: `typer`, `pyyaml`
- Server optional deps: `fastapi`, `python-multipart`, `uvicorn`, `httpx`
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
1. `uv sync --all-extras`
1. `uv run pytest -q`

No deploy pipeline in repo; CI currently focused on correctness tests. The `--all-extras` install ensures server tests and remote CLI tests have their dependencies.

## Docker

`Dockerfile` builds a production image with server dependencies:

```bash
docker build -t okf-server -f Dockerfile .
docker run -p 8080:8080 -v okf-data:/data okf-server
```

Inside the image:

- base: `python:3.11-slim-bookworm`
- `uv sync --frozen --all-extras --no-dev`
- default CMD runs `okf-server serve` on `0.0.0.0:8080` with store and database under `/data`.

Source: `Dockerfile`, `.dockerignore`.

## Smoke testing

`scripts/smoke.sh` exercises the full Docker-based server cycle:

- build the server image
- create a tiny OKF bundle
- start a container
- register a user
- publish, remote list, remote show, clone
- verify cloned contents

Run locally when changing server, remote, or Docker code:

```bash
bash scripts/smoke.sh
```

## Environment variables

Remote commands read:

- `OKF_URL` — server base URL (overridden by `--url`).
- `OKF_TOKEN` — bearer token for authenticated publish/list/show (overridden by `--token`).

## Repo artifacts and hygiene

- `example/` contains sample source markdown.
- Default output (`<input>_knowledge_base`) is git-ignored local artifact (`.gitignore`).
- `bundled/`, `dist/`, `*.tar.gz`, and local store paths are also git-ignored.

When changing command behavior, update sample docs/output only if behavior change is intentional and tested.

## Release-facing notes

Recent history shows production hardening and feature additions were shipped via small incremental commits (validate/list/show, YAML conformance gate, lenient parsing, `.okfignore`, remote sharing, okf-server).

Operational takeaway: keep releases narrow and test-backed; avoid large unverified refactors.
