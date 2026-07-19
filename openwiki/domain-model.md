# Domain model

## What repo models

This repository models an **OKF knowledge bundle pipeline**:

- input domain: plain markdown knowledge notes;
- canonical output domain: OKF concept documents with YAML frontmatter + directory `index.md` files;
- reader domain: concept ID listing and retrieval from conformant bundles.

Spec anchor: `OKF_SPEC.md`.

## Key entities

### Concept document

Markdown file with YAML frontmatter at top:

- required for non-reserved files: `type` (non-empty string)
- optional but common: `title`, `description`, `timestamp`, plus arbitrary producer-defined keys

Implementation: `parse_frontmatter`, `check_conformance` in `src/okf/core.py`. API returns parsed data via `ConceptContent` dataclass.

### Concept ID

Bundle-relative path without `.md` suffix.

- Example: `tables/orders.md` -> `tables/orders`.

Implementation: `api.list_concepts()`, `api.show_concept()` in `src/okf/api.py`.

### Result types (API)

`src/okf/api.py` defines typed return values:

- `BundleResult` — `files_written`, `output_dir`, `warnings`, `errors`
- `ValidateResult` — `total_files`, `errors`, `warnings`, `ok` (property)
- `ConceptContent` — `frontmatter` (dict), `body`, `raw`

### Reserved filenames

Two rule sets:

- Bundling input skip set: `index.md`, `log.md`, `README.md` (`RESERVED`)
- Spec reserved set: `index.md`, `log.md`, `agents.md` (`SPEC_RESERVED`)

Why dual sets: raw input dirs often include README-like repo artifacts; spec-level bundle reading should only reserve spec names plus `agents.md` (generated at bundle root, never a concept).

Implementation: `src/okf/core.py` + command logic.

## Parsing rules (bundle input)

`parse_md` tries strict parse then lenient fallback.

Strict (`_parse_strict`):

1. first line must be `# Title`
1. then a `>` description block
1. remaining content is body

Lenient (`_parse_lenient`):

- title from line 1 only if present;
- description synthesized from first 80 chars of collapsed body;
- never raises errors.

Why it exists: tolerate real-world docs that are not perfectly formatted while still producing usable bundles.

Source: `src/okf/core.py`.

## Link checking (bundle-only)

`bundle` scans markdown body links for local `.md` targets before writing output.

- `_iter_links(text)` extracts `[text](target)` via regex.
- `_resolve_md_target(current_rel, raw_target)` resolves to a bundle-relative POSIX path.
- Ignored: external URLs (`https:`, `mailto:`), fragment-only links (`#section`), directory links, non-`.md` targets.
- Default mode: warnings for missing targets or targets resolving outside bundle.
- `--strict`: turns warnings into fatal exit and skips `AGENTS.md` generation.
- Generated `index.md` files count as valid link targets.

Source: `src/okf/api.py` (`_iter_links`, `_resolve_md_target`).

## `.okfignore` model (bundle-only)

- file location: `<input-dir>/.okfignore`
- syntax: one exact bundle-relative markdown path per line
- ignores blank lines and `#` comments
- no glob/negation semantics
- non-UTF-8 `.okfignore` fails bundling

Source: `_load_okfignore` in `src/okf/api.py`; example file: `example/.okfignore`.

## Bundle output artifacts

Each bundle run produces:

- concept `.md` files with YAML frontmatter
- `index.md` per directory listing contents and subdirs
- `AGENTS.md` at output root: navigation guide for AI agents and humans (references `index.md`, explains frontmatter and cross-links); omitted in `--strict` mode

Source: `src/okf/api.py` (`_write_concept`, `_generate_indexes`, `bundle`).

## Conformance rules enforced

`check_conformance` enforces bundle constraints:

1. non-reserved markdown must have parseable YAML frontmatter;
1. non-reserved markdown must include non-empty string `type`;
1. `agents.md` is skipped entirely (no frontmatter/validation);
1. `index.md` and `log.md` structure rules:
   - non-root `index.md` must not have frontmatter;
   - root `index.md` may have frontmatter only containing `okf_version`;
   - `log.md` must not have frontmatter;
1. markdown files must be UTF-8.

Source: `src/okf/core.py`; behavior validated by `tests/test_api.py` (`TestValidate`) and `tests/test_cli.py`.
