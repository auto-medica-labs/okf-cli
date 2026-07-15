# Architecture

## Runtime shape

`okf-cli` has a three-layer architecture:

- **CLI layer** (`src/okf/cli.py`) — Typer app creation, command registration, `--version` callback.
- **API layer** (`src/okf/api.py`) — programmatic Python functions, all business logic lives here.
- **Core layer** (`src/okf/core.py`) — shared parsing, formatting, conformance helpers.
- **Command wrappers** (`src/okf/commands/`) — thin IO/error bridges from CLI args to API calls.

Why this split: the API layer is the canonical home for all logic. Commands handle only Typer argument parsing, error display, and exit codes. `core.py` is pure utility with no side effects.

## Key modules

### `src/okf/api.py` — programmatic API

Public functions and return types:

| Function | Returns | Key behavior |
|---|---|---|
| `bundle(input_dir, output_dir, ...)` | `BundleResult` | Full bundle pipeline with link checking, `.okfignore`, `AGENTS.md` generation |
| `list_concepts(bundle_dir)` | `list[str]` | Conformance-gated concept ID listing |
| `show_concept(bundle_dir, concept_id)` | `ConceptContent` | Conformance-gated concept read with path traversal guard |
| `validate(bundle_dir)` | `ValidateResult` | Conformance check with `.ok` property |

Internal helpers (not public API): `_iter_links`, `_resolve_md_target`, `_load_okfignore`, `_generate_indexes`.

### `src/okf/core.py` — shared utilities

- `RESERVED` — filenames `bundle` skips: `index.md`, `log.md`, `readme.md`.
- `SPEC_RESERVED` — spec-level reserved names: `index.md`, `log.md`, `agents.md`.
- `build_frontmatter(type_, title, description, timestamp)` — YAML frontmatter via JSON-escaped values.
- `parse_md(text)` — extracts title/description/body; strict first, lenient fallback.
- `parse_frontmatter(text)` — parses YAML frontmatter, returns `None` for invalid.
- `check_conformance(directory)` — validates OKF §9, returns `(errors, warnings)`.

### Command wrappers (`src/okf/commands/`)

Each file imports from `okf.api` and calls the corresponding function, translating exceptions to Typer exit codes. No business logic.

## Command execution flow

### `okf bundle` (via `api.bundle()`)

1. Read source directory + optional `.okfignore` (`_load_okfignore`).
1. Walk `*.md`, skipping reserved names and ignored paths.
1. Parse each markdown file via `parse_md` (strict first, lenient fallback).
1. Scan markdown body links via `_iter_links` / `_resolve_md_target` — warns on missing or out-of-bundle targets; `--strict-links` makes these fatal.
1. Build YAML frontmatter via `build_frontmatter`.
1. Write transformed files and generate `index.md` per directory.
1. Write `AGENTS.md` at output root with navigation guidance for the knowledge base.

### `okf validate` (via `api.validate()`)

1. Ensure target directory exists and has markdown files.
1. Call `check_conformance` once.
1. Return `ValidateResult` with file count, errors, and warnings.

### `okf list` and `okf show` (via `api.list_concepts()` / `api.show_concept()`)

Both functions first run `check_conformance`. If directory is non-conformant, they raise `ValueError`.

Reason: reading APIs should not return misleading data from broken bundles.

## Shared invariants

- Reserved name handling differs by phase:
  - Bundling phase skips `index.md`, `log.md`, `README.md` (`RESERVED`).
  - Spec-conformance phase reserves `index.md`, `log.md`, `agents.md` (`SPEC_RESERVED`). `agents.md` is reserved but skipped during conformance checks (not an error).
- Non-UTF-8 markdown is a conformance error.
- `type` frontmatter is required and must be non-empty for non-reserved concept files.

Source: `src/okf/core.py` (constants), `src/okf/api.py` (enforcement).

## Evolution notes (from git history)

Major behavior shifts:

- project started bundling-focused, then added `validate`/`list`/`show` workflow;
- frontmatter parsing/conformance matured to real YAML parsing and shared conformance gating;
- markdown parsing in bundling became lenient to tolerate imperfect source docs;
- `.okfignore` added to allow selective exclusions without moving/deleting source files;
- business logic extracted from commands into `src/okf/api.py` for programmatic use.

Evidence: `git log -- src/okf/core.py`, `git log -- src/okf/commands/bundle.py`, top-level `git log --oneline`.

## Extension points

- New API function: add to `src/okf/api.py` with typed return, add tests in `tests/test_api.py`.
- New command: add thin wrapper in `src/okf/commands/`, register in `src/okf/cli.py`, add CLI tests in `tests/test_cli.py`.
- New conformance rule: implement in `check_conformance` (`src/okf/core.py`) and update API/validate expectations.
- New metadata field support: no schema migration required; parser already tolerates extra YAML keys.
