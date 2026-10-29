"""Serve a conformant OKF bundle over MCP Streamable HTTP."""

from pathlib import Path
from typing import Any

import typer

from okf import api
from okf.core import err_console


def _create_server(bundle_dir: Path) -> Any:
    """Create an MCP server exposing read-only bundle tools."""
    try:
        from fastmcp import FastMCP
    except ImportError as exc:
        raise RuntimeError(
            "MCP support is not installed. Install okf-cli with the 'mcp' extra."
        ) from exc

    mcp = FastMCP(f"OKF bundle: {bundle_dir.name}")

    @mcp.tool
    def list_concepts() -> list[dict[str, str]]:
        """List concept IDs and their type, title, and description."""
        return api.list_entries(bundle_dir)

    @mcp.tool
    def read_concept(concept_id: str) -> dict[str, Any]:
        """Read an OKF concept by its bundle-relative ID, e.g. tables/orders."""
        concept = api.show_concept(bundle_dir, concept_id)
        return {
            "id": concept_id,
            "frontmatter": concept.frontmatter,
            "body": concept.body,
        }

    return mcp


def serve_mcp(
    directory: Path = typer.Argument(..., help="Directory of the OKF bundle"),
    host: str = typer.Option(
        "127.0.0.1", "--host", help="Interface to bind (default: localhost only)"
    ),
    port: int = typer.Option(8000, "--port", help="HTTP port to bind"),
) -> None:
    """Serve an OKF bundle over MCP Streamable HTTP."""
    bundle_dir = directory.resolve()
    try:
        report = api.validate(bundle_dir)
    except (NotADirectoryError, OSError) as exc:
        err_console.print(f"Error: {exc}", style="red")
        raise typer.Exit(code=1) from exc

    if not report.ok:
        err_console.print(
            "Error: directory is not an OKF-conformant bundle:", style="red"
        )
        for error in report.errors:
            err_console.print(f"  {error}", style="red")
        raise typer.Exit(code=1)

    try:
        mcp = _create_server(bundle_dir)
    except RuntimeError as exc:
        err_console.print(f"Error: {exc}", style="red")
        raise typer.Exit(code=1) from exc

    mcp.run(transport="streamable-http", host=host, port=port, path="/mcp")
