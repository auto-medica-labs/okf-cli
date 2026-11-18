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
        "links": [],
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

    def fake_create_server(_bundle_dir, token=None, loaded=None):
        assert loaded is not None
        server_options.update(token=token, loaded_ids=loaded.ids())
        return FakeServer()

    monkeypatch.setattr("okf.commands.serve_mcp._create_server", fake_create_server)
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
    # The bundle is loaded once by the command and handed to the server.
    assert server_options == {"token": "secret-token", "loaded_ids": ["tables/orders"]}
    assert run_options == {
        "transport": "streamable-http",
        "host": "0.0.0.0",
        "port": 9000,
        "path": "/mcp",
    }


def test_serve_mcp_rejects_nonconformant_bundle(tmp_path: Path, monkeypatch):
    bundle_dir = tmp_path / "bundle"
    _write_bundle(bundle_dir, conformant=False)

    def fail_if_called(_bundle_dir, token=None, loaded=None):
        raise AssertionError("server must not start for a non-conformant bundle")

    monkeypatch.setattr("okf.commands.serve_mcp._create_server", fail_if_called)
    result = runner.invoke(app, ["serve-mcp", str(bundle_dir)])

    assert result.exit_code == 1
    assert "not an OKF-conformant bundle" in result.output


def _write_kb(bundle_dir: Path) -> None:
    files = {
        "tables/orders.md": "---\ntype: Table\ntitle: Orders\ndescription: "
        "Order records.\ntags: [sales]\nstale_after: 2026-12-31\n---\n\n"
        "# Schema\n\n| order_id |\n\n# Notes\n\n"
        "Joined with [customers](customers.md) and [refunds](/tables/refunds.md).\n",
        "tables/customers.md": "---\ntype: Table\ntitle: Customers\n"
        "description: One row per customer.\n---\n\nBody.\n",
    }
    for rel, text in files.items():
        path = bundle_dir / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


def test_mcp_search_browse_and_read_section(tmp_path: Path):
    bundle_dir = tmp_path / "bundle"
    _write_kb(bundle_dir)
    server = _create_server(bundle_dir)

    async def call_tools():
        async with Client(server) as client:
            found = await client.call_tool("search", {"query": "sales orders"})
            filtered = await client.call_tool(
                "search", {"type": "Table", "filters": {"tags": "sales"}}
            )
            index = await client.call_tool("browse", {"path": "tables"})
            section = await client.call_tool(
                "read_concept", {"concept_id": "tables/orders", "section": "Schema"}
            )
        return found, filtered, index, section

    found, filtered, index, section = asyncio.run(call_tools())

    assert [e["id"] for e in found.structured_content["result"]] == ["tables/orders"]
    assert [e["id"] for e in filtered.structured_content["result"]] == ["tables/orders"]
    assert index.structured_content == {
        "path": "tables",
        "concepts": [
            {
                "id": "tables/customers",
                "type": "Table",
                "title": "Customers",
                "description": "One row per customer.",
            },
            {
                "id": "tables/orders",
                "type": "Table",
                "title": "Orders",
                "description": "Order records.",
            },
        ],
        "directories": [],
    }
    assert section.structured_content["body"] == "# Schema\n\n| order_id |\n"
    assert section.structured_content["links"] == []
    assert section.structured_content["frontmatter"]["stale_after"] == "2026-12-31"


def test_mcp_tools_see_files_written_after_start(tmp_path: Path):
    bundle_dir = tmp_path / "bundle"
    _write_kb(bundle_dir)
    server = _create_server(bundle_dir)
    (bundle_dir / "tables" / "invoices.md").write_text(
        "---\ntype: Table\ntitle: Invoices\n---\n\nBody.\n", encoding="utf-8"
    )

    async def call_tools():
        async with Client(server) as client:
            return await client.call_tool("search", {"query": "invoices"})

    result = asyncio.run(call_tools())

    assert [e["id"] for e in result.structured_content["result"]] == ["tables/invoices"]


def test_mcp_instructions_include_bundle_agents_md(tmp_path: Path):
    bundle_dir = tmp_path / "bundle"
    _write_kb(bundle_dir)

    plain = _create_server(bundle_dir)
    (bundle_dir / "AGENTS.md").write_text("Code wins over the KB.", encoding="utf-8")
    guided = _create_server(bundle_dir)

    assert "`search`" in plain.instructions
    assert "Code wins over the KB." not in plain.instructions
    assert guided.instructions.startswith(plain.instructions)
    assert guided.instructions.endswith("Code wins over the KB.")


def test_mcp_read_concept_resolves_links_and_id(tmp_path: Path):
    bundle_dir = tmp_path / "bundle"
    _write_kb(bundle_dir)
    server = _create_server(bundle_dir)

    async def call_tools():
        async with Client(server) as client:
            tools = await client.list_tools()
            concept = await client.call_tool(
                "read_concept", {"concept_id": "/tables/orders.md"}
            )
            root = await client.call_tool("browse", {"path": ""})
        return tools, concept, root

    tools, concept, root = asyncio.run(call_tools())

    assert all(t.annotations.read_only_hint for t in tools)
    assert concept.structured_content["id"] == "tables/orders"
    assert concept.structured_content["links"] == [
        {"target": "customers.md", "id": "tables/customers", "exists": True},
        {"target": "/tables/refunds.md", "id": "tables/refunds", "exists": False},
    ]
    assert root.structured_content == {
        "path": "",
        "concepts": [],
        "directories": ["tables"],
    }


def test_mcp_instructions_point_agents_md_index_to_browse(tmp_path: Path):
    bundle_dir = tmp_path / "bundle"
    _write_kb(bundle_dir)
    (bundle_dir / "AGENTS.md").write_text("Read index.md first.", encoding="utf-8")

    instructions = _create_server(bundle_dir).instructions

    assert "call `browse` instead" in instructions
    assert instructions.index("call `browse` instead") < instructions.index(
        "Read index.md first."
    )
