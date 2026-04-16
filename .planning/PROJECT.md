# Cocos RAG — AI 编程助手知识库

## What This Is

为 Cocos Creator 3.7.3 和 3.8.8 构建的 RAG（检索增强生成）系统。通过爬取官方中文文档并建立向量索引，以 MCP Server 形式暴露检索接口，让 Claude 等 AI 编程助手能够准确回答 Cocos 开发问题。

## Core Value

AI 能通过自然语言准确检索到对应版本的 Cocos 官方文档片段，辅助开发者解决 Cocos 编程问题。

## Requirements

### Validated

(None yet — ship to validate)

### Active

- [ ] 爬取 docs.cocos.com 的 3.7.3 和 3.8.8 中文文档
- [ ] 对文档进行清洗、分块（chunking）处理
- [ ] 使用 OpenAI text-embedding-3 生成向量嵌入
- [ ] 将向量存入 Chroma 向量数据库，按版本分开索引
- [ ] 实现 `search_cocos_docs(query, version)` MCP 工具
- [ ] 构建 MCP Server，可供 Claude/OpenCode 调用
- [ ] 提供文档索引构建脚本（爬取 → 向量化 → 入库）

### Out of Scope

- 英文文档索引 — 优先中文，节省 embedding 成本
- `get_api_reference` / `list_cocos_topics` / `compare_versions` 工具 — v1 仅做核心搜索，其余工具后续迭代
- Web UI / 聊天界面 — 只做 MCP 服务，不做前端
- 实时文档同步 — 定期手动重建索引即可

## Context

- Cocos 官方文档：https://docs.cocos.com/creator/3.8/zh/  和 https://docs.cocos.com/creator/3.7/zh/
- 技术栈：Python + LangChain（或 LlamaIndex）+ Chroma + MCP Python SDK
- 文档结构：Gitbook 风格，多层目录，需要递归爬取
- 两个版本文档结构相似但内容有差异，分开索引便于版本隔离查询

## Constraints

- **Embedding**: OpenAI text-embedding-3-small/large — 需要有效的 OpenAI API Key
- **向量库**: Chroma — 嵌入式运行，无需独立部署服务
- **语言**: Python 3.10+ 
- **MCP**: 遵循 MCP (Model Context Protocol) 规范，使用官方 Python SDK
- **爬虫**: 遵守 robots.txt，控制请求频率避免封禁

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| 分版本索引（3.7.3 vs 3.8.8） | 用户需要指定版本查询，避免版本混淆 | — Pending |
| 使用 Chroma 嵌入式向量库 | 无需部署独立服务，开发和使用简单 | — Pending |
| 中文文档为主 | 目标用户为中文开发者，减少 embedding 成本 | — Pending |
| OpenAI text-embedding-3 | 中文支持好，质量高，有成熟的 LangChain 集成 | — Pending |
| 以 MCP Server 形式暴露 | 与 Claude/OpenCode 等 AI 工具原生集成 | — Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-04-16 after initialization*
