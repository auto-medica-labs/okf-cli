# okf-cli — Open Knowledge Format tooling

Converts plain markdown into [OKF](https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md)-conformant knowledge bundles. Domain experts write `# Title` then `> description` — `okf bundle` generates frontmatter, type, timestamps, and index files.

Also validates bundles and lists concept IDs for consumption by other tools.

## Install

```bash
uv tool install okf-cli
```

### Dev quickstart

```bash
uv sync
uv run okf --help
```

## Commands

### `okf bundle` — convert plain markdown to OKF bundle

```
okf bundle <input-dir> [output-dir] [--default-type <name>] [--force]
```

| Argument | Description |
|---|---|
| `input-dir` | Directory of plain `.md` files |
| `output-dir` | Target directory (default: `bundled`) |
| `--default-type` | Type for root-level files (skip root files if omitted) |
| `--force`, `-f` | Overwrite output directory if it exists |

```bash
okf bundle example --default-type reference  # first run → bundled/
okf bundle example --default-type reference --force  # re-run
cat bundled/tables/orders.md
```

### `okf list` — list concept IDs in a bundle

```
okf list <directory>
```

Prints concept IDs (bundle-relative path with `.md` stripped) for every
concept file in the bundle. Reserved filenames (`index.md`, `log.md`)
are excluded. `README.md` is not reserved by the OKF spec and is listed
as a concept if present.

Requires the directory to be a valid OKF bundle; fails if any
non-reserved `.md` is missing frontmatter or a non-empty `type`.

```bash
okf list bundled/
# datasets/sales
# playbooks/incident-response
# tables/orders
# …
```

Useful for piping OKF bundles into other tooling:

```bash
okf list bundled/ | xargs -I{} okf show bundled/ {}
```

### `okf show` — read a concept by ID

```
okf show <directory> <concept-id>
```

Prints the full contents (frontmatter + body) of a concept file.
Concept IDs are the bundle-relative path with `.md` stripped — exactly
as printed by `okf list`.

Requires the directory to be a valid OKF bundle.

```bash
okf show bundled/ tables/orders
# ---
# type: "tables"
# title: "Customer Orders"
# ...
```

Guards against path traversal and rejects reserved filenames.

### `okf validate` — check OKF conformance

```
okf validate <directory>
```

Checks OKF v0.1 §9 conformance:

- Every non-reserved `.md` has parseable YAML frontmatter with non-empty `type`.
- Reserved filenames (`index.md`, `log.md`) follow spec structure (§6/§7).
- Non-UTF-8 files are flagged.

```bash
okf validate bundled/
# 16 files: 16 ok
```

## Writing input files (for `bundle`)

Every `.md` file must start with:

```markdown
# Title

> Description
> Second optional description line.
```

Everything after the description block is preserved unchanged.

**Rules:**

| Rule | Why |
|---|---|
| First line must be `# Title` | Tool reads title here |
| Followed by `> Description` | Tool reads description here |
| Folder name = concept type | `tables/orders.md` → `type: "tables"` |
| Only `.md` files processed | Non-`.md` files ignored |
| `index.md`, `log.md`, `README.md` skipped in `bundle` | Input may contain repo artifacts; these are not concepts. `bundle` warns when it skips them. Other commands (`list`, `show`, `validate`) operate on conformant OKF bundles where only `index.md` and `log.md` are reserved. |

**Violations:**

| Condition | Behavior |
|---|---|
| Line 1 not `# Title` | Error, stop |
| Empty title | Error, stop |
| No `> description` block | Error, stop |
| Root-level file without `--default-type` | Skip file, warn, continue |

Root files need `--default-type`. Otherwise put files in named folders.

See the [`example/`](example/) directory for a sample of how to structure files.

## How `bundle` works

1. Walk `input-dir` for `.md` files (skip reserved names)
2. Extract `title` from `#`, `description` from `>`
3. Set `type` from parent dir name, `timestamp` from file mtime
4. Write concept files with YAML frontmatter
5. Generate `index.md` per directory — `# Contents` for files, `# Directories` for subdirs (recursive)

## Output

Each concept becomes a markdown file with YAML frontmatter:

```yaml
---
type: "tables"
title: "Customer Orders"
description: "One row per completed customer order across all channels."
timestamp: "2026-07-04T15:06:51+00:00"
---

Original body preserved as-is.
```

Every directory gets its own `index.md`:

```markdown
# Contents

* [Customer Orders](orders.md) - One row per completed customer order across all channels.

# Directories

* [partitions](partitions/)
```

## OKF Conformance

Generated bundles conform to [OKF v0.1](OKF_SPEC.md) (§9):

- Every non-reserved `.md` has parseable YAML frontmatter with non-empty `type` ✓
- Reserved filenames follow spec structure ✓
- Consumers MUST tolerate missing optional fields, unknown types, broken links ✓

## Project layout

```
okf-cli
├── .github/workflows/test.yml  # CI
├── OKF_SPEC.md                 # OKF specification
├── pyproject.toml              # uv-managed Python project
├── src/okf/
│   ├── cli.py            # Typer entrypoint
│   ├── core.py           # Shared parsing/formatting
│   └── commands/         # bundle, list, show, validate
├── tests/test_cli.py     # Tests
└── example/              # Sample input markdown
```
