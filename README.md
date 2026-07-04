# okf-cli — Open Knowledge Format tooling

**okf-cli** converts plain markdown into [OKF](https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md)-conformant knowledge bundles.

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

## For domain experts — writing docs that work

### Every file follows the same 3-line pattern

Open your file. Write exactly this:

```markdown
# Customer Orders

> One row per completed customer order across all channels.
```

That's the template. **Every** file must start with a `#` heading, then a blank line, then a `>` description.

Everything after the description is free-form — schema tables, notes, examples, diagrams. It's preserved as-is.

### What you write → what the tool produces

| You write (in `tables/orders.md`) | Tool generates |
|---|---|
| `# Customer Orders` | `title: "Customer Orders"` |
| `> One row per order.` | `description: "One row per order."` |
| File is inside `tables/` folder | `type: "tables"` (from folder name) |
| File's last-modified time | `timestamp: "2026-07-04T15:06:51+00:00"` (auto) |
| Your body text after the description | Preserved unchanged below frontmatter |

### Folder name = concept type

The folder your file lives in becomes its **type** — the category that tells readers what kind of thing this is.

```
tables/orders.md       → type is "tables"
playbooks/oncall.md    → type is "playbooks"
datasets/sales.md      → type is "datasets"
```

**Organize your files into named folders.** Don't leave them loose at the root unless the person running the tool knows to set a default type.

### You can link to other docs

```markdown
See the [orders table](../tables/orders.md) for the join key.
```

Use standard markdown links. Relative paths (`../tables/orders.md`) work. The OKF spec accepts broken links too — no penalty for linking to something not yet written.

### The complete rulebook (short)

| Rule | Why |
|---|---|
| Start every file with `# Title` | Tool reads the title here |
| Follow with `> Description` | Tool reads the description here |
| Name your folder what you want the type to be | Tool infers type from folder name |
| Use `.md` extension | Only `.md` files are processed |
| Don't name files `index.md`, `README.md`, or `log.md` | These names are reserved by the OKF spec |

### What the tool handles FOR you

You don't need to think about:

- **YAML frontmatter** — generated automatically
- **Timestamps** — taken from your file's last-modified time
- **Index files** — every folder gets an `index.md` listing its contents
- **Type field** — derived from your folder structure
- **Quoting** — all values are safely quoted for YAML parsing

### Quick reference: one good file, start to finish

```markdown
# Data Freshness Incident

> Steps to triage a freshness alert on the orders pipeline.

## Trigger

A freshness alert fires when the [orders](../tables/orders.md) table lags.

## Steps

1. Check the ingestion dashboard.
2. Verify upstream source connectivity.
3. Notify the data engineering team if the issue persists.
```

This becomes an OKF concept with `type: "playbooks"` (if in `playbooks/`), a title, description, auto-timestamp, and the body unchanged.

### If something goes wrong

| You see | Likely cause |
|---|---|
| "Line 1 must be '# Title'" | File doesn't start with `# Something` |
| "Must have a '> description' block" | No description line after the title |
| "Skipping ... root-level file" | File is in the root folder; needs `--default-type` from whoever runs the tool |
| File silently missing from output | File is named `index.md`, `log.md`, or `README.md` (reserved names) |

## Input rules (for operators)

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
