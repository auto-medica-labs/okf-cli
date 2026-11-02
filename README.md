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

The server binds to `127.0.0.1:8000` by default and listens at `http://127.0.0.1:8000/mcp`. Use `--host` and `--port` to change the bind address; `--host 0.0.0.0` listens on all IPv4 interfaces. The server exposes read-only `list_concepts` and `read_concept` tools. Add `--token <secret>` to require the matching `Authorization: Bearer <secret>` header on MCP requests; without it, requests are unauthenticated. For example:

```bash
uv run okf serve-mcp example_knowledge_base --token "$OKF_MCP_TOKEN"
```

Use HTTPS (typically through a TLS-terminating proxy) when serving beyond localhost. The token is a command-line argument and may be visible in shell history or process listings; use this option only on a trusted network, and do not treat it as a replacement for TLS.

#### HTTPS with Caddy

When Caddy runs on the same machine, leave the MCP server bound to its default `127.0.0.1` address and let Caddy handle public HTTPS:

```caddyfile
mcp.example.com {
    reverse_proxy 127.0.0.1:8000
}
```

Start the MCP server with authentication enabled:

```bash
uv run okf serve-mcp example_knowledge_base --token "$OKF_MCP_TOKEN"
```

Clients connect to `https://mcp.example.com/mcp` and send `Authorization: Bearer <token>`. Keep port `8000` private; Caddy should be the public entry point. Caddy can provision HTTPS automatically when the domain points to the server and is reachable on the required ports.

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
