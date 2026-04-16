<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
None (No CONTEXT.md found for this phase)

### the agent's Discretion
None

### Deferred Ideas (OUT OF SCOPE)
None
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| INFRA-01 | 提供一键构建索引脚本（爬取 → 清洗 → 向量化 → 入库） | Provided skeleton structure in Architecture Patterns |
| INFRA-02 | 提供 README，说明如何配置 OpenAI Key、运行爬虫、启动 MCP Server | Standardized README pattern established |
| INFRA-03 | 依赖管理（requirements.txt 或 pyproject.toml） | `uv` package manager and `pyproject.toml` selected as Standard Stack |
</phase_requirements>

# Phase 1: Infrastructure & Project Scaffold - Research

**Researched:** 2026-04-16
**Domain:** Python Project Scaffolding, MCP Server Basics, Vector Database Setup
**Confidence:** HIGH

## Summary

This phase focuses on setting up a robust, modern Python project foundation for the Cocos RAG system. We will leverage `uv` for fast, reproducible dependency management and create the foundational entry points (MCP server and CLI data pipeline). The core technical decisions revolve around ensuring `mcp`, `chromadb`, and `langchain-openai` can co-exist and be easily invoked.

**Primary recommendation:** Use `uv` to initialize a `pyproject.toml` based setup. Create two main entry points: `src/server.py` for the MCP service and `src/indexer.py` for the data ingestion pipeline.

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `uv` | 0.9.29 | Dependency management | Blazing fast, reliable lockfiles, native Windows support |
| `mcp` | 1.27.0 | MCP Server implementation | Official Anthropic SDK for Model Context Protocol |
| `chromadb` | 1.5.7 | Vector database | Embedded, no external service required, native Python |
| `langchain-openai` | 1.1.13 | Embeddings | Official integration for `text-embedding-3-small` |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `python-dotenv` | 1.0.1 | Config management | Loading `OPENAI_API_KEY` from local `.env` file |
| `pytest` | 8.3.5 | Testing | Standard framework for ensuring imports and basic scripts work |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `uv` | `pip` + `requirements.txt` | `requirements.txt` is simpler but lacks robust lockfile and workspace capabilities. `uv` is installed and much faster. |

**Installation:**
```bash
uv init
uv add mcp chromadb langchain-openai python-dotenv
uv add --dev pytest
```

## Architecture Patterns

### Recommended Project Structure
```
D:\learn\cocos_rag\
├── .env.example        # Template for API keys
├── README.md           # Instructions for setup, indexing, and MCP
├── pyproject.toml      # Dependency and project config
├── uv.lock             # Reproducible builds
├── data/
│   └── chroma_db/      # Persistent storage for Chroma (git-ignored)
└── src/
    ├── __init__.py
    ├── indexer.py      # Entry point for INFRA-01 (crawl -> clean -> embed -> insert)
    ├── server.py       # Entry point for MCP-01 (stdio server)
    └── core/
        ├── config.py   # Env var loading
        └── db.py       # ChromaDB initialization logic
```

### Pattern 1: Embedded Chroma Initialization
**What:** Centralized Chroma client that can be used by both the indexer and the server.
**When to use:** Whenever interacting with the vector store.
**Example:**
```python
# src/core/db.py
import os
import chromadb
from chromadb.config import Settings

def get_chroma_client():
    # Persist in the project root under data/chroma_db
    persist_directory = os.path.join(os.path.dirname(os.path.dirname(__dirname)), "data", "chroma_db")
    return chromadb.PersistentClient(path=persist_directory, settings=Settings(anonymized_telemetry=False))
```

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| MCP Protocol | Custom stdio JSON-RPC parser | `mcp.server.FastMCP` | Official SDK handles message framing, tool registration, and error boundaries out of the box. |
| Vector math | Numpy cosine similarity scripts | `chromadb` | Built-in indexing, metadata filtering, and optimized native execution. |

## Common Pitfalls

### Pitfall 1: MCP Server Print Statements
**What goes wrong:** Adding `print("Starting server")` in `server.py` breaks the MCP connection.
**Why it happens:** MCP uses `stdio` (stdout/stdin) for JSON-RPC communication. Any standard print writes to stdout and corrupts the JSON stream.
**How to avoid:** Use the standard `logging` module and output to a file or `sys.stderr` for debugging the MCP server.

### Pitfall 2: Missing `.env` Handling
**What goes wrong:** API calls fail because `OPENAI_API_KEY` is not loaded into the environment when running `indexer.py` or the MCP server.
**Why it happens:** AI agents or external processes (like Claude Desktop) don't inherit terminal environment variables automatically.
**How to avoid:** Always call `load_dotenv()` at the very top of your entry points (`server.py` and `indexer.py`).

## Code Examples

### MCP Server Skeleton (INFRA-02 support)
```python
# src/server.py
from dotenv import load_dotenv
import logging

load_dotenv()
logging.basicConfig(level=logging.INFO, filename="mcp_server.log")

from mcp.server.fastmcp import FastMCP

# Create an MCP server
mcp = FastMCP("Cocos RAG Server")

@mcp.tool()
def search_cocos_docs(query: str, version: str = "3.8.8", top_k: int = 5) -> str:
    """Search Cocos documentation."""
    return f"Mock results for {query} in {version}"

if __name__ == "__main__":
    mcp.run()
```

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| `python` | Runtime | ✓ | 3.12.10 | — |
| `uv` | Dependency Management | ✓ | 0.9.29 | `pip` |
| `chromadb` | Vector Store | ✓ | 1.5.7 (via pip index) | — |

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8.3.5 |
| Config file | `pyproject.toml` |
| Quick run command | `uv run pytest -q` |
| Full suite command | `uv run pytest -v` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| INFRA-01 | Indexer script exists and can be imported | unit | `uv run pytest tests/test_infra.py::test_indexer_imports` | ❌ Wave 0 |
| INFRA-02 | README exists with setup instructions | unit | `uv run pytest tests/test_infra.py::test_readme_exists` | ❌ Wave 0 |
| INFRA-03 | pyproject.toml exists and deps resolve | unit | `uv run uv pip check` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `uv run pytest -q`
- **Per wave merge:** `uv run pytest -v`
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `tests/test_infra.py` — covers basic structural assertions
- [ ] Framework install: `uv add --dev pytest`

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - Extracted from `STATE.md` constraints and verified latest pip indices.
- Architecture: HIGH - Follows official `mcp` SDK patterns and `chromadb` local usage.
- Pitfalls: HIGH - stdio logging issues are the #1 cause of failure in MCP servers.

**Research date:** 2026-04-16
**Valid until:** 2026-05-16