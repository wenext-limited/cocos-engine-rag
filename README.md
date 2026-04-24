# Cocos RAG — AI 编程助手知识库

为 Cocos Creator 3.7.3 / 3.8.8 构建的双源 RAG（检索增强生成）系统：

- **官方中文文档**（`docs.cocos.com`）— 适合"怎么用 / 有什么概念 / API 概览"类问题
- **引擎源码（TypeScript + C++）**— 适合"具体方法签名 / 实现细节 / 文档没写清楚"类问题

通过 MCP Server 同时暴露 `search_cocos_docs` 和 `search_cocos_source` 两个工具，让 Claude / OpenCode 等 AI 编程助手按需选择。检索采用 **BM25 + 向量混合召回 + RRF 融合 + 可选 LLM Rerank** 三段流水线，对中英混合查询都有较好排序质量。

---

## 目录

- [技术栈](#技术栈)
- [项目结构](#项目结构)
- [完整数据流](#完整数据流)
- [快速开始](#快速开始)
- [模块说明](#模块说明)
- [MCP Server 接入](#mcp-server-接入)
- [测试](#测试)
- [已知问题](#已知问题)

---

## 技术栈

| 组件 | 技术 |
|------|------|
| 语言 | Python 3.12 |
| 包管理 | uv |
| 向量数据库 | ChromaDB（嵌入式持久化，无需独立部署） |
| Embedding 模型 | OpenAI `text-embedding-3-small` |
| 关键词检索 | `rank-bm25`（中文按字、英文按词分词） |
| 融合策略 | Reciprocal Rank Fusion (RRF) |
| Rerank（可选） | OpenAI `gpt-5.4-mini`（默认开启，可关闭） |
| 源码解析 | tree-sitter（`tree-sitter-typescript` + `tree-sitter-cpp`） |
| MCP SDK | `mcp>=1.27.0`（FastMCP，stdio transport） |
| HTML 解析 | BeautifulSoup4 |
| HTTP 爬虫 | requests + urllib3 Retry |

---

## 项目结构

```
cocos_rag/
├── src/
│   ├── crawler.py          # 文档爬虫（BFS + 断点续传）
│   ├── parser.py           # HTML 解析与文本分块（文档）
│   ├── indexer.py          # 文档向量化入库
│   ├── code_parser.py      # 引擎源码 AST 分块（tree-sitter）
│   ├── code_indexer.py     # 源码向量化入库
│   ├── server.py           # MCP Server 入口（暴露两个 tool）
│   └── core/
│       ├── config.py       # 环境变量加载
│       ├── db.py           # ChromaDB 客户端初始化
│       ├── embedding.py    # OpenAI 嵌入服务
│       ├── vector_store.py # ChromaDB 向量存储管理
│       ├── search.py       # SearchService + CodeSearchService（hybrid + rerank）
│       └── reranker.py     # LLM Reranker（gpt-4o-mini）
├── tests/                  # 单元测试
├── test_search.py          # 文档检索 E2E 验证
├── test_code_search.py     # 源码检索 E2E 验证
├── test_code_parser.py     # 解析器稳定性测试（子进程 + 硬超时）
├── test_full_engine_parse.py # 全量引擎解析（带 watchdog）
├── .data/                  # 数据目录（gitignored）
│   ├── raw/                # 原始文档 HTML
│   ├── engine/             # 引擎源码 git clone
│   │   ├── 3.7.3/
│   │   └── 3.8.8/
│   ├── processed/
│   │   ├── chunks_*.jsonl       # 文档分块
│   │   └── code_chunks_*.jsonl  # 源码分块
│   └── chroma_db/          # ChromaDB 持久化
├── run_mcp.bat             # Windows 快速启动脚本
├── claude_desktop_config.json.sample
├── .env.example
└── pyproject.toml
```

---

## 完整数据流

### 离线构建

```
 ──── 文档侧 ──────────────────────────────────────────────
docs.cocos.com/creator/3.7|3.8/manual/zh/
        ↓  src/crawler.py（BFS + 限速 + 断点续传）
.data/raw/{3.7.3,3.8.8}/*.html
        ↓  src/parser.py（HTML 清洗 → Markdown → 按标题分块）
.data/processed/chunks_{version}.jsonl
        ↓  src/indexer.py（OpenAI text-embedding-3-small）
.data/chroma_db/  collection: cocos_{version}

 ──── 源码侧 ──────────────────────────────────────────────
github.com/cocos/cocos-engine （git clone --depth 1 --branch <tag>）
        ↓
.data/engine/{3.7.3,3.8.8}/
        ↓  src/code_parser.py（tree-sitter AST 级分块）
.data/processed/code_chunks_{version}.jsonl
        ↓  src/code_indexer.py（OpenAI text-embedding-3-small）
.data/chroma_db/  collection: code_{version}
```

### 运行时检索

```
用户查询
   ↓
src/server.py（MCP @tool）
   ↓
search_cocos_docs           |  search_cocos_source
↓                           |  ↓
SearchService               |  CodeSearchService
   ↓                        |     ↓
BM25 召回 + 向量召回         |  BM25 召回 + 向量召回（支持 language / class_name 过滤）
   ↓                        |     ↓
RRF 融合（top 4×k 候选）    |  RRF 融合（top 4×k 候选）
   ↓                        |     ↓
（可选）LLM Rerank          |  （可选）LLM Rerank（gpt-5.4-mini，默认开启）
   ↓                        |     ↓
Top-K 结果（JSON）          |  Top-K 结果（含 GitHub 行级链接）
```

---

## 快速开始

### 1. 安装依赖

```powershell
uv sync
```

### 2. 配置环境变量

```powershell
Copy-Item .env.example .env
# 编辑 .env，填入有效的 OPENAI_API_KEY
```

可选环境变量：

| 变量 | 默认 | 说明 |
|------|------|------|
| `OPENAI_API_KEY` | — | 必填 |
| `OPENAI_RERANK_MODEL` | `gpt-4o-mini` (已修改为 `gpt-5.4-mini`) | LLM Rerank 使用的模型 |
| `COCOS_RAG_RERANK` | `1` | 设为 `0` 全局关闭 LLM Rerank |

### 3. 文档侧（已有数据可跳过）

```powershell
# 爬取 + 解析（断点续传）
uv run src/crawler.py
uv run src/parser.py

# 向量化入库
uv run src/indexer.py                    # 全部版本
uv run src/indexer.py --version 3.8.8    # 单版本
```

### 4. 源码侧

```powershell
# 1) 克隆引擎源码（注意：3.8.8 用 v3.8.8，3.7.3 只有 tag 3.7.3）
git clone --depth 1 --branch v3.8.8 https://github.com/cocos/cocos-engine.git .data/engine/3.8.8
git clone --depth 1 --branch 3.7.3  https://github.com/cocos/cocos-engine.git .data/engine/3.7.3

# 2) AST 分块（带子进程超时保护，约 8s/版本）
uv run python test_full_engine_parse.py 3.8.8 3.7.3

# 3) 向量化入库（首次约 6-12 分钟/版本，支持断点续传）
uv run src/code_indexer.py --version 3.8.8
uv run src/code_indexer.py --version 3.7.3
```

### 5. 启动 MCP Server

```powershell
# Windows
.\run_mcp.bat

# 或手动
$env:PYTHONPATH="src"; uv run python -m src.server
```

---

## 模块说明

### `src/crawler.py` — 文档爬虫

BFS 爬取 docs.cocos.com 指定版本的中文文档。

- 限速 `sleep(0.5)`、自动重试 5 次（指数退避）
- 跳过非文档资源（图片、压缩包等）
- 严格按 `version_prefix` 过滤，不跨版本
- 已存在的本地 HTML 直接读取，跳过下载

### `src/parser.py` — HTML 解析与分块

清洗 HTML、按 H1~H6 标题层级切割为 chunks，输出 JSONL。

- 移除 `nav / header / footer / script / style / aside` 等无关元素
- 主内容优先级：`<main>` → `.content` → `<article>` → `.book-body`
- 标题转 Markdown（`#`~`######`），维护 breadcrumbs 栈记录层级
- 超长块自动二次切割（4000 字符），追加 `Part N` 标记

### `src/indexer.py` — 文档向量化入库

读取 JSONL，调用 OpenAI `text-embedding-3-small` 生成向量后写入 `cocos_{version}` collection。

- Chunk ID = `md5(url) + md5(content)`，幂等
- 嵌入文本将 breadcrumbs 编入开头，提升检索精度
- 已入库的 chunk 自动跳过

### `src/code_parser.py` — 源码 AST 分块

使用 tree-sitter 把每个 `.ts / .cpp / .h / .hpp / .cc` 文件切成语义单元（class_summary、method、function、enum、interface、type_alias）。

**关键设计**：

- **显式递归 + 熔断**：每文件最多遍历 500k AST 节点 / 产出 5k chunk，避免病态嵌套打挂进程
- **JSDoc / Doxygen 解析**：提取 `@en / @zh / @param / @returns / @example / @deprecated`，对中英文双语注释完美适配
- **过滤 noise**：跳过 `@internal / @engineInternal` 标注的内部 API、跳过 `__` 开头的私有方法、跳过 C++ 前向声明（`class Foo;`，无 body）
- **embedding_text 设计**：模块路径 + 类名 + 方法名 + 中英文描述 + signature + params + returns，对自然语言查询召回率高
- **raw_code 截断保留**：每条 chunk 同时存最多 3000 字符的原始代码，方便 AI 直接读到实现

输出：`.data/processed/code_chunks_{version}.jsonl`

### `src/code_indexer.py` — 源码向量化入库

类似 `indexer.py`，但目标 collection 是 `code_{version}`。元数据保留 `chunk_type / class_name / method_name / signature / language / file_path / line_start / line_end / raw_code` 等，供检索时构造 GitHub 链接和 metadata 过滤。

### `src/core/embedding.py` — 嵌入服务

封装 OpenAI Embeddings API。动态批处理（每批 ≤100 条 & ≤100k 字符），批次失败时回退到逐条嵌入，带速率控制。

### `src/core/search.py` — 检索服务

提供两个 service，共用 hybrid 流水线：

| Service | Collection | 用途 |
|---|---|---|
| `SearchService` | `cocos_{version}` | 文档检索 |
| `CodeSearchService` | `code_{version}` | 源码检索（额外支持 `language` / `class_name` 过滤） |

**Hybrid 流水线**：

1. **向量召回**：query embedding → ChromaDB HNSW，取 `4×top_k` 候选
2. **BM25 召回**：tokenize（英文按词、中文按字）→ `rank_bm25.BM25Okapi` 全量打分，取相同数量候选
   - BM25 索引按 collection 缓存在内存中，首次查询会全量拉取一次（~40k 文档约几秒）
3. **RRF 融合**：`score = Σ 1 / (k + rank_i)`，k=60
4. **（可选）LLM Rerank**：将融合后的候选连同 query 一并发给 `gpt-5.4-mini`，要求按 0~10 打分；最终分数 = `0.7 × LLM 分 + 0.3 × 检索分`，重新排序后截断到 top_k

Rerank 默认开启，可通过环境变量 `COCOS_RAG_RERANK=0` 全局关闭，或在 `CodeSearchService.search(rerank=False)` 单次禁用。

### `src/core/reranker.py` — LLM Reranker

零额外依赖（共用 OpenAI 客户端）的轻量 reranker：

- 单次调用即可对全部候选打分（成本约 0.001 美元/次）
- 跨语言能力强（中英混合 query 表现稳定）
- 失败时自动降级为仅使用检索分数，不影响主链路
- 接口设计为 `Reranker.rerank(query, candidates, top_k)`，未来可平滑替换为本地 cross-encoder（如 `BAAI/bge-reranker-base`）

### `src/server.py` — MCP Server

使用 FastMCP（stdio transport）暴露两个工具：

#### `search_cocos_docs(query, version="3.8.8", top_k=5)`

适用场景：

- "如何使用 XX 组件" / "XX 是什么概念" / "怎么实现 XX 功能"
- 概览、入门、使用示例、配置说明

返回格式：

```json
{
  "status": "success",
  "query": "如何播放音频",
  "version": "3.8.8",
  "results": [
    {
      "content": "文档块内容…",
      "source_url": "https://docs.cocos.com/...",
      "section_title": "AudioSource 组件参考 > 属性",
      "relevance_score": 0.856,
      "version": "3.8.8"
    }
  ]
}
```

#### `search_cocos_source(query, version="3.8.8", top_k=5, language="all", class_name="")`

适用场景：

- "XX 方法的具体签名 / 参数" / "XX 类有哪些方法"
- 文档没写清楚的实现细节、源码级别的行为分析

参数：

- `language`：`"typescript"` / `"cpp"` / `"all"`（默认 all）
- `class_name`：可选，限制到具体类（如 `"Node"`, `"Sprite"`）

返回格式：

```json
{
  "status": "success",
  "query": "Node addChild",
  "version": "3.8.8",
  "results": [
    {
      "content": "addChild(child: Node): void { … }",     // raw_code 片段
      "embedding_text": "Module: cocos/scene-graph/node.ts\nClass: Node\nMethod: addChild\n…",
      "source_url": "https://github.com/cocos/cocos-engine/blob/3.8.8/cocos/scene-graph/node.ts#L624",
      "file_path": "cocos/scene-graph/node.ts",
      "chunk_type": "method",
      "class_name": "Node",
      "method_name": "addChild",
      "signature": "addChild(child: Node): void",
      "language": "typescript",
      "relevance_score": 0.381,
      "rerank_score": 1.0,
      "llm_score": 10.0,
      "version": "3.8.8"
    }
  ]
}
```

日志写入 `mcp_server.log`（不输出到 stdout，避免污染 MCP 协议）。

---

## MCP Server 接入

### Claude Desktop

配置文件路径：

- **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`
- **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`

```json
{
  "mcpServers": {
    "cocos-rag": {
      "command": "uv",
      "args": ["run", "python", "-m", "src.server"],
      "env": {
        "PYTHONPATH": "src",
        "OPENAI_API_KEY": "YOUR_OPENAI_API_KEY"
        "OPENAI_RERANK_MODEL": "gpt-5.4-mini",
        "PYTHONIOENCODING": "utf-8"
      },
      "cwd": "C:\\path\\to\\cocos_rag"
    }
  }
}
```

### OpenCode / 其他 MCP 客户端

参见 `claude_desktop_config.json.sample`，配置方式相同。

### 给 AI 的使用提示

可以在系统提示中加入工具选择指引：

> 回答 Cocos Creator 相关问题时：
> - 概念/教程/使用示例 → 用 `search_cocos_docs`
> - 具体 API 签名 / 实现细节 / 文档没写清楚 → 用 `search_cocos_source`
> - 不确定时两个都查一下，源码可以验证文档的说法

---

## 测试

### 单元测试

```powershell
uv run pytest
```

| 测试文件 | 覆盖内容 |
|----------|---------|
| `tests/test_infra.py` | 基础设施：文件存在性、ChromaDB 客户端 |
| `tests/test_parser.py` | HTML 清洗、分块、面包屑提取 |
| `tests/test_embedding.py` | 嵌入服务（mock OpenAI API） |
| `tests/test_vector_store.py` | ChromaDB collection 创建与文档增删 |

### 集成 / 端到端

```powershell
# 文档检索手动验证
uv run python test_search.py

# 源码检索 E2E（带 LLM rerank，默认 ON）
uv run python test_code_search.py
$env:RERANK="0"; uv run python test_code_search.py   # 关闭 rerank 对照

# 解析器稳定性测试（每个用例都在子进程 + 硬超时下运行，绝不会锁死本机）
uv run python test_code_parser.py

# 全量引擎解析烟雾测试（带 10 分钟硬超时）
uv run python test_full_engine_parse.py 3.8.8 3.7.3
```

`test_code_search.py` 内置 7 条真实 Cocos 查询作为相关性回归基线，全部命中期望关键词时输出 `ALL OK`。

---

## 已知问题

- **首次源码搜索较慢**：`CodeSearchService` 启动后第一次查询会全量构建该 collection 的 BM25 索引（~4 万文档约 3-5 秒），后续查询走内存缓存，单次延迟 < 1s（不含 rerank）。
- **LLM Rerank 增加延迟**：每次查询额外 1~3 秒、约 0.001 美元成本。如对延迟敏感可关闭：`COCOS_RAG_RERANK=0`。
- **Chroma HNSW 索引偶发损坏**：indexer 进程中途被 kill 时可能在 `.data/chroma_db/` 留下半成品 segment，表现为 `count()` / `query()` 抛 `Error loading hnsw index`。恢复方式：
  ```powershell
  uv run python -c "import sys; sys.path.insert(0,'src'); from core.config import load_env; load_env(); from core.vector_store import VectorStoreManager; VectorStoreManager().delete_collection('code_3_7_3')"
  uv run src/code_indexer.py --version 3.7.3
  ```
- **PowerShell 控制台中文乱码**：终端默认 GBK 编码下打印 UTF-8 中文会显示乱码，但 ChromaDB 中存储的内容、MCP 返回给 AI 的 JSON 始终是正确的 UTF-8。如需在终端正常显示：`chcp 65001`。
- **`main.py` 为占位符**：仅输出 `Hello from cocos-rag!`，实际业务逻辑均在 `src/` 中。
