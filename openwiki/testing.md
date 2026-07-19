# Testing

## Test suite map

- API unit/integration tests: `tests/test_api.py`
  - `TestBundle` — bundling via `api.bundle()`, link checking, `.okfignore`, lenient parsing, `AGENTS.md` generation
  - `TestListConcepts` — listing via `api.list_concepts()`, reserved file handling
  - `TestShowConcept` — reading via `api.show_concept()`, path traversal guard
  - `TestValidate` — conformance checks via `api.validate()`, all §9 rule variants
  - `TestWorkflow` — cross-command pipeline (bundle → validate/list/show)
- Core unit tests: `tests/test_core.py`
  - parsing helpers (`parse_md`, `parse_frontmatter`)
  - frontmatter generation (`build_frontmatter`)
  - conformance engine (`check_conformance`)
- CLI integration tests: `tests/test_cli.py`
  - exit codes and error message formatting for all commands
  - Typer-specific behavior (argument parsing, `--force`, `--strict`)

## Run tests

```bash
uv run pytest -q
```

## Change-oriented guidance

### If editing `src/okf/api.py`

Run at minimum:

```bash
uv run pytest -q tests/test_api.py tests/test_cli.py
```

Reason: API functions are the business logic; CLI tests verify the wrapper layer.

### If editing `src/okf/core.py`

Run at minimum:

```bash
uv run pytest -q tests/test_core.py tests/test_api.py
```

Reason: core helpers are used by the API layer.

### If editing command wrappers (`src/okf/commands/*.py`)

Run at minimum:

```bash
uv run pytest -q tests/test_cli.py
```

Reason: commands are thin wrappers — CLI tests verify exit codes and error output.

### If editing CLI registration (`src/okf/cli.py`)

Run full suite:

```bash
uv run pytest -q
```

## Behaviors with dedicated regression coverage

- `.okfignore` parsing and skip semantics, including non-UTF-8 failure.
- Lenient parsing fallback when strict markdown format is missing.
- Reserved filename differences between bundling and spec conformance.
- Root `index.md` special allowance for `okf_version` only.
- `list`/`show` hard failure on non-conformant bundles.
- `show` path traversal guard.
- Link checking: `_resolve_md_target` path resolution, `--strict` fatal mode, missing/out-of-bundle targets.

Primary evidence: `tests/test_api.py`, `tests/test_core.py`, `tests/test_cli.py`.
