# okf — Open Knowledge Format tooling

**okf** converts plain markdown into [OKF](OKF_SPEC.md)-conformant knowledge bundles.

Domain experts write markdown with a simple rule — `# Title` then `> description` — and `okf enrich` generates the frontmatter, type, timestamps, and index files.

---

## Quickstart

```bash
# Install
uv sync

# Convert the example
uv run okf example out

# See the result
cat out/index.md
cat out/tables/orders.md
cat out/tables/index.md
```

## Usage

```
okf <input-dir> <output-dir> [--default-type <name>]
```

| Argument | Description |
|---|---|
| `input-dir` | Directory of plain markdown files |
| `output-dir` | Target directory for the OKF bundle (must not exist) |
| `--default-type` | Type for root-level files (skip root files if omitted) |

## Input rules

Every markdown file **must** start with:

```markdown
# Customer Orders

> One row per completed customer order across all channels.
> Second line of description if needed.
```

| Rule | Violation |
|---|---|
| Line 1 must be `# Title` | Error, stop |
| Title must be non-empty | Error, stop |
| Next non-blank lines must be `> description` | Error, stop |
| Root-level file without `--default-type` | Skip file, warn, continue |

Files named `index.md`, `log.md`, or `README.md` are automatically skipped (not concepts).

## How it works

1. Walks `input-dir` for all `.md` files
2. Extracts `title` from `#`, `description` from `>`
3. Sets `type` from parent directory name (`tables/orders.md` → `type: tables`)
4. Sets `timestamp` from file modification time
5. Generates `index.md` per directory listing contents
6. Writes OKF-conformant bundle to `output-dir`

### Example

```
input/
├── datasets/
│   └── sales.md
├── tables/
│   ├── orders.md
│   └── customers.md
└── playbooks/
    └── incident-response.md
```

```
$ okf input bundle
Done. Converted 4 files → bundle
```

```
bundle/
├── index.md                      # lists: datasets/ playbooks/ tables/
├── datasets/
│   ├── index.md                  # lists: Sales
│   └── sales.md                  # type: datasets
├── tables/
│   ├── index.md                  # lists: Customer Orders, Customers
│   ├── orders.md                 # type: tables
│   └── customers.md              # type: tables
└── playbooks/
    ├── index.md                  # lists: Incident Response
    └── incident-response.md      # type: playbooks
```

Output files:

```yaml
---
type: tables
title: Customer Orders
description: One row per completed customer order across all channels.
timestamp: 2026-07-04T15:06:51+00:00
---

Original body content preserved as-is.
```

## OKF Conformance

The generated bundle is conformant with [OKF v0.1](OKF_SPEC.md) (§9):

- Every non-reserved `.md` has parseable YAML frontmatter with non-empty `type` ✓
- Reserved filenames (`index.md`) follow spec structure ✓
- Consumers MUST tolerate missing optional fields, unknown types, broken links ✓

## Project

```
okf
├── OKF_SPEC.md           # The Open Knowledge Format specification
├── pyproject.toml        # uv-managed Python project
├── src/okf/cli.py        # Single-file CLI
├── tests/test_cli.py     # Tests
└── example/              # Example markdown to try the tool
```
