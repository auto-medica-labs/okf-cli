"""MCP server and CLI tests."""

import asyncio
from pathlib import Path

from fastmcp import Client
from typer.testing import CliRunner

from okf.cli import app
from okf.commands.serve_mcp import _create_server

runner = CliRunner()


def _write_bundle(bundle_dir: Path, *, conformant: bool = True) -> None:
    concept = bundle_dir / "tables" / "orders.md"
    concept.parent.mkdir(parents=True)
    content = (
        "---\ntype: tables\ntitle: Orders\ndescription: Order records.\n---\n\n"
        "Details about orders.\n"
        if conformant
        else "Not an OKF concept.\n"
    )
    concept.write_text(content, encoding="utf-8")


def test_mcp_tools_list_and_read_concepts(tmp_path: Path):
    bundle_dir = tmp_path / "bundle"
    _write_bundle(bundle_dir)
    server = _create_server(bundle_dir)
    assert server.auth is None

    async def call_tools():
        async with Client(server) as client:
            entries = await client.call_tool("list_concepts")
            concept = await client.call_tool(
                "read_concept", {"concept_id": "tables/orders"}
            )
        return entries, concept

    entries, concept = asyncio.run(call_tools())

    assert entries.is_error is False
    assert entries.structured_content == {
        "result": [
            {
                "id": "tables/orders",
                "type": "tables",
                "title": "Orders",
                "description": "Order records.",
            }
        ]
    }
    assert concept.is_error is False
    assert concept.structured_content == {
        "id": "tables/orders",
        "frontmatter": {
            "type": "tables",
            "title": "Orders",
            "description": "Order records.",
        },
        "body": "Details about orders.\n",
    }


def test_mcp_token_authentication(tmp_path: Path):
    bundle_dir = tmp_path / "bundle"
    _write_bundle(bundle_dir)
    server = _create_server(bundle_dir, token="secret-token")

    async def verify_tokens():
        assert server.auth is not None
        valid = await server.auth.verify_token("secret-token")
        invalid = await server.auth.verify_token("wrong-token")
        return valid, invalid

    valid, invalid = asyncio.run(verify_tokens())
    assert valid is not None
    assert invalid is None


def test_serve_mcp_runs_streamable_http(tmp_path: Path, monkeypatch):
    bundle_dir = tmp_path / "bundle"
    _write_bundle(bundle_dir)
    run_options = {}
    server_options = {}

    class FakeServer:
        def run(self, **kwargs):
            run_options.update(kwargs)

    monkeypatch.setattr(
        "okf.commands.serve_mcp._create_server",
        lambda _bundle_dir, token=None: (
            server_options.update(token=token) or FakeServer()
        ),
    )
    result = runner.invoke(
        app,
        [
            "serve-mcp",
            str(bundle_dir),
            "--host",
            "0.0.0.0",
            "--port",
            "9000",
            "--token",
            "secret-token",
        ],
    )

    assert result.exit_code == 0, result.output
    assert server_options == {"token": "secret-token"}
    assert run_options == {
        "transport": "streamable-http",
        "host": "0.0.0.0",
        "port": 9000,
        "path": "/mcp",
    }


def test_serve_mcp_rejects_nonconformant_bundle(tmp_path: Path, monkeypatch):
    bundle_dir = tmp_path / "bundle"
    _write_bundle(bundle_dir, conformant=False)

    def fail_if_called(_bundle_dir, token=None):
        raise AssertionError("server must not start for a non-conformant bundle")

    monkeypatch.setattr("okf.commands.serve_mcp._create_server", fail_if_called)
    result = runner.invoke(app, ["serve-mcp", str(bundle_dir)])

    assert result.exit_code == 1
    assert "not an OKF-conformant bundle" in result.output
