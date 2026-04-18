"""
MCP Server for Cocos Creator RAG.

Exposes two tools:
  - search_cocos_docs: Search official documentation
  - search_cocos_source: Search engine source code (TypeScript + C++)

Both use hybrid search (BM25 + vector) for improved accuracy.
"""

import logging
import os
import json
from core.config import load_env
from mcp.server.fastmcp import FastMCP
from core.search import SearchService, CodeSearchService

load_env()
logging.basicConfig(level=logging.INFO, filename="mcp_server.log")

mcp = FastMCP("Cocos RAG Server")
api_key = os.environ.get("OPENAI_API_KEY")
if not api_key:
    logging.warning("OPENAI_API_KEY not set — searches will fail")

search_service = SearchService(api_key=api_key)
code_search_service = CodeSearchService(api_key=api_key)


def fix_encoding(text: str) -> str:
    """Helper to fix latin-1 mojibake if present in the text."""
    if not text:
        return text
    try:
        return text.encode("latin-1").decode("utf-8")
    except Exception:
        return text


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

        # Fix encoding issues in the results
        fixed_results = []
        for r in results:
            fixed_results.append(
                {
                    "content": fix_encoding(r.get("content", "")),
                    "source_url": fix_encoding(r.get("source_url", "")),
                    "section_title": fix_encoding(r.get("section_title", "")),
                    "relevance_score": r.get("relevance_score", 0.0),
                    "version": r.get("version", version),
                }
            )

        return json.dumps(
            {
                "status": "success",
                "query": query,
                "version": version,
                "results": fixed_results,
            },
            ensure_ascii=False,
            indent=2,
        )

    except Exception as e:
        logging.error(f"Error in search_cocos_docs: {e}")
        return json.dumps({"status": "error", "message": str(e)})


@mcp.tool()
def search_cocos_source(
    query: str,
    version: str = "3.8.8",
    top_k: int = 5,
    language: str = "all",
    class_name: str = "",
) -> str:
    """
    Search Cocos Creator engine source code (TypeScript + C++).

    Use this tool to find API implementations, class definitions, method signatures,
    and inline documentation from the Cocos Creator engine source code.
    This complements the documentation search by providing actual code context.

    Args:
        query: The search query string (e.g., "Node getComponent", "physics raycast").
        version: The Cocos Creator version ('3.8.8' or '3.7.3'). Default is '3.8.8'.
        top_k: Number of results to return. Default is 5.
        language: Filter by language: 'typescript', 'cpp', or 'all'. Default is 'all'.
        class_name: Optional: restrict search to a specific class (e.g., 'Node', 'Sprite').

    Returns:
        JSON string containing matching source code chunks with metadata.
    """
    try:
        results = code_search_service.search(
            query=query,
            version=version,
            top_k=top_k,
            language=language if language != "all" else None,
            class_name=class_name if class_name else None,
        )

        if not results:
            return json.dumps(
                {"status": "success", "message": "No results found.", "results": []}
            )

        formatted_results = []
        for r in results:
            formatted_results.append(
                {
                    "content": r.get("content", ""),
                    "source_url": r.get("source_url", ""),
                    "file_path": r.get("file_path", ""),
                    "chunk_type": r.get("chunk_type", ""),
                    "class_name": r.get("class_name", ""),
                    "method_name": r.get("method_name", ""),
                    "signature": r.get("signature", ""),
                    "language": r.get("language", ""),
                    "relevance_score": r.get("relevance_score", 0.0),
                    "version": r.get("version", version),
                }
            )

        return json.dumps(
            {
                "status": "success",
                "query": query,
                "version": version,
                "language": language,
                "class_name": class_name,
                "results": formatted_results,
            },
            ensure_ascii=False,
            indent=2,
        )

    except Exception as e:
        logging.error(f"Error in search_cocos_source: {e}")
        return json.dumps({"status": "error", "message": str(e)})


def main_server():
    """Run the server."""
    transport = os.environ.get("TRANSPORT", "stdio")
    if transport == "sse":
        port = int(os.environ.get("PORT", "8000"))
        
        import uvicorn
        
        starlette_app = mcp.sse_app(None)
        uvicorn.run(
            starlette_app,
            host="0.0.0.0",
            port=port,
            log_level="info",
        )
    else:
        mcp.run()


if __name__ == "__main__":
    main_server()
