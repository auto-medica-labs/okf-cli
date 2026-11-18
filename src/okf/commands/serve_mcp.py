"""Serve a conformant OKF bundle over MCP Streamable HTTP."""

import secrets
from datetime import date, datetime
from pathlib import Path
from typing import Any

import typer

from okf import api
from okf.core import err_console


def _create_server(
    bundle_dir: Path, token: str | None = None, loaded: api.Bundle | None = None
) -> Any:
    """Create an MCP server exposing read-only bundle tools.

    Pass ``loaded`` to hand in an already-open bundle instead of loading it
    a second time.
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
            async def verify_token(self, provided: str) -> AccessToken | None:
                if not secrets.compare_digest(provided, expected_token):
                    return None
                return AccessToken(
                    token=provided,
                    client_id="okf-cli",
                    scopes=[],
                )

        auth = _TokenVerifier()

    if loaded is None:
        loaded = api.Bundle.open(bundle_dir)
    instructions = _instructions(bundle_dir)
    mcp = FastMCP(
        f"OKF bundle: {bundle_dir.name}", instructions=instructions, auth=auth
    )

    # Tools re-check the bundle on every call, so a file another process
    # added, changed or removed is picked up on the next tool call.
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
        """Find concepts by words in the ID, title, description, tags or any
        other frontmatter value.

        Each word in `query` is matched case-insensitively as a substring of
        the ID and of every frontmatter string value (dates and numbers are
        matched as their text; `generated` and `verified` are ignored).
        Concepts matching more words rank higher, then by field weight (ID
        and title > tags and description > other keys). `type` keeps only
        concepts of that type (case-insensitive). `filters` maps frontmatter
        keys to required values; a list-valued key matches when it contains
        the value. An empty `query` lists every concept passing the filters.
        """
        loaded.refresh()
        return loaded.search(query, type_=type, filters=filters, limit=limit)

    @mcp.tool(annotations=read_only)
    def browse(path: str = "") -> dict[str, Any]:
        """List a bundle directory ("" for the bundle root).

        Returns the directory's concepts (id, type, title, description) and
        its subdirectories, all with bundle-relative paths. Every concept id
        can be passed to `read_concept` and every directory back to
        `browse`, e.g. "tables".
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


_TOOL_GUIDE = (
    "This server serves an Open Knowledge Format (OKF) bundle: a directory of "
    "markdown concepts with YAML frontmatter (type, title, description and "
    "producer-defined keys). A concept's ID is its path without the .md "
    "suffix, e.g. tables/orders. To answer from the bundle: use `search` to "
    "find concepts by words, IDs, tags or other frontmatter values; `browse` "
    'to walk the directory tree from the root (""); `read_concept` to read '
    "one concept, optionally only the section you need. Body links are "
    "relative markdown paths; `read_concept` reports them with the concept "
    "`id` to follow and an `exists` flag (false means the referenced concept "
    "is not in this bundle). `list_concepts` returns the whole listing and "
    "is best kept for small bundles — prefer `search` or `browse`."
)

_AGENTS_NOTE = (
    "The bundle's own AGENTS.md follows. Its advice is written for reading "
    "the files directly; where it says to read an index.md, call `browse` "
    'instead (the root index is `browse("")`).'
)


def _instructions(bundle_dir: Path) -> str:
    """Fixed tool guide followed by the bundle's AGENTS.md, when present."""
    try:
        for entry in bundle_dir.iterdir():
            if entry.name.lower() == "agents.md" and entry.is_file():
                guide = entry.read_text(encoding="utf-8").strip()
                if guide:
                    return f"{_TOOL_GUIDE}\n\n{_AGENTS_NOTE}\n\n{guide}"
    except OSError:
        pass
    return _TOOL_GUIDE


def _jsonable(value: Any) -> Any:
    """Turn dates and timestamps into ISO strings for JSON transport."""
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, (date, datetime)):
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
    except NotADirectoryError as exc:
        err_console.print(f"Error: {exc}", style="red")
        raise typer.Exit(code=1) from exc
    except ValueError as exc:
        # Bundle errors are "not an OKF-conformant bundle:" + one line each.
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
