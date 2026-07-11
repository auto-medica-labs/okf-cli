# Architecture

## Runtime shape

`okf-cli` is intentionally small: Typer command layer + shared core helpers.

- CLI app creation and command registration: `src/okf/cli.py`
- Core format/parsing/conformance helpers: `src/okf/core.py`
- Command handlers:
  - `bundle`: `src/okf/commands/bundle.py`
  - `validate`: `src/okf/commands/validate.py`
  - `list`: `src/okf/commands/list.py`
  - `show`: `src/okf/commands/show.py`

Why this split exists: business rules live once in `core.py`, while command files mostly handle IO/CLI errors.

## Command execution flow

### `okf bundle`

1. Read source directory + optional `.okfignore` (`_load_okfignore`).
2. Walk `*.md`, skipping reserved names and ignored paths.
3. Parse each markdown file via `parse_md` (strict first, lenient fallback).
4. Build YAML frontmatter via `build_frontmatter`.
5. Write transformed files and generate `index.md` per directory.

Source: `src/okf/commands/bundle.py`, `src/okf/core.py`.

### `okf validate`

1. Ensure target directory exists and has markdown files.
2. Call `check_conformance` once.
3. Print warnings/errors + summary, exit non-zero on errors.

Source: `src/okf/commands/validate.py`, `src/okf/core.py`.

### `okf list` and `okf show`

Both commands first run `check_conformance`. If directory is non-conformant, they refuse to proceed.

Reason: reading APIs should not return misleading data from broken bundles.

Source: `src/okf/commands/list.py`, `src/okf/commands/show.py`.

## Shared invariants

- Reserved name handling differs by phase:
  - Bundling phase skips `index.md`, `log.md`, `README.md` (`RESERVED`).
  - Spec-conformance phase reserves only `index.md`, `log.md` (`SPEC_RESERVED`).
- Non-UTF-8 markdown is a conformance error.
- `type` frontmatter is required and must be non-empty for non-reserved concept files.

Source: `src/okf/core.py`.

## Evolution notes (from git history)

Major behavior shifts:
- project started bundling-focused, then added `validate`/`list`/`show` workflow;
- frontmatter parsing/conformance matured to real YAML parsing and shared conformance gating;
- markdown parsing in bundling became lenient to tolerate imperfect source docs;
- `.okfignore` added to allow selective exclusions without moving/deleting source files.

Evidence: `git log -- src/okf/core.py`, `git log -- src/okf/commands/bundle.py`, top-level `git log --oneline`.

## Extension points

- New command: add `src/okf/commands/<name>.py`, register in `src/okf/cli.py`, add CLI tests under `tests/cli/`.
- New conformance rule: implement in `check_conformance` (`src/okf/core.py`) and update validate/list/show expectations.
- New metadata field support: no schema migration required; parser already tolerates extra YAML keys.
