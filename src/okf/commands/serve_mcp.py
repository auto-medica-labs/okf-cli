"""Serve a conformant OKF bundle over MCP Streamable HTTP."""

import secrets
from datetime import date
from pathlib import Path
from typing import Any

import typer

from okf import api
from okf.core import err_console


def _create_server(
    bundle_dir: Path, token: str | None = None, loaded: api.Bundle | None = None
) -> Any:
    """Create an MCP server exposing read-only bundle tools.

    Pass ``loaded`` when the bundle is already open, to avoid loading it twice.
    """
    try:
        from fastmcp import FastMCP
    except ImportError as exc:
        raise RuntimeError(
            "MCP support is not installed. Install okf-cli with the 'mcp' extra."
        ) from exc

    auth = None
    if token is not None:
        from fastmcp.server.auth import AccessToken, TokenVerifier

        expected_token = token

        class _TokenVerifier(TokenVerifier):
            async def verify_token(self, token: str) -> AccessToken | None:
                if not secrets.compare_digest(token, expected_token):
                    return None
                return AccessToken(
                    token=token,
                    client_id="okf-cli",
                    scopes=[],
                )

        auth = _TokenVerifier()

    if loaded is None:
        loaded = api.Bundle.open(bundle_dir)
    mcp = FastMCP(
        f"OKF bundle: {bundle_dir.name}",
        instructions=_instructions(bundle_dir),
        auth=auth,
    )

    # Every tool refreshes first: files changed on disk since the last call
    # (for example by a generator writing into the bundle) are re-read.
    read_only = {"readOnlyHint": True}

    @mcp.tool(annotations=read_only)
    def list_concepts() -> list[dict[str, str]]:
        """List every concept ID with its type, title, and description.

        Large bundles return a long list; prefer `search` or `browse`.
        """
        loaded.refresh()
        return loaded.entries()

    @mcp.tool(annotations=read_only)
    def search(
        query: str = "",
        type: str | None = None,
        filters: dict[str, str] | None = None,
        limit: int = 20,
    ) -> list[dict[str, str]]:
        """Find concepts by words, IDs, tags or other frontmatter values.

        Each word of `query` is matched case-insensitively as a substring of
        the concept ID, title, description, tags and every other frontmatter
        value. Concepts matching more words rank first. `type` keeps only that
        concept type; `filters` maps frontmatter keys to required values (a
        list-valued key must contain the value). An empty `query` lists every
        concept that passes the filters.
        """
        loaded.refresh()
        return loaded.search(query, type_=type, filters=filters, limit=limit)

    @mcp.tool(annotations=read_only)
    def browse(path: str = "") -> dict[str, Any]:
        """List a bundle directory ("" for the root).

        Returns the directory's concepts (id, type, title, description) and
        its subdirectories. Every concept `id` can be passed to `read_concept`
        and every directory back to `browse`, e.g. "tables".
        """
        loaded.refresh()
        return loaded.listdir(path)

    @mcp.tool(annotations=read_only)
    def read_concept(concept_id: str, section: str | None = None) -> dict[str, Any]:
        """Read an OKF concept by its bundle-relative ID, e.g. tables/orders.

        Set `section` to a heading (e.g. "Schema") to get only that section.
        `links` lists the concepts the returned body links to: `target` as
        written in the body, `id` to pass to `read_concept`, and `exists`
        false when that concept is not in the bundle.
        """
        loaded.refresh()
        concept = loaded.read(concept_id, section=section)
        return {
            "id": concept.id,
            "frontmatter": _jsonable(concept.frontmatter),
            "body": concept.body,
            "links": concept.links,
        }

    return mcp


_DEFAULT_INSTRUCTIONS = (
    "This server serves an OKF (Open Knowledge Format) knowledge bundle. Each "
    "concept is a markdown document with YAML frontmatter (type, title, "
    "description, and producer-defined keys), identified by its path without "
    "'.md' (e.g. tables/orders). Use `search` to find concepts by words, IDs, "
    "tags or other frontmatter values; use `browse` to walk directories from "
    'the root (""); use `read_concept` to read a concept, or only one section '
    "of it. Links in a concept body are relative markdown paths: follow them "
    "with the `id` from `read_concept`'s `links`, where `exists` is false for "
    "a concept missing from the bundle."
)

_AGENTS_PREAMBLE = (
    "The bundle's own guide follows. It is written for reading the files "
    "directly: where it says to read an index.md, call `browse` instead "
    '(the root index is `browse("")`).'
)


def _instructions(bundle_dir: Path) -> str:
    """Tool guidance, followed by the bundle's own AGENTS.md when present."""
    for entry in bundle_dir.iterdir():
        if entry.name.lower() == "agents.md" and entry.is_file():
            guide = entry.read_text(encoding="utf-8").strip()
            return f"{_DEFAULT_INSTRUCTIONS}\n\n{_AGENTS_PREAMBLE}\n\n{guide}"
    return _DEFAULT_INSTRUCTIONS


def _jsonable(value: Any) -> Any:
    """Turn YAML dates and timestamps into ISO strings for JSON output."""
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_jsonable(v) for v in value]
    if isinstance(value, date):
        return value.isoformat()
    return value


def serve_mcp(
    directory: Path = typer.Argument(..., help="Directory of the OKF bundle"),
    host: str = typer.Option(
        "127.0.0.1", "--host", help="Interface to bind (default: localhost only)"
    ),
    port: int = typer.Option(8000, "--port", help="HTTP port to bind"),
    token: str | None = typer.Option(
        None,
        "--token",
        help="Require this bearer token for MCP requests",
        show_default=False,
    ),
) -> None:
    """Serve an OKF bundle over MCP Streamable HTTP."""
    if token is not None and not token.strip():
        err_console.print("Error: --token must not be empty", style="red")
        raise typer.Exit(code=2)

    bundle_dir = directory.resolve()
    try:
        loaded = api.Bundle.open(bundle_dir)
    except (NotADirectoryError, OSError) as exc:
        err_console.print(f"Error: {exc}", style="red")
        raise typer.Exit(code=1) from exc
    except ValueError as exc:
        # Message: "not an OKF-conformant bundle:" followed by one error per line
        first, *errors = str(exc).splitlines()
        err_console.print(f"Error: directory is {first}", style="red")
        for error in errors:
            err_console.print(f"  {error}", style="red")
        raise typer.Exit(code=1) from exc

    try:
        mcp = _create_server(bundle_dir, token=token, loaded=loaded)
    except RuntimeError as exc:
        err_console.print(f"Error: {exc}", style="red")
        raise typer.Exit(code=1) from exc

    mcp.run(transport="streamable-http", host=host, port=port, path="/mcp")
