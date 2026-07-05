# AGENTS.md — okf-cli contributor context

This file is for AI agents (and humans) picking up work on `okf-cli`.

## Project overview

`okf-cli` is a Python CLI that converts plain markdown directories into
[Open Knowledge Format (OKF)](OKF_SPEC.md) bundles and provides tools to
inspect/validate them.

- **Input:** plain `.md` files starting with `# Title` and a `>` description block.
- **Output:** OKF-conformant markdown with YAML frontmatter, per-directory `index.md` files.
- **Operations:** `bundle`, `list`, `show`, `validate`.

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
uv run okf bundle example bundled --default-type reference --force
```

## Project layout

```
okf-cli
├── .github/workflows/test.yml # CI (pytest on 3.11, 3.13)
├── OKF_SPEC.md              # OKF v0.1 specification
├── README.md                # user-facing docs
├── AGENTS.md                # this file
├── pyproject.toml           # project metadata + deps
├── uv.lock                  # uv lockfile
├── src/okf/
│   ├── cli.py               # Typer entrypoint, registers commands
│   ├── core.py              # shared parsing/formatting/conformance
│   └── commands/
│       ├── bundle.py        # plain markdown → OKF bundle
│       ├── list.py          # list concept IDs
│       ├── show.py          # print concept by ID
│       └── validate.py      # conformance check
└── tests/test_cli.py        # pytest suite
```

## Architecture

### `src/okf/cli.py`

- Creates the `typer.Typer` app named `okf`.
- Registers `bundle`, `list`, `show`, `validate`.
- No business logic here.

### `src/okf/core.py`

- `RESERVED` — filenames `bundle` skips: `index.md`, `log.md`, `README.md`.
- `SPEC_RESERVED` — filenames reserved by the OKF spec: `index.md`, `log.md`.
- `build_frontmatter(...)` — generates YAML frontmatter using JSON-escaped strings.
- `parse_md(...)` — extracts title/description/body from plain markdown.
- `parse_frontmatter(...)` — parses YAML frontmatter with `yaml.safe_load`.
- `check_conformance(...)` — validates a directory against OKF §9, returns `(errors, warnings)`. Now enforces:
  - §9.1: Non-reserved `.md` must have parseable frontmatter.
  - §9.2: Frontmatter must have non-empty `type`.
  - §9.3: `index.md` must not contain frontmatter (§6), except root `index.md` may have only `okf_version` (§11). `log.md` must not contain frontmatter (§7).
  - Non-UTF-8 files are flagged as errors.

### Commands

| Command | Input expected | Behavior |
|---|---|---|
| `bundle` | non-conformant plain markdown dir | generates OKF bundle; skips `index.md`, `log.md`, `README.md` with warnings; root files need `--default-type`; requires `--force` to overwrite existing output |
| `list` | OKF-conformant bundle | prints concept IDs; exits 1 if dir is not conformant |
| `show` | OKF-conformant bundle | prints concept file by ID; exits 1 if dir is not conformant |
| `validate` | any directory | prints conformance errors and summary per §9 |

## Key conventions

### Reserved filenames

- `bundle` treats `index.md`, `log.md`, `README.md` as reserved because it
  often runs against raw repo directories that may contain these files.
- `list`, `show`, `validate` operate on already-conformant OKF bundles, so
  they only treat `index.md` and `log.md` as reserved per the spec.
- `README.md` can be a valid concept in an OKF bundle.

### OKF conformance (§9)

1. Every non-reserved `.md` must have parseable YAML frontmatter.
2. Every frontmatter must contain a non-empty `type` string.
3. Reserved filenames (`index.md`, `log.md`) follow structure per §6/§7 when present.
   - `index.md` must not contain frontmatter (§6), except root `index.md` may contain only `okf_version` (§11).
   - `log.md` must not contain frontmatter (§7).
4. All files must be valid UTF-8.

`check_conformance()` is the source of truth for this logic.

### Frontmatter

`build_frontmatter()` outputs JSON-escaped YAML values, e.g.:

```yaml
---
type: "tables"
title: "Customer Orders"
---
```

`parse_frontmatter()` uses `yaml.safe_load()` and returns `None` for missing,
malformed, or non-dict frontmatter.

## Testing

Run the full suite before finishing:

```bash
uv run pytest -q
```

Add tests for new behavior in `tests/test_cli.py`. Existing patterns:

- Unit tests for `core.py` helpers.
- CLI integration tests using `typer.testing.CliRunner` and `tmp_path`.
- Conformance tests for `validate`, `list`, `show`.

## Common tasks

### Regenerate the example bundle

```bash
uv run okf bundle example bundled --default-type reference --force
uv run okf validate bundled
uv run okf list bundled
```

`bundled/` is gitignored; it is only a local artifact. Use `--force` for re-runs.

### Add a new CLI command

1. Create `src/okf/commands/<name>.py` with a function taking `typer` arguments.
2. Import and register it in `src/okf/cli.py` with `app.command()(fn)` or
   `app.command("alias")(fn)`.
3. Add tests in `tests/test_cli.py`.

### Modify conformance behavior

Update `check_conformance()` in `src/okf/core.py`, then ensure
`validate`, `list`, and `show` all behave consistently.

## Style guidelines

- Keep changes minimal. Prefer stdlib/installed dependencies over new ones.
- Do not add abstractions "for later".
- Use `Path` from `pathlib`, not string path manipulation.
- Use `uv` for all package/runtime commands.
