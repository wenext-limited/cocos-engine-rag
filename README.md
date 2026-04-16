# Cocos RAG — AI 编程助手知识库

为 Cocos Creator 3.7.3 和 3.8.8 构建的 RAG（检索增强生成）系统。通过 MCP Server 提供检索接口，辅助 AI 编程助手回答开发问题。

## Setup

1. Install dependencies:
   ```bash
   uv sync
   # or
   uv pip install
   ```

2. Configure environment variables:
   Copy `.env.example` to `.env` and add your OpenAI API Key.
   ```bash
   cp .env.example .env
   ```
   *Edit `.env` and set `OPENAI_API_KEY` to your valid key.*

## Project Structure

```text
cocos_rag/
├── src/          # Source code for crawler, indexer, and MCP server
├── tests/        # Pytest test cases
├── data/         # Data directory for ChromaDB storage
├── .env.example  # Environment variables template
├── pyproject.toml# Project dependencies and config
└── README.md     # Project documentation
```

## Indexing

To run the document crawler and indexer into ChromaDB:

```bash
uv run src/indexer.py
```

## MCP Server

To start the MCP Server (stdio transport for Claude Desktop / OpenCode):

```bash
uv run src/server.py
```