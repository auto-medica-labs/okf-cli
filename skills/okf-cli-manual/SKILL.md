---
name: okf-cli-manual
description: Install and use okf-cli to convert plain markdown into OKF-conformant knowledge bundles, list concept IDs, inspect concepts, and validate bundles. Use when the user asks to "bundle markdown", "create OKF bundle", "validate OKF", "list concepts", or work with okf-cli.
license: MIT
---

# okf-cli Manual

Install and use okf-cli for working with Open Knowledge Format (OKF)

## Install

```bash
uv tool install okf-cli
okf --version
```

Upgrade:

```bash
uv tool upgrade okf-cli
```

## Commands

### `okf bundle` — convert plain markdown to OKF bundle

```
okf bundle <input-dir> [output-dir] [--default-type <type>] [--force] [--strict-links]
```

| Argument         | Description                                                                  |
| ---------------- | ---------------------------------------------------------------------------- |
| `input-dir`      | Directory of plain `.md` files                                               |
| `output-dir`     | Target directory (default: `bundled`)                                        |
| `--default-type` | Type for root-level files — skip root files if omitted                       |
| `--force`, `-f`  | Overwrite output directory if it exists                                      |
| `--strict-links` | Fail if local markdown links point outside bundle or to missing `.md` target |

```bash
okf bundle my-docs bundled --default-type reference
okf bundle my-docs bundled --default-type reference --force
okf bundle my-docs bundled --default-type reference --strict-links
```

`.okfignore` — place in `input-dir` root, one bundle-relative path per line:

```
# skip these files
smoke-ignore.md
tables/orders.md
```

### `okf list` — list concept IDs in a bundle

```
okf list <directory>
```

Prints concept IDs (path with `.md` stripped). Reserved files (`index.md`, `log.md`) excluded.

```bash
okf list bundled/
# datasets/sales
# tables/orders
# tables/customers
```

### `okf show` — print a concept by ID

```
okf show <directory> <concept-id>
```

```bash
okf show bundled/ tables/orders
```

### `okf validate` — check OKF conformance

```
okf validate <directory>
```

Validates per OKF §9: frontmatter present, `type` non-empty, reserved filenames follow structure.

```bash
okf validate bundled/
```

## Input format for `bundle`

Each `.md` file should follow this structure:

```markdown
# Clear Concept Title

> One-sentence summary of this concept.

Body content with useful context, structure, examples, or schema.
```

Rules:

- First line: `# Title`
- Second block: `>` description (concise, factual)
- Directory name becomes the concept `type`: `tables/orders.md` → type `tables`
- Root-level files require `--default-type`
- Do not add frontmatter to source files — `okf bundle` generates it
- Avoid creating `index.md`, `log.md`, or `README.md` as source concepts (reserved by spec)
