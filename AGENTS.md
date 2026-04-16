<!-- GSD:project-start source:PROJECT.md -->
## Project

**Cocos RAG — AI 编程助手知识库**

为 Cocos Creator 3.7.3 和 3.8.8 构建的 RAG（检索增强生成）系统。通过爬取官方中文文档并建立向量索引，以 MCP Server 形式暴露检索接口，让 Claude 等 AI 编程助手能够准确回答 Cocos 开发问题。

**Core Value:** AI 能通过自然语言准确检索到对应版本的 Cocos 官方文档片段，辅助开发者解决 Cocos 编程问题。

### Constraints

- **Embedding**: OpenAI text-embedding-3-small/large — 需要有效的 OpenAI API Key
- **向量库**: Chroma — 嵌入式运行，无需独立部署服务
- **语言**: Python 3.10+ 
- **MCP**: 遵循 MCP (Model Context Protocol) 规范，使用官方 Python SDK
- **爬虫**: 遵守 robots.txt，控制请求频率避免封禁
<!-- GSD:project-end -->

<!-- GSD:stack-start source:STACK.md -->
## Technology Stack

Technology stack not yet documented. Will populate after codebase mapping or first phase.
<!-- GSD:stack-end -->

<!-- GSD:conventions-start source:CONVENTIONS.md -->
## Conventions

Conventions not yet established. Will populate as patterns emerge during development.
<!-- GSD:conventions-end -->

<!-- GSD:architecture-start source:ARCHITECTURE.md -->
## Architecture

Architecture not yet mapped. Follow existing patterns found in the codebase.
<!-- GSD:architecture-end -->

<!-- GSD:skills-start source:skills/ -->
## Project Skills

No project skills found. Add skills to any of: `.claude/skills/`, `.agents/skills/`, `.cursor/skills/`, or `.github/skills/` with a `SKILL.md` index file.
<!-- GSD:skills-end -->

<!-- GSD:workflow-start source:GSD defaults -->
## GSD Workflow Enforcement

Before using Edit, Write, or other file-changing tools, start work through a GSD command so planning artifacts and execution context stay in sync.

Use these entry points:
- `/gsd-quick` for small fixes, doc updates, and ad-hoc tasks
- `/gsd-debug` for investigation and bug fixing
- `/gsd-execute-phase` for planned phase work

Do not make direct repo edits outside a GSD workflow unless the user explicitly asks to bypass it.
<!-- GSD:workflow-end -->



<!-- GSD:profile-start -->
## Developer Profile

> Profile not yet configured. Run `/gsd-profile-user` to generate your developer profile.
> This section is managed by `generate-claude-profile` -- do not edit manually.
<!-- GSD:profile-end -->
