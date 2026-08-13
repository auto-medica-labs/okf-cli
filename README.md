# okf-cli — Open Knowledge Format tooling

Convert plain markdown directories into [OKF](https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md)-conformant knowledge bundles. `okf bundle` generates YAML frontmatter, concept types, provenance, and per-directory `index.md` files; `okf validate`, `okf list`, and `okf read` consume the resulting bundle.

## Install

```bash
uv tool install okf-cli
```

### Dev quickstart

```bash
uv sync
uv run okf --help
uv run okf --version
```

## Commands

| Command                               | Purpose                                      |
| ------------------------------------- | -------------------------------------------- |
| `okf bundle <input-dir> [output-dir]` | Convert markdown into an OKF bundle          |
| `okf validate <directory>`            | Check OKF v0.2 §11 conformance               |
| `okf list <directory>`                | List concepts (ID, type, title, description) |
| `okf read <directory> <concept-id>`   | Print a concept by ID                        |

Run `okf <command> --help` for options such as `--default-type`, `--force`, `--strict`, and `--dry-run`.

## Quick example

```bash
uv run okf bundle example --default-type reference --force
uv run okf validate example_knowledge_base
uv run okf list example_knowledge_base
uv run okf read example_knowledge_base tables/customers
```

## Documentation

- Detailed user and contributor docs: [wiki/quickstart.md](wiki/quickstart.md)
- Agent contributor context: [AGENTS.md](AGENTS.md)
- OKF v0.2 specification: [SPEC/OKF_SPEC_V0_2.md](SPEC/OKF_SPEC_V0_2.md)
