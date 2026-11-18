# Architecture

## Runtime shape

`okf-cli` has a three-layer architecture:

- **CLI layer** (`src/okf/cli.py`) — Typer app creation, command registration, `--version` callback.
- **API layer** (`src/okf/api.py`) — programmatic Python functions, all business logic lives here.
- **Core layer** (`src/okf/core.py`) — shared parsing, formatting, conformance helpers.
- **Command wrappers** (`src/okf/commands/`) — thin IO/error bridges from CLI args to API calls. `serve_mcp.py` is the optional FastMCP adapter for read-only MCP access over Streamable HTTP.

Why this split: the API layer is the canonical home for all logic. Commands handle only Typer argument parsing, error display, and exit codes. `core.py` holds pure parsing / formatting / conformance logic, but also instantiates shared rich `Console` singletons at import for output (used by `cli.py` and `commands/*`).

## Key modules

### `src/okf/api.py` — programmatic API

Public functions and return types:

| Function                                                                 | Returns          | Key behavior                                                                                                                   |
| ------------------------------------------------------------------------ | ---------------- | ------------------------------------------------------------------------------------------------------------------------------ |
| `bundle(input_dir, output_dir, *, default_type, force, strict, dry_run)` | `BundleResult`   | Full bundle pipeline with link checking, `.okfignore`, `AGENTS.md` generation; `dry_run` validates and reports without writing |
| `convert_file(input_file, output_file, type_)`                           | `BundleResult`   | Convert single markdown file to OKF concept (`generated` from mtime)                                                           |
| `convert_content(content, output_file, type_)`                           | `BundleResult`   | Convert raw markdown string to OKF concept (no `generated` block)                                                              |
| `list_concepts(bundle_dir)`                                              | `list[str]`      | Conformance-gated concept ID listing                                                                                           |
| `list_entries(bundle_dir)`                                               | `list[dict]`     | Conformance-gated concept metadata (id, type, title, description)                                                              |
| `show_concept(bundle_dir, concept_id, *, section)`                       | `ConceptContent` | Conformance-gated concept read; `section` returns one heading's section as `body`                                              |
| `search(bundle_dir, query, *, type_, filters, limit)`                    | `list[dict]`     | One-shot `Bundle.search`; best match first                                                                                     |
| `write_concept(bundle_dir, concept_id, frontmatter, body)`               | `Path`           | Atomic write of one concept exactly as given (keeps `type`/`generated`); validates first; does not touch `index.md`            |
| `validate_concept(frontmatter, body)`                                    | `ValidateResult` | §11 check of one concept, including a YAML round trip of the frontmatter                                                       |
| `reindex(bundle_dir)`                                                    | `BundleResult`   | Rebuild `index.md` from disk; stale indexes are emptied, never deleted; `files_written` counts files written, `warnings` names emptied indexes |
| `validate(bundle_dir)`                                                   | `ValidateResult` | Conformance check with `.ok` property                                                                                          |

`Bundle` is the loaded form for callers that read a bundle repeatedly (programs, the MCP server):

| Member                                    | Behavior                                                                                                                |
| ----------------------------------------- | ----------------------------------------------------------------------------------------------------------------------- |
| `Bundle.open(bundle_dir)`                 | One conformance pass; indexes every concept's frontmatter in memory. Raises `ValueError` if non-conformant.              |
| `refresh()`                               | Re-reads only files added/removed/changed (stamp = mtime, size, inode); failure leaves the previous state untouched; returns whether anything changed |
| `ids()`, `entries()`                      | Same results and order as `list_concepts` / `list_entries`, served from memory                                            |
| `search(query, *, type_, filters, limit)` | Word-substring match over ID + frontmatter strings (nested values included; dates/numbers match as text; `generated`/`verified` excluded); ranks by words matched, then field weight (ID/title > tags/description > others); exact whole-value match bonus. `type_` and `filters` compare case-insensitively |
| `read(concept_id, *, section)`            | Reads the file from disk; accepts link-style IDs (`/a/b.md`); sets normalized `id` and `links` (bundle-local concept links as `{target, id, exists}`, deduplicated, reserved/outside targets omitted) |
| `listdir(directory)`                      | `{path, concepts, directories}` from memory, bundle-relative; dot segments normalized; escapes rejected              |
| `browse(directory)`                       | The directory's `index.md` when present, else the same listing generated from memory                                    |
| `write(concept_id, frontmatter, body)`    | `write_concept` then `refresh()`                                                                                        |

