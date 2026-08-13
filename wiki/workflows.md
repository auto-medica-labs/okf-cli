# Workflows

## Core user workflow

### 1) Author plain markdown

Expected strict shape (best quality output):

```markdown
# Title

> One-line description

Body...
```

Authors may also put OKF frontmatter directly in the source markdown. The
bundler will detect, parse, and merge those fields instead of overwriting them:

```markdown
---
tags: [finance, revenue]
status: stable
verified:
  by: human:ahormati
  at: "2026-06-25T09:00:00Z"
---

# Title

> One-line description

Body...
```

Lenient fallback exists for imperfect files, but strict shape gives better metadata (`src/okf/core.py::parse_md`).

### 2) Bundle to OKF

```bash
uv run okf bundle <input-dir> [output-dir] [--default-type <type>] [--force] [--strict] [--dry-run]
# output-dir defaults to <input-dir>_knowledge_base
# --default-type defaults to input directory name
```

Important behavior:

- Root-level markdown uses input directory name as type if `--default-type` not specified.
- Reserved filenames skipped during bundling (`index.md`, `log.md`, `README.md`).
- `.okfignore` in input root can skip exact bundle-relative paths.
- Pre-existing YAML frontmatter in source files is merged into the output concept:
  `type`, `generated`, and `okf_version` are overwritten/dropped; everything else
  is preserved dynamically.
- `--strict` enforces strict OKF spec output: fails on broken local `.md` links, malformed input frontmatter, and skips `AGENTS.md` generation.
- `--dry-run` validates the source and reports warnings/errors without writing files or directories; existing output is left untouched even if `--force` is passed.
- `AGENTS.md` is generated at output root with navigation guidance (unless `--strict` or `--dry-run` is used).

Source: `src/okf/api.py`.

### 3) Validate output

```bash
uv run okf validate <output-dir>
```

Validate before downstream usage; this is same conformance gate used by reader commands.

Source: `src/okf/commands/validate.py`, `src/okf/core.py`.

### 4) Consume bundle

```bash
uv run okf list <output-dir>
uv run okf read <output-dir> <concept-id>
```

`list` prints a table of concepts (ID, type, title, description); `read` prints full concept markdown.

## Contributor workflow

### Change parsing/frontmatter/conformance rules

Start files:

- `src/okf/core.py`
- `tests/test_core.py`
- `tests/test_api.py` (validate/list/read tests)

Why: `check_conformance` and parsing helpers are shared dependencies across the API layer.

### Change bundling behavior

Start files:

- `src/okf/api.py` (all logic lives here)
- `tests/test_api.py` (TestBundle class)

Common pitfalls:

- keep root `index.md` generation behavior stable;
- keep reserved-name semantics (`README.md` reserved only for bundling phase);
- keep `.okfignore` exact-match behavior (no globs).

### Add new API function

1. Add function to `src/okf/api.py` with docstring and typed return.
1. Add tests in `tests/test_api.py`.
1. Optionally add CLI command: thin wrapper in `src/okf/commands/`, register in `src/okf/cli.py`, add CLI tests in `tests/test_cli.py`.

### Add new CLI command (without API change)

1. Add thin wrapper in `src/okf/commands/` that calls an `api.*` function.
1. Register in `src/okf/cli.py`.
1. Add CLI integration tests in `tests/test_cli.py`.

## Smoke workflow with repo fixtures

Repo contains:

- source sample: `example/`

Use to verify end-to-end behavior quickly:

```bash
uv run okf bundle example --default-type reference --force
uv run okf validate example_knowledge_base
uv run okf list example_knowledge_base
```

(Generated output directory is ignored by git for default `example_knowledge_base/`; see `.gitignore`.)
