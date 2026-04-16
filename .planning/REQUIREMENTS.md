# Requirements — Cocos RAG

## v1 Requirements

### DOC — 文档爬取与处理

- [ ] **DOC-01**: 系统能爬取 docs.cocos.com 3.7.3 中文版所有文档页面
- [ ] **DOC-02**: 系统能爬取 docs.cocos.com 3.8.8 中文版所有文档页面
- [ ] **DOC-03**: 爬虫遵守请求频率限制（delay/retry），避免被封禁
- [ ] **DOC-04**: 将 HTML 页面解析为干净的 Markdown/纯文本（去掉导航栏、广告、无关内容）
- [ ] **DOC-05**: 对文档文本进行分块（chunk），每块保留标题上下文
- [ ] **DOC-06**: 保存原始爬取数据到本地（支持重新处理，无需重复爬取）

### EMB — 向量化

- [ ] **EMB-01**: 使用 OpenAI text-embedding-3-small 为每个文档块生成向量嵌入
- [ ] **EMB-02**: 嵌入过程支持断点续传（避免 API 中途失败重头来过）
- [ ] **EMB-03**: 向量数据存入 Chroma，3.7.3 和 3.8.8 分别存入独立 collection

### SEARCH — 检索

- [ ] **SEARCH-01**: 根据自然语言 query 和指定版本，返回 Top-K 相关文档片段
- [ ] **SEARCH-02**: 返回结果包含：文档片段内容、来源 URL、所属章节标题
- [ ] **SEARCH-03**: 支持不指定版本时默认查询最新版（3.8.8）

### MCP — 服务接口

- [ ] **MCP-01**: 构建符合 MCP 规范的 Python Server
- [ ] **MCP-02**: 暴露 `search_cocos_docs(query: str, version: str = "3.8.8", top_k: int = 5)` 工具
- [ ] **MCP-03**: MCP Server 可通过 stdio 启动（兼容 Claude Desktop / OpenCode MCP 配置）
- [ ] **MCP-04**: 工具调用返回结构化结果（JSON），AI 能直接使用

### INFRA — 基础设施 & 脚本

- [x] **INFRA-01**: 提供一键构建索引脚本（爬取 → 清洗 → 向量化 → 入库）
- [x] **INFRA-02**: 提供 README，说明如何配置 OpenAI Key、运行爬虫、启动 MCP Server
- [x] **INFRA-03**: 依赖管理（requirements.txt 或 pyproject.toml）

## v2 Requirements（延后）

- `get_api_reference(class_name, version)` — 根据类名/函数名精确查 API
- `list_cocos_topics(version)` — 列出文档目录结构
- `compare_versions(topic, v1, v2)` — 对比两版本差异
- 英文文档索引支持
- 定时自动重建索引

## Out of Scope

- Web UI / 聊天界面 — 仅做 MCP 服务层，不做前端
- 多租户 / 权限控制 — 本地工具，无需鉴权
- 生产级部署（Docker、K8s）— 本地开发环境即可

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| INFRA-01 | Phase 1: Infrastructure & Project Scaffold | Complete |
| INFRA-02 | Phase 1: Infrastructure & Project Scaffold | Complete |
| INFRA-03 | Phase 1: Infrastructure & Project Scaffold | Complete |
| DOC-01 | Phase 2: Document Crawling | Pending |
| DOC-02 | Phase 2: Document Crawling | Pending |
| DOC-03 | Phase 2: Document Crawling | Pending |
| DOC-06 | Phase 2: Document Crawling | Pending |
| DOC-04 | Phase 3: Document Parsing & Chunking | Pending |
| DOC-05 | Phase 3: Document Parsing & Chunking | Pending |
| EMB-01 | Phase 4: Embedding & Vector Storage | Pending |
| EMB-02 | Phase 4: Embedding & Vector Storage | Pending |
| EMB-03 | Phase 4: Embedding & Vector Storage | Pending |
| SEARCH-01 | Phase 5: Search Service | Pending |
| SEARCH-02 | Phase 5: Search Service | Pending |
| SEARCH-03 | Phase 5: Search Service | Pending |
| MCP-01 | Phase 6: MCP Server | Pending |
| MCP-02 | Phase 6: MCP Server | Pending |
| MCP-03 | Phase 6: MCP Server | Pending |
| MCP-04 | Phase 6: MCP Server | Pending |
