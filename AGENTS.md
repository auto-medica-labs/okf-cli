# AGENTS.md — okf-cli contributor context

This file is for AI agents (and humans) picking up work on `okf-cli`.

## OpenWiki (read first)

This repository has docs in `openwiki/`.

Start here:

- [OpenWiki quickstart](openwiki/quickstart.md)

Then follow links to architecture, workflows, domain model, operations, and testing notes relevant to task.

## Project overview

`okf-cli` is a Python CLI that converts plain markdown directories into
[Open Knowledge Format (OKF)](OKF_SPEC.md) bundles and provides tools to
inspect/validate them.

- **Input:** plain `.md` files starting with `# Title` and a `>` description block.
  `bundle` also supports optional `.okfignore` in input root.
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
├── .github/workflows/test.yml # CI (pytest on 3.11)
├── OKF_SPEC.md              # OKF v0.1 specification
├── README.md                # user-facing docs
├── AGENTS.md                # this file
├── pyproject.toml           # project metadata + deps
├── uv.lock                  # uv lockfile
├── src/okf/
│   ├── cli.py               # Typer entrypoint, registers commands
│   ├── api.py               # programmatic Python API (all business logic)
│   ├── core.py              # shared parsing/formatting/conformance
│   └── commands/
│       ├── bundle.py        # thin wrapper → api.bundle()
│       ├── list.py          # thin wrapper → api.list_concepts()
│       ├── show.py          # thin wrapper → api.show_concept()
│       └── validate.py      # thin wrapper → api.validate()
└── tests/
    ├── test_api.py          # API unit/integration tests
    ├── test_cli.py          # CLI exit code/error message tests
    └── test_core.py         # core helper unit tests
```

## Architecture

### `src/okf/cli.py`

- Creates the `typer.Typer` app named `okf`.
- Registers `bundle`, `list`, `show`, `validate`.
- No business logic here.

### `src/okf/api.py` — programmatic Python API

- `bundle(input_dir, output_dir, ...)` → `BundleResult`
- `list_concepts(bundle_dir)` → `list[str]`
- `show_concept(bundle_dir, concept_id)` → `ConceptContent`
- `validate(bundle_dir)` → `ValidateResult`
- All business logic lives here. Commands are thin wrappers.

### `src/okf/core.py`

- `RESERVED` — filenames `bundle` skips: `index.md`, `log.md`, `README.md`.
- `SPEC_RESERVED` — filenames reserved by the OKF spec: `index.md`, `log.md`.
- `build_frontmatter(...)` — generates YAML frontmatter using JSON-escaped strings.
- `parse_md(...)` — extracts title/description/body from plain markdown. Tries strict format first (line 1 `# Title`, `>` block); falls back leniently (title from line 0 only, description from first 80 chars of body). Never raises.
- `parse_frontmatter(...)` — parses YAML frontmatter with `yaml.safe_load`.
- `check_conformance(...)` — validates a directory against OKF §9, returns `(errors, warnings)`. Now enforces:
  - §9.1: Non-reserved `.md` must have parseable frontmatter.
  - §9.2: Frontmatter must have non-empty `type`.
  - §9.3: `index.md` must not contain frontmatter (§6), except root `index.md` may have only `okf_version` (§11). `log.md` must not contain frontmatter (§7).
  - Non-UTF-8 files are flagged as errors.

### Commands (thin wrappers around API)

| Command    | API function          | Input expected                    | Behavior                                                                                                |
| ---------- | --------------------- | --------------------------------- | ------------------------------------------------------------------------------------------------------- |
| `bundle`   | `api.bundle()`        | non-conformant plain markdown dir | generates OKF bundle; skips reserved files, `.okfignore` matches; link checking; `AGENTS.md` generation |
| `list`     | `api.list_concepts()` | OKF-conformant bundle             | prints concept IDs; exits 1 if not conformant                                                           |
| `show`     | `api.show_concept()`  | OKF-conformant bundle             | prints concept by ID; exits 1 if not conformant                                                         |
| `validate` | `api.validate()`      | any directory                     | prints conformance errors and summary per §9                                                            |

## Key conventions

### Reserved filenames

- `bundle` treats `index.md`, `log.md`, `README.md` as reserved because it
  often runs against raw repo directories that may contain these files.
- `list`, `show`, `validate` operate on already-conformant OKF bundles, so
  they only treat `index.md` and `log.md` as reserved per the spec.
- `README.md` can be a valid concept in an OKF bundle.

### Link checks in `bundle`

- `bundle` scans markdown body links for local `.md` targets.
- Supports relative (`./x.md`, `../x.md`) and bundle-root (`/dir/x.md`) links.
- Ignores external links (scheme URLs like `https:`/`mailto:`), fragment-only links, directory links, and non-`.md` targets.
- Default behavior: emit warnings for missing local targets or targets outside bundle.
- `--strict-links`: treat those link issues as fatal and exit non-zero.

### `.okfignore` (bundle only)

- Location: input directory root (`<input-dir>/.okfignore`).
- Format: one bundle-relative markdown path per line.
  - Example: `tables/orders.md`, `smoke-ignore.md`
- Blank lines and lines starting with `#` are ignored.
- Matching is exact path match only (no glob, no negation).
- If `.okfignore` is non-UTF-8, `bundle` exits with error.

### OKF conformance (§9)

1. Every non-reserved `.md` must have parseable YAML frontmatter.
1. Every frontmatter must contain a non-empty `type` string.
1. Reserved filenames (`index.md`, `log.md`) follow structure per §6/§7 when present.
   - `index.md` must not contain frontmatter (§6), except root `index.md` may contain only `okf_version` (§11).
   - `log.md` must not contain frontmatter (§7).
1. All files must be valid UTF-8.

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

Test files:

- `tests/test_api.py` — API functions (`bundle`, `list_concepts`, `show_concept`, `validate`), cross-command workflow tests.
- `tests/test_cli.py` — CLI exit codes and error message formatting only.
- `tests/test_core.py` — core helpers (`parse_md`, `parse_frontmatter`, `build_frontmatter`, `check_conformance`).

Add tests for API behavior in `tests/test_api.py`. Add tests for CLI-specific behavior in `tests/test_cli.py`.

## Common tasks

### Regenerate the example bundle

```bash
uv run okf bundle example bundled --default-type reference --force
uv run okf bundle example bundled --default-type reference --force --strict-links
uv run okf validate bundled
uv run okf list bundled
```

`bundled/` is gitignored; it is only a local artifact. Use `--force` for re-runs.
If `example/.okfignore` exists, `bundle` will skip matched files.

### Add a new CLI command

1. Create `src/okf/commands/<name>.py` with a function taking `typer` arguments.
1. Import and register it in `src/okf/cli.py` with `app.command()(fn)` or
   `app.command("alias")(fn)`.
1. Add tests in `tests/test_cli.py`.

### Modify conformance behavior

Update `check_conformance()` in `src/okf/core.py`, then ensure
`validate`, `list`, and `show` all behave consistently.

## Style guidelines

- Keep changes minimal. Prefer stdlib/installed dependencies over new ones.
- Do not add abstractions "for later".
- Use `Path` from `pathlib`, not string path manipulation.
- Use `uv` for all package/runtime commands.

## OpenWiki

This repository has documentation located in the /openwiki directory.

Start here:

- [OpenWiki quickstart](openwiki/quickstart.md)

OpenWiki includes repository overview, architecture notes, workflows, domain concepts, operations, integrations, testing guidance, and source maps.

When working in this repository, read the OpenWiki quickstart first, then follow its links to the relevant architecture, workflow, domain, operation, and testing notes.