`list_concepts`, `list_entries`, `show_concept` and `search` are thin wrappers that open a `Bundle` per call.

Internal helpers (not public API): `_iter_links`, `_resolve_md_target`, `_load_okfignore`, `_is_ignored`, `_generate_indexes`, `_index_texts`, `_merge_input_frontmatter`, `_write_concept`, `_concept_file`, `_section_lines`, `_search_document`.

### `src/okf/core.py` — shared utilities

- `RESERVED` — filenames `bundle` skips: `index.md`, `log.md`, `readme.md`.
- `SPEC_RESERVED` — spec-level reserved names: `index.md`, `log.md`, `agents.md`.
- `build_frontmatter(type_, title, description, generated, extras)` — YAML
  frontmatter rendered with `yaml.safe_dump`; `extras` are producer-defined
  keys preserved from input frontmatter.
- `parse_md(text)` — extracts title/description/body; strict first, lenient fallback.
- `parse_md_with_frontmatter(text, strict=False)` — parses a leading YAML
  frontmatter block, then extracts title/description/body from the remaining
  content; malformed frontmatter either falls back (normal) or raises (`strict`).
- `parse_frontmatter(text)` — parses YAML frontmatter, returns `None` for invalid.
- `dump_frontmatter(data)` — renders a frontmatter mapping as a `---` block,
  `type`/`title`/`description` first, other keys in the mapping's order.
- `check_file(rel, text)` — §11 rules for one file; returns problems (no path
  prefix) and the parsed frontmatter. Shared by `check_conformance`, `Bundle`
  and `validate_concept`.
- `check_conformance(directory)` — validates OKF v0.2 §11, returns `(errors, warnings)`.

### Command wrappers (`src/okf/commands/`)

Each file imports from `okf.api` and calls the corresponding function, translating exceptions to Typer exit codes. No business logic.

## Command execution flow

### `okf bundle` (via `api.bundle()`)

1. Read source directory + optional `.okfignore` (`_load_okfignore`).
1. Walk `*.md`, skipping reserved names and ignored paths.
1. Parse each markdown file via `parse_md_with_frontmatter` (strict first on the
   frontmatter block, then `parse_md` on the stripped body).
1. Scan markdown body links via `_iter_links` / `_resolve_md_target` — warns on missing or out-of-bundle targets; `--strict` makes these fatal (even during `--dry-run`).
1. If `dry_run=True`, skip all writes: no concept files, no `index.md` files, and no `AGENTS.md`. The result still reports planned `files_written` and any warnings/errors.
1. Merge input frontmatter with bundler-derived fields via `_merge_input_frontmatter`.
1. Build YAML frontmatter via `build_frontmatter`.
1. Write transformed files and generate `index.md` per directory.
1. Write `AGENTS.md` at output root with navigation guidance for the knowledge base (skipped when `--strict` is used).

### `okf validate` (via `api.validate()`)

1. Ensure target directory exists and has markdown files.
1. Call `check_conformance` once.
1. Return `ValidateResult` with file count, errors, and warnings.

### `okf reindex` (via `api.reindex()`)

1. Call `list_entries()` — which runs the conformance gate and raises `ValueError` on a non-conformant bundle.
1. Rebuild `(concept_id, metadata)` pairs from the parsed frontmatter.
1. Call `_generate_indexes(..., overwrite=True)` to rewrite every `index.md` from scratch.

