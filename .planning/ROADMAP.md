# ROADMAP — Cocos RAG

> RAG system for Cocos Creator docs (3.7.3 + 3.8.8), exposing semantic search via MCP Server.

## Phases

- [x] **Phase 1: Infrastructure & Project Scaffold** — Dependency management, build scripts, and README foundation (completed 2026-04-16)
- [x] **Phase 2: Document Crawling** — Crawl all pages for both doc versions with rate limiting and raw storage (completed 2026-04-16)
- [ ] **Phase 3: Document Parsing & Chunking** — Clean HTML to text, split into searchable chunks with metadata
- [ ] **Phase 4: Embedding & Vector Storage** — Generate OpenAI embeddings with resume support, store in Chroma
- [ ] **Phase 5: Search Service** — Natural language semantic search returning ranked chunks with source metadata
- [ ] **Phase 6: MCP Server** — MCP-compliant server exposing search_cocos_docs tool via stdio

---

## Phase Details

### Phase 1: Infrastructure & Project Scaffold
**Goal**: Developer can install dependencies, understand the project, and run a no-op build pipeline
**Depends on**: Nothing (first phase)
**Requirements**: INFRA-01, INFRA-02, INFRA-03
**Success Criteria** (what must be TRUE):
  1. `pip install -r requirements.txt` (or `pip install -e .`) completes without errors
  2. README explains how to set OPENAI_API_KEY, run the crawler, and start the MCP server
  3. A top-level `build_index.py` (or similar) script exists and prints a usage/help message
  4. Project directory structure is documented and consistent with the codebase
**Plans**:
- [x] 01-01-PLAN.md — Initialize Project and Dependencies
- [x] 01-02-PLAN.md — Create Skeleton Scripts and Tests

### Phase 2: Document Crawling
**Goal**: Both versions of Cocos Creator docs are fully crawled and saved locally
**Depends on**: Phase 1
**Requirements**: DOC-01, DOC-02, DOC-03, DOC-06
**Success Criteria** (what must be TRUE):
  1. Running the crawler produces local files covering all pages of the 3.7.3 docs
  2. Running the crawler produces local files covering all pages of the 3.8.8 docs
  3. Crawler respects a configurable delay between requests and retries on failures
  4. Raw crawl output is saved to disk — re-running the pipeline never re-crawls unless explicitly forced
  5. Crawl can be resumed after interruption without re-downloading already-saved pages
**Plans**:
- [x] 02-01-PLAN.md — Document Crawler Implementation
- [x] 02-02-PLAN.md — Add Network Retry Logic (Gap Closure)

### Phase 3: Document Parsing & Chunking
**Goal**: Raw crawl data is transformed into clean, structured text chunks ready for embedding
**Depends on**: Phase 2
**Requirements**: DOC-04, DOC-05
**Success Criteria** (what must be TRUE):
  1. Each raw HTML page is parsed to clean Markdown/plaintext with navigation, ads, and chrome removed
  2. Parsed text is split into chunks, each chunk retaining its heading hierarchy (breadcrumb context)
  3. Each chunk carries metadata: source URL, version, section title
  4. Chunk output is inspectable as JSON/JSONL files on disk before embedding begins
**Plans**:
- [x] 03-01-PLAN.md — Document Parsing and Chunking

### Phase 4: Embedding & Vector Storage
**Goal**: All doc chunks have embeddings and are queryable in Chroma, version-isolated
**Depends on**: Phase 3
**Requirements**: EMB-01, EMB-02, EMB-03
**Success Criteria** (what must be TRUE):
  1. OpenAI text-embedding-3-small embeddings are generated for every chunk from both versions
  2. Embedding job can be interrupted and resumed — already-embedded chunks are not re-processed
  3. 3.7.3 chunks live in a dedicated Chroma collection separate from 3.8.8 chunks
  4. Chroma DB persists to disk and can be loaded in a fresh Python process without re-embedding
**Plans**:
- [x] 04-01-PLAN.md — Phase 4 Plan: Embedding & Vector Storage
- [x] 04-02-PLAN.md — Fix ChromaDB Persistence Directory (Gap Closure)

### Phase 5: Search Service
**Goal**: Given a natural language query and version, the system returns relevant doc chunks with full provenance
**Depends on**: Phase 4
**Requirements**: SEARCH-01, SEARCH-02, SEARCH-03
**Success Criteria** (what must be TRUE):
  1. `search("节点的生命周期", version="3.8.8", top_k=5)` returns 5 relevant chunks from the 3.8.8 collection
  2. Each result includes: chunk text, source URL, section title, relevance score
  3. Calling search without a version argument defaults to querying the 3.8.8 collection
  4. Querying a non-existent version returns a clear error rather than silently returning empty results
**Plans**: TBD

### Phase 6: MCP Server
**Goal**: Claude / OpenCode can discover and call search_cocos_docs via MCP stdio transport
**Depends on**: Phase 5
**Requirements**: MCP-01, MCP-02, MCP-03, MCP-04
**Success Criteria** (what must be TRUE):
  1. `python -m cocos_rag.server` (or equivalent) starts an MCP server on stdio without crashing
  2. MCP tool list includes `search_cocos_docs` with correct JSON Schema (query, version, top_k params)
  3. A Claude Desktop / OpenCode config snippet calling the server is documented and tested
  4. Tool call returns a JSON array of result objects that an LLM can read directly without post-processing
**Plans**: TBD

---

## Progress

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Infrastructure & Project Scaffold | 2/2 | Complete   | 2026-04-16 |
| 2. Document Crawling | 2/2 | Complete | 2026-04-16 |
| 3. Document Parsing & Chunking | 0/1 | Not started | - |
| 4. Embedding & Vector Storage | 1/2 | Planned | - |
| 5. Search Service | 0/? | Not started | - |
| 6. MCP Server | 0/? | Not started | - |

---

## Coverage Map

| Requirement | Phase |
|-------------|-------|
| INFRA-01 | Phase 1 |
| INFRA-02 | Phase 1 |
| INFRA-03 | Phase 1 |
| DOC-01 | Phase 2 |
| DOC-02 | Phase 2 |
| DOC-03 | Phase 2 |
| DOC-06 | Phase 2 |
| DOC-04 | Phase 3 |
| DOC-05 | Phase 3 |
| EMB-01 | Phase 4 |
| EMB-02 | Phase 4 |
| EMB-03 | Phase 4 |
| SEARCH-01 | Phase 5 |
| SEARCH-02 | Phase 5 |
| SEARCH-03 | Phase 5 |
| MCP-01 | Phase 6 |
| MCP-02 | Phase 6 |
| MCP-03 | Phase 6 |
| MCP-04 | Phase 6 |

**Coverage: 19/19 ✓**

---
*Created: 2026-04-16*
