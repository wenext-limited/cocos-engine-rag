import logging
import json
from core.config import load_env
from mcp.server.fastmcp import FastMCP
from core.search import SearchService

load_env()
logging.basicConfig(level=logging.INFO, filename="mcp_server.log")

mcp = FastMCP("Cocos RAG Server")
search_service = SearchService()


@mcp.tool()
def search_cocos_docs(query: str, version: str = "3.8.8", top_k: int = 5) -> str:
    """
    Search Cocos Creator documentation using RAG.

    Args:
        query: The search query string.
        version: The Cocos Creator version ('3.8.8' or '3.7.3'). Default is '3.8.8'.
        top_k: Number of results to return. Default is 5.

    Returns:
        JSON string containing the top relevant chunks.
    """
    try:
        results = search_service.search(query=query, version=version, top_k=top_k)

        if not results:
            return json.dumps(
                {"status": "success", "message": "No results found.", "results": []}
            )

        return json.dumps(
            {
                "status": "success",
                "query": query,
                "version": version,
                "results": results,
            },
            ensure_ascii=False,
            indent=2,
        )

    except Exception as e:
        logging.error(f"Error in search_cocos_docs: {e}")
        return json.dumps({"status": "error", "message": str(e)})


def stdio_server():
    """Run the server using stdio transport."""
    # FastMCP uses stdio by default when called without arguments
    mcp.run()


if __name__ == "__main__":
    stdio_server()
