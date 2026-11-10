# okf-cli — Open Knowledge Format tooling

Convert plain markdown directories into [OKF](https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md)-conformant knowledge bundles. `okf bundle` generates YAML frontmatter, concept types, provenance, and per-directory `index.md` files; `okf validate`, `okf list`, and `okf read` consume the resulting bundle.

## Install

```bash
uv tool install okf-cli
```

This installs the `okf` command. To include the optional MCP server support at the same time, install with the `mcp` extra instead:

```bash
uv tool install 'okf-cli[mcp]'
```

(If you already installed without it, reinstall with `uv tool install --force 'okf-cli[mcp]'`.)

Check the installation:

```bash
okf --help
okf --version
```

## Quick example

Try it on a scratch directory:

```bash
mkdir okf-demo
printf '# Customers\n\n> Master table of customers.\n\nOne row per customer.\n' > okf-demo/customers.md

okf bundle okf-demo
okf validate okf-demo_knowledge_base
okf list okf-demo_knowledge_base
okf read okf-demo_knowledge_base customers
```

Your real usage will point at your own markdown directories instead:

```bash
okf bundle my-notes
okf validate my-notes_knowledge_base
okf list my-notes_knowledge_base
okf read my-notes_knowledge_base <concept-id>
```

Run `okf <command> --help` for options such as `--default-type`, `--force`, `--strict`, and `--dry-run`. (Without an explicit output directory, `okf bundle <input-dir>` writes to `<input-dir>_knowledge_base` in the current directory.)

## Commands

| Command                               | Purpose                                      |
| ------------------------------------- | -------------------------------------------- |
| `okf bundle <input-dir> [output-dir]` | Convert markdown into an OKF bundle          |
| `okf validate <directory>`            | Check OKF v0.2 §11 conformance               |
| `okf list <directory>`                | List concepts (ID, type, title, description) |
| `okf read <directory> <concept-id>`   | Print a concept by ID                        |
| `okf serve-mcp <directory>`           | Serve a conformant bundle over MCP HTTP      |

### MCP server

Install the optional MCP dependency (if you installed with `uv tool install okf-cli`, reinstall with `--force 'okf-cli[mcp]'` as shown above), then serve a conformant bundle over Streamable HTTP:

```bash
okf serve-mcp my-bundle
```

The server binds to `127.0.0.1:8000` by default and listens at `http://127.0.0.1:8000/mcp`. Use `--host` and `--port` to change the bind address; `--host 0.0.0.0` listens on all IPv4 interfaces. The server exposes read-only `list_concepts` and `read_concept` tools. Add `--token <secret>` to require the matching `Authorization: Bearer <secret>` header on MCP requests; without it, requests are unauthenticated. For example:

```bash
okf serve-mcp my-bundle --token "$OKF_MCP_TOKEN"
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
okf serve-mcp my-bundle --token "$OKF_MCP_TOKEN"
```

Clients connect to `https://mcp.example.com/mcp` and send `Authorization: Bearer <token>`. Keep port `8000` private; Caddy should be the public entry point. Caddy can provision HTTPS automatically when the domain points to the server and is reachable on the required ports.

## Documentation

- OKF v0.2 specification: [SPEC/OKF_SPEC_V0_2.md](SPEC/OKF_SPEC_V0_2.md)
- Development and contributor docs: [wiki/quickstart.md](wiki/quickstart.md) and [AGENTS.md](AGENTS.md)
