"""`python -m planner.mcp` -- run the MCP server over stdio."""

import asyncio

from .server import serve

if __name__ == "__main__":
    asyncio.run(serve())
