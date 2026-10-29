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
| `okf serve-mcp <directory>`           | Serve a conformant bundle over MCP HTTP      |

Run `okf <command> --help` for options such as `--default-type`, `--force`, `--strict`, and `--dry-run`.

### MCP server

Install the optional MCP dependency, then serve a conformant bundle over Streamable HTTP:

```bash
uv sync --extra mcp
uv run okf serve-mcp example_knowledge_base
```

The server binds to `127.0.0.1:8000` by default and listens at `http://127.0.0.1:8000/mcp`. Use `--host` and `--port` to change the bind address. The server exposes read-only `list_concepts` and `read_concept` tools. Non-local binds have no built-in authentication; use them only on a trusted network or behind an authenticated proxy.

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
