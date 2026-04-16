---
phase: "03"
plan: "03-01"
subsystem: "parser"
tags: ["html", "chunking", "parsing"]
requires: ["02-01"]
provides: ["04-01"]
affects: ["data"]
tech-stack: ["BeautifulSoup", "JSONL"]
key-files: ["src/parser.py", "tests/test_parser.py"]
key-decisions:
  - "Decided to use a simple recursive DOM text extraction with Markdown header injection instead of complex LLM or AST-based chunking."
  - "Chunks are separated precisely by heading hierarchy (H1-H6) to provide context for embedding."
metrics:
  duration: "10m"
  completed_date: "2026-04-16"
---

# Phase 03 Plan 01: Document Parsing & Chunking Summary

> Beautiful DOM-based extraction and recursive header tracking for context-aware text chunking.

## Overview
Implemented `src/parser.py` which takes raw HTML output from Phase 2, strips away irrelevant chrome (`<nav>`, `<header>`, `<footer>`, `<script>`, `<style>`), and linearly chunks content by markdown-style header injections. 

## Completed Tasks
- [x] Implemented HTML chrome cleaner using BeautifulSoup.
- [x] Implemented text extraction preserving header context as breadcrumbs.
- [x] Created batch processor reading from `.data/raw/*` and outputting `.data/processed/chunks_*.jsonl`.
- [x] Added unit tests for HTML cleaning and chunk generation (`tests/test_parser.py`).

## Technical Details
- Injected Markdown headers (`#`, `##`, etc.) into `<h*>` tags and newlines around block elements (`<p>`, `<div>`, `<ul>`, etc.) before calling `soup.get_text()`. This safely flattens nested tag hierarchies without merging disparate blocks or losing heading breaks.
- Breadcrumbs are tracked by popping back to the current header level, naturally replicating the document's structure without complex DOM traversal.
- Outputs clean `.jsonl` lines: `{"url": "...", "version": "...", "breadcrumbs": ["Title", "Subtitle"], "content": "..."}`.

## Deviations from Plan
- **None:** The plan was executed directly as written, though a simpler custom chunking logic was favored over importing LangChain due to the highly structured nature of the Cocos documentation.

## Next Steps
- Implement Phase 4 to read the generated `.jsonl` files, compute embeddings using OpenAI, and store them into ChromaDB.