`_generate_indexes` keeps any existing index file unless `overwrite=True`; `reindex()` is the only caller that opts in. Rewriting from scratch is what makes `reindex()` safe to run after concepts or directories were deleted: indexes that no concept feeds anymore are **emptied** in place (root index keeps its `okf_version` block; subdirectory indexes become empty files), the emptied paths are named in `result.warnings`, and `files_written` counts them. Files are never deleted. `bundle()` uses the non-overwriting path against a fresh staging directory. The run is idempotent: a second `reindex()` against a clean bundle reports no emptied files.

### `okf list` and `okf read` (via `api.list_entries()` / `api.show_concept()`)

`okf list` renders the metadata returned by `api.list_entries()` as a Rich table (ID, type, title, description). `okf read` looks up a single concept by ID via `api.show_concept()`.

Both reading paths open a `Bundle`, which runs conformance first. If the directory is non-conformant, they raise `ValueError`.

Reason: reading APIs should not return misleading data from broken bundles.

### `okf serve-mcp`

The command opens a `Bundle` once (refusing non-conformant bundles) and hands it to `_create_server`. Every tool (`list_concepts`, `search`, `browse`, `read_concept`) calls `refresh()` first, so files another process added, changed or removed are served on the next call. Tools are annotated `readOnlyHint`. `browse` returns `Bundle.listdir()` — bundle-relative concept IDs and directory paths agents can feed straight back to the tools. `read_concept` accepts `section` and returns the normalized `id` plus `links` resolved to concept IDs, so agents never resolve relative paths themselves. Server instructions are a fixed tool guide plus, when present, the bundle's `AGENTS.md` behind a note that maps its "read index.md" advice to `browse`. Dates and timestamps in frontmatter are returned as ISO strings. A bundle that breaks while served makes tool calls fail with a `ToolError` carrying the conformance message rather than serving stale data.

## Shared invariants

- Reserved name handling differs by phase:
  - Bundling phase skips `index.md`, `log.md`, `README.md` (`RESERVED`).
  - Spec-conformance phase reserves `index.md`, `log.md`, `agents.md` (`SPEC_RESERVED`). `agents.md` is reserved but skipped during conformance checks (not an error).
- `.okfignore` matching is exact-path or folder-prefix (`_is_ignored`); folder
  entries may be written as `dir/`, `dir/*`, or `dir/**` and all normalize to
  `dir/`.
- Non-UTF-8 markdown is a conformance error.
- `type` frontmatter is required and must be non-empty for non-reserved concept files.
- Bundling preserves arbitrary producer-defined frontmatter keys; only `type`,
  `generated`, and `okf_version` are overwritten or dropped.

Source: `src/okf/core.py` (constants), `src/okf/api.py` (enforcement).

## Evolution notes (from git history)

Major behavior shifts:

- project started bundling-focused, then added `validate`/`list`/`read` workflow;
- frontmatter parsing/conformance matured to real YAML parsing and shared conformance gating;
- markdown parsing in bundling became lenient to tolerate imperfect source docs;
- `.okfignore` added to allow selective exclusions without moving/deleting source files;
- single-file conversion (`convert_file`, `convert_content`) added for programmatic use without full directory bundling;
- `bundle()` internal logic refactored to use shared `_write_concept` helper.
- Bundler learned to detect and merge pre-existing YAML frontmatter in source
  markdown, preserving producer-defined fields while still setting `type` and
  `generated` itself.

Evidence: `git log -- src/okf/core.py`, `git log -- src/okf/commands/bundle.py`, top-level `git log --oneline`.

## Extension points

- New API function: add to `src/okf/api.py` with typed return, add tests in `tests/test_api.py`.
- New command: add thin wrapper in `src/okf/commands/`, register in `src/okf/cli.py`, add CLI tests in `tests/test_cli.py`.
- New conformance rule: implement in `check_file` (`src/okf/core.py`) so `check_conformance`, `Bundle` and `validate_concept` all enforce it; update API/validate expectations.
- New metadata field support: no schema migration required; parser already tolerates extra YAML keys.
