# okf-cli — Open Knowledge Format tooling

Converts plain markdown into [OKF](https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md)-conformant knowledge bundles. Domain experts write `# Title` then `> description` — `okf bundle` generates frontmatter, type, timestamps, and index files.

## Install

```bash
uv tool install okf-cli
```

Then run:

```bash
okf bundle example              # output → bundled/
cat bundled/index.md
cat bundled/tables/orders.md
```

### Dev quickstart

```bash
uv sync
uv run okf example
```

## Usage

```
okf <input-dir> [output-dir] [--default-type <name>]
```

| Argument | Description |
|---|---|
| `input-dir` | Directory of plain `.md` files |
| `output-dir` | Target directory (default: `bundled`) |
| `--default-type` | Type for root-level files (skip root files if omitted) |

## Writing input files

Every `.md` file must start with:

```markdown
# Title

> Description
> Second optional description line.
```

Everything after the description block is free-form — preserved unchanged.

**Rules:**

| Rule | Why |
|---|---|
| First line must be `# Title` | Tool reads title here |
| Followed by `> Description` | Tool reads description here |
| Folder name = concept type | `tables/orders.md` → `type: "tables"` |
| Only `.md` files processed | Non-`.md` files ignored |
| Reserved names skipped: `index.md`, `log.md`, `README.md` | OKF spec reserves these |

**Violations:**

| Condition | Behavior |
|---|---|
| Line 1 not `# Title` | Error, stop |
| Empty title | Error, stop |
| No `> description` block | Error, stop |
| Root-level file without `--default-type` | Skip file, warn, continue |

Root files need `--default-type`. Otherwise put files in named folders.

See the [`example/`](example/) directory for a sample of how to structure files.

## How it works

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
├── OKF_SPEC.md           # OKF specification
├── pyproject.toml        # uv-managed Python project
├── src/okf/cli.py        # Single-file CLI
├── tests/test_cli.py     # Tests
└── example/              # Sample input markdown
```
