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

Implementation: `parse_frontmatter`, `check_conformance` in `src/okf/core.py`.

### Concept ID

Bundle-relative path without `.md` suffix.

- Example: `tables/orders.md` -> `tables/orders`.

Implementation: `src/okf/commands/list.py`, `src/okf/commands/show.py`.

### Reserved filenames

Two rule sets:

- Bundling input skip set: `index.md`, `log.md`, `README.md` (`RESERVED`)
- Spec reserved set: `index.md`, `log.md` (`SPEC_RESERVED`)

Why dual sets: raw input dirs often include README-like repo artifacts; spec-level bundle reading should only reserve spec names.

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

## `.okfignore` model (bundle-only)

- file location: `<input-dir>/.okfignore`
- syntax: one exact bundle-relative markdown path per line
- ignores blank lines and `#` comments
- no glob/negation semantics
- non-UTF-8 `.okfignore` fails bundling

Source: `_load_okfignore` in `src/okf/commands/bundle.py`; example file: `example/.okfignore`.

## Conformance rules enforced

`check_conformance` enforces bundle constraints:

1. non-reserved markdown must have parseable YAML frontmatter;
1. non-reserved markdown must include non-empty string `type`;
1. `index.md` and `log.md` structure rules:
   - non-root `index.md` must not have frontmatter;
   - root `index.md` may have frontmatter only containing `okf_version`;
   - `log.md` must not have frontmatter;
1. markdown files must be UTF-8.

Source: `src/okf/core.py`; behavior validated by `tests/test_core.py` and `tests/cli/test_validate.py`.
