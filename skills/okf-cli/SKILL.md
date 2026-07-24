---
name: okf-cli
description: >
  User manual and reference for the okf CLI tool (Open Knowledge Format).
  Use for questions about bundling plain markdown into OKF knowledge bases,
  validating OKF bundles, listing concepts, reading concepts, CLI options,
  and end-user workflows. Not for okf-cli source development.
license: MIT
---

# okf CLI User Manual

`okf` converts plain markdown directories into **Open Knowledge Format (OKF)** bundles — structured knowledge bases with YAML frontmatter, auto-generated indexes, and cross-link support.

## Installation

Requires Python 3.11+ and `uv`:

```bash
uv tool install okf-cli
okf --version
```

Upgrade:

```bash
uv tool upgrade okf-cli
```

## CLI overview

```bash
okf [OPTIONS] COMMAND [ARGS]...
```

Global options:

| Option                 | Description                              |
| ---------------------- | ---------------------------------------- |
| `--version`            | Show version and exit                    |
| `--install-completion` | Install completion for the current shell |
| `--show-completion`    | Print completion script to copy          |
| `--help`               | Show help                                |

## Commands

### `okf bundle`

Convert a directory of plain markdown into an OKF bundle.

```bash
okf bundle <input-dir> [output-dir] [OPTIONS]
```

Arguments:

| Argument     | Description                                              |
| ------------ | -------------------------------------------------------- |
| `input-dir`  | Source directory of plain markdown files                 |
| `output-dir` | Target directory (default: `<input-dir>_knowledge_base`) |

Options:

| Option                  | Description                                                       |
| ----------------------- | ----------------------------------------------------------------- |
| `--default-type <type>` | Concept type for root-level files (default: input directory name) |
| `--force`, `-f`         | Overwrite output directory if it exists                           |
| `--strict`              | Fail on broken local `.md` links and skip `AGENTS.md` generation  |

Examples:

```bash
okf bundle my-docs --default-type reference
okf bundle my-docs out --default-type reference --force
okf bundle my-docs --default-type reference --strict
```

Behavior:

- Skips `index.md`, `log.md`, `README.md` during input scanning.
- Reads `.okfignore` in the input root for exact bundle-relative paths to skip.
- Generates `index.md` in every directory containing concepts or subdirectories.
- Generates `AGENTS.md` at bundle root with navigation guidance (skipped with `--strict`).
- Warns about broken local `.md` links; `--strict` turns warnings into fatal errors.

### `okf validate`

Check whether a directory conforms to the OKF specification.

```bash
okf validate <directory>
```

Reports errors and warnings per file. Exits non-zero on conformance failures.

### `okf list`

List all concept IDs in a conformant OKF bundle.

```bash
okf list <directory>
```

Concept IDs are bundle-relative paths without the `.md` suffix, e.g. `tables/orders`.

### `okf read`

Print a concept's full contents by concept ID.

```bash
okf read <directory> <concept-id>
```

Example:

```bash
okf read my-docs_knowledge_base tables/orders
```

## Plain markdown input format

Best-quality input uses strict shape:

```markdown
# Clear Concept Title

> One-sentence summary of this concept.

Body content with useful context, structure, examples, or schema.
```

Lenient fallback exists for imperfect files, but metadata quality may be lower.

Rules:

- First line: `# Title`
- Next block: `>` description (concise, factual)
- Directory name becomes the concept `type`: `tables/orders.md` → type `tables`
- Root-level files use `--default-type`, or the input directory name if omitted
- Do not add frontmatter to source files — `okf bundle` generates it
- Avoid creating `index.md`, `log.md`, or `README.md` as source concepts (reserved)

## Typical workflow

```bash
# 1. Bundle
okf bundle my-notes --default-type reference --force

# 2. Validate
okf validate my-notes_knowledge_base

# 3. Explore
okf list my-notes_knowledge_base
okf read my-notes_knowledge_base some/concept
```

## `.okfignore`

Place in the input root to exclude markdown files. Syntax:

```text
# comments and blank lines allowed
private-notes.md
drafts/old-post.md
```

Entries are exact bundle-relative paths. No glob or negation support.

## Reserved filenames

These files are never treated as concepts:

- `index.md` — generated directory listings
- `log.md` — changelog / activity log
- `agents.md` — agent navigation guidance (generated)
- `README.md` — skipped only during bundling input

## Strict mode

Use `--strict` when you want:

- Broken local `.md` links to fail the bundle
- No `AGENTS.md` generated

Example:

```bash
okf bundle my-docs --default-type reference --strict
```

## Tips

- Always run `okf validate` before consuming a bundle with `list` or `read`; those commands refuse non-conformant bundles.
- Use `--force` when regenerating bundles; output directories are not overwritten by default.
- Root-level markdown files get their `type` from the input directory name unless `--default-type` is set.
- Subdirectory markdown files get their `type` from the subdirectory name.
