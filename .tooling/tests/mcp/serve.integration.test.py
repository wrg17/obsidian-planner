"""Starting the server for real, over stdio, as a client would.

Every other MCP test calls `call_tool` directly, because dispatch is deliberately
transport-agnostic -- and that is exactly how a server that could not start shipped:
the 2.0 SDK removed the `@server.list_tools()` decorators `serve()` was built on, and
nothing in the suite ever ran `serve()`. A client saw only "connection closed".

So this test owns one claim the others cannot make: the process comes up, completes the
handshake, and answers. It is slow (a subprocess and a real handshake) and marked so.
"""

import asyncio
import os
import sys

import pytest

from planner.mcp import TOOLS

pytest.importorskip("mcp", reason="the MCP SDK is an optional extra")

TIMEOUT = 30  # generous: a cold import of the SDK on CI is not instant


async def _talk(vault, body):
    """Start the server as a subprocess and hand `body` an initialised session."""
    from mcp.client.stdio import stdio_client

    from mcp import ClientSession, StdioServerParameters

    params = StdioServerParameters(
        # sys.executable, not "python3": the venv running the suite is the one with
        # `planner` and the SDK on its path, which is the same requirement a client
        # config has to satisfy.
        command=sys.executable,
        args=["-m", "planner.mcp"],
        # Inherited rather than replaced, so PATH and any PYTHONPATH survive. Only the
        # vault is overridden -- pointed at a tmp_path, so the suite never touches the
        # real one.
        env={**os.environ, "PLANNER_VAULT": str(vault)},
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await asyncio.wait_for(session.initialize(), TIMEOUT)
            return await body(session)


@pytest.mark.slow
class TestTheServerStarts:
    def test_it_completes_a_handshake_and_names_itself(self, tmp_path):
        async def body(session):
            return (await session.list_tools()).tools

        tools = asyncio.run(_talk(tmp_path, body))
        assert {t.name for t in tools} == {t["name"] for t in TOOLS}

    def test_every_tool_reaches_the_client_with_its_schema(self, tmp_path):
        """A schema that does not survive the wire is a tool a model cannot use."""

        async def body(session):
            return (await session.list_tools()).tools

        for tool in asyncio.run(_talk(tmp_path, body)):
            assert tool.description.strip()
            assert tool.input_schema["type"] == "object"

    def test_a_call_returns_the_payload(self, tmp_path):
        async def body(session):
            return await session.call_tool("describe_schema", {})

        result = asyncio.run(_talk(tmp_path, body))
        assert result.is_error is False
        assert '"kinds"' in result.content[0].text

    def test_a_failed_call_is_flagged_rather_than_thrown(self, tmp_path):
        """The payload stays readable -- the model corrects itself from it -- but the
        client is told it was a failure rather than an answer.
        """

        async def body(session):
            return await session.call_tool("get_note", {"title": "No such note"})

        result = asyncio.run(_talk(tmp_path, body))
        assert result.is_error is True
        assert '"ok": false' in result.content[0].text
