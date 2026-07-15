# okf-cli — Open Knowledge Format tooling

Converts plain markdown into [OKF](https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md)-conformant knowledge bundles. Domain experts write the content, `okf bundle` generates frontmatter, type, timestamps, and index files.

Also validates bundles, lists concept IDs, and reads concepts by ID.

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
okf bundle <input-dir> [output-dir] [--default-type <name>] [--force] [--strict-links]
```

| Argument         | Description                                                                  |
| ---------------- | ---------------------------------------------------------------------------- |
| `input-dir`      | Directory of plain `.md` files                                               |
| `output-dir`     | Target directory (default: `bundled`)                                        |
| `--default-type` | Type for root-level files (skip root files if omitted)                       |
| `--force`, `-f`  | Overwrite output directory if it exists                                      |
| `--strict-links` | Fail if local markdown links point outside bundle or to missing `.md` target |

```bash
okf bundle example --default-type reference  # → bundled/
okf bundle example --default-type reference --force --strict-links
```

**`.okfignore`**: put in `input-dir` root; one bundle-relative `.md` path per line. Exact match only (no glob).

**Link checking**: scans body links to local `.md` targets. Missing or out-of-bundle links warn by default, fail with `--strict-links`.

### `okf list` — list concept IDs in a bundle

```
okf list <directory>
```

Prints concept IDs (path without `.md`). Requires valid OKF bundle.

```bash
okf list bundled/
# datasets/sales
# tables/orders
```

### `okf show` — read a concept by ID

```
okf show <directory> <concept-id>
```

Prints full concept contents (frontmatter + body). Concept IDs as printed by `okf list`. Guards against path traversal.

### `okf validate` — check OKF conformance

```
okf validate <directory>
```

Checks OKF v0.1 §9 conformance: frontmatter required, `type` required, reserved filenames follow spec structure, UTF-8 required.

```bash
okf validate bundled/
# 16 files: 16 ok
```

## Input format

### Strict (recommended)

```markdown
# Title

> Description
```

### Lenient fallback

Files without strict format are bundled best-effort: title omitted if absent, description synthesized from first 80 chars of body.

| Rule                                                  | Why                                                                                              |
| ----------------------------------------------------- | ------------------------------------------------------------------------------------------------ |
| Folder name = concept type                            | `tables/orders.md` → `type: "tables"`                                                            |
| Only `.md` files processed                            | Non-`.md` files ignored                                                                          |
| `index.md`, `log.md`, `README.md` skipped in `bundle` | Repo artifacts; not OKF concepts. `list`/`show`/`validate` only reserve `index.md` and `log.md`. |
| `.okfignore` entries skipped                          | Skip selected files without moving them.                                                         |

Root files need `--default-type`. See [`example/`](example/) for sample structure.

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

Every directory gets an `index.md` listing files and subdirs.

## OKF Conformance

Generated bundles conform to [OKF v0.1](OKF_SPEC.md) (§9): frontmatter required, non-empty `type`, reserved filenames follow spec structure.

## Project layout

```
okf-cli
├── .github/workflows/test.yml  # CI
├── OKF_SPEC.md                 # OKF specification
├── pyproject.toml              # uv-managed Python project
├── src/okf/
│   ├── cli.py            # Typer entrypoint
│   ├── api.py            # Programmatic Python API
│   ├── core.py           # Shared parsing/formatting
│   └── commands/         # bundle, list, show, validate
├── tests/                # pytest suite
└── example/              # Sample input markdown
```
