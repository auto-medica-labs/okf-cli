# Workflows

## Core user workflow

### 1) Author plain markdown

Expected strict shape (best quality output):

```markdown
# Title

> One-line description

Body...
```

Lenient fallback exists for imperfect files, but strict shape gives better metadata (`src/okf/core.py::parse_md`).

### 2) Bundle to OKF

```bash
uv run okf bundle <input-dir> <output-dir> --default-type reference --force
uv run okf bundle <input-dir> <output-dir> --default-type reference --force --strict-links
```

Important behavior:

- Root-level markdown requires `--default-type`, else skipped with warning.
- Reserved filenames skipped during bundling (`index.md`, `log.md`, `README.md`).
- `.okfignore` in input root can skip exact bundle-relative paths.
- `--strict-links` fails if any local `.md` link is missing or points outside bundle.
- `AGENTS.md` is generated at output root with navigation guidance.

Source: `src/okf/commands/bundle.py`.

### 3) Validate output

```bash
uv run okf validate <output-dir>
```

Validate before downstream usage; this is same conformance gate used by reader commands.

Source: `src/okf/commands/validate.py`, `src/okf/core.py`.

### 4) Consume bundle

```bash
uv run okf list <output-dir>
uv run okf show <output-dir> <concept-id>
```

`list` returns concept IDs; `show` prints full concept markdown.

## Contributor workflow

### Change parsing/frontmatter/conformance rules

Start files:

- `src/okf/core.py`
- `tests/test_core.py`
- `tests/cli/test_validate.py`
- `tests/cli/test_list.py`
- `tests/cli/test_show.py`

Why: `check_conformance` and parsing helpers are shared dependencies across commands.

### Change bundling behavior

Start files:

- `src/okf/commands/bundle.py`
- `tests/cli/test_bundle.py`

Common pitfalls:

- keep root `index.md` generation behavior stable;
- keep reserved-name semantics (`README.md` reserved only for bundling phase);
- keep `.okfignore` exact-match behavior (no globs).

### Add new CLI command

1. Add command implementation under `src/okf/commands/`.
1. Register in `src/okf/cli.py`.
1. Add CLI integration tests.
1. Update `README.md` and OpenWiki quickstart if UX changes.

## Smoke workflow with repo fixtures

Repo contains:

- source sample: `example/`
- generated sample: `bundled-smoke/`

Use to verify end-to-end behavior quickly:

```bash
uv run okf bundle example bundled-smoke --default-type reference --force
uv run okf validate bundled-smoke
uv run okf list bundled-smoke
```

(Generated output directory is ignored by git for default `bundled/`; see `.gitignore`.)
