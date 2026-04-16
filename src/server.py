import logging
from core.config import load_env
from mcp.server.fastmcp import FastMCP

load_env()
logging.basicConfig(level=logging.INFO, filename="mcp_server.log")

mcp = FastMCP("Cocos RAG Server")


@mcp.tool()
def search_cocos_docs(query: str, version: str = "3.8.8", top_k: int = 5) -> str:
    """Search Cocos documentation."""
    return f"Mock results for {query} in {version}"


if __name__ == "__main__":
    mcp.run()
