# okf-cli — Open Knowledge Format tooling

**okf-cli** converts plain markdown into [OKF](OKF_SPEC.md)-conformant knowledge bundles.

Domain experts write markdown with a simple rule — `# Title` then `> description` — and `okf enrich` generates the frontmatter, type, timestamps, and index files.

---

## Quickstart

```bash
# Install
uv sync

# Convert the example (output-dir defaults to 'bundled')
uv run okf example

# See the result
cat bundled/index.md
cat bundled/tables/orders.md
cat bundled/tables/index.md
```

## Usage

```
okf <input-dir> [output-dir] [--default-type <name>]
```

| Argument | Description |
|---|---|
| `input-dir` | Directory of plain markdown files |
| `output-dir` | Target directory for the OKF bundle (default: `bundled`) |
| `--default-type` | Type for root-level files (skip root files if omitted) |

## Input rules

Every markdown file **must** start with:

```markdown
# Customer Orders

> One row per completed customer order across all channels.
> Second line of description if needed.
```

Violations:

| Condition | Behavior |
|---|---|
| Line 1 not `# Title` | Error, stop |
| Empty title | Error, stop |
| No `> description` block after title | Error, stop |
| Root-level file without `--default-type` | Skip file, warn, continue |

Files named `index.md`, `log.md`, or `README.md` are automatically skipped (OKF reserved filenames).

## How it works

1. Walk `input-dir` for all `.md` files
2. Extract `title` from `#`, `description` from `>`
3. Set `type` from parent directory name (`tables/orders.md` → `type: tables`)
4. Set `timestamp` from file modification time
5. Generate `index.md` per directory — `# Contents` for files, `# Directories` for subdirectories (recursive)
6. Write OKF-conformant bundle to `output-dir`

## Output

Each concept becomes a markdown file with YAML frontmatter. Values are always quoted for safety:

```yaml
---
type: "tables"
title: "Customer Orders"
description: "One row per completed customer order across all channels."
timestamp: "2026-07-04T15:06:51+00:00"
---

Original body preserved as-is.
```

Every directory gets an `index.md` with files and subdirectories listed separately:

```markdown
# Contents

* [Customer Orders](orders.md) - One row per completed customer order across all channels.
* [Customers](customers.md) - One row per registered customer.

# Directories

* [partitions](partitions/)
```

Nested directories get the same treatment recursively:

```
bundle/
├── index.md                       # Contents + Directories (top-level)
├── tables/
│   ├── index.md                   # Contents + Directories (partitions/)
│   ├── orders.md
│   └── partitions/
│       ├── index.md               # Contents + Directories (2026/)
│       ├── daily.md
│       └── 2026/
│           ├── index.md           # Directories only
│           └── q1/
│               ├── index.md       # Directories only
│               └── jan/
│                   ├── index.md   # Contents only
│                   └── january.md
```

## OKF Conformance

The generated bundle is conformant with [OKF v0.1](OKF_SPEC.md) (§9):

- Every non-reserved `.md` has parseable YAML frontmatter with non-empty `type` (values safely quoted) ✓
- Reserved filenames (`index.md`) follow spec structure ✓
- Consumers MUST tolerate missing optional fields, unknown types, broken links ✓

## Project

```
okf-cli
├── OKF_SPEC.md           # The Open Knowledge Format specification
├── pyproject.toml        # uv-managed Python project
├── src/okf/cli.py        # Single-file CLI
├── tests/test_cli.py     # Tests
└── example/              # Sample markdown to try the tool
```
