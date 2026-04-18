"""
Search services for Cocos Creator RAG.

Provides two search services:
  - SearchService: searches documentation chunks (existing)
  - CodeSearchService: searches engine source code chunks (new)

Both support hybrid search (BM25 + vector) with Reciprocal Rank Fusion (RRF).
"""

import logging
import os
import re
from typing import List, Dict, Any, Optional
from rank_bm25 import BM25Okapi
from core.embedding import EmbeddingService
from core.vector_store import VectorStoreManager
from core.reranker import LLMReranker

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# BM25 tokenizer for mixed Chinese/English text
# ---------------------------------------------------------------------------


def tokenize(text: str) -> List[str]:
    """
    Simple tokenizer for mixed Chinese/English text.
    Splits on whitespace and punctuation, also splits Chinese text into
    individual characters (good enough for BM25 on CJK text).
    """
    if not text:
        return []
    # Split English words and CJK characters
    tokens = []
    # First extract English words and numbers
    for word in re.findall(r"[a-zA-Z_]\w*|[\u4e00-\u9fff]", text.lower()):
        tokens.append(word)
    return tokens


# ---------------------------------------------------------------------------
# Reciprocal Rank Fusion
# ---------------------------------------------------------------------------


def reciprocal_rank_fusion(
    ranked_lists: List[List[str]],
    scores_map: Dict[str, float],
    k: int = 60,
) -> List[str]:
    """
    Combine multiple ranked lists using RRF.
    ranked_lists: list of lists of document IDs, each ordered by relevance
    scores_map: unused in pure RRF but available for weighted variants
    k: RRF constant (default 60)
    Returns: merged list of document IDs sorted by fused score
    """
    rrf_scores: Dict[str, float] = {}
    for ranked_list in ranked_lists:
        for rank, doc_id in enumerate(ranked_list):
            rrf_scores[doc_id] = rrf_scores.get(doc_id, 0.0) + 1.0 / (k + rank + 1)

    sorted_ids = sorted(rrf_scores.keys(), key=lambda x: rrf_scores[x], reverse=True)
    return sorted_ids


# ---------------------------------------------------------------------------
# Documentation Search Service (enhanced with hybrid search)
# ---------------------------------------------------------------------------


class SearchService:
    """Search documentation chunks with hybrid BM25+vector search."""

    def __init__(self, api_key: str = None):
        self.embedding_service = EmbeddingService(api_key=api_key)
        self.vector_store = VectorStoreManager()
        self._bm25_cache: Dict[str, Any] = {}  # version -> (bm25, doc_ids, docs)

    def _get_bm25_index(self, version: str):
        """Build or retrieve cached BM25 index for a version's doc collection."""
        if version in self._bm25_cache:
            return self._bm25_cache[version]

        collection = self.vector_store.get_or_create_collection(version)
        # Fetch all documents for BM25 indexing
        all_data = collection.get(include=["documents"])

        if not all_data["ids"]:
            return None, [], []

        doc_ids = all_data["ids"]
        documents = all_data["documents"]

        # Tokenize all documents for BM25
        tokenized = [tokenize(doc) for doc in documents]
        bm25 = BM25Okapi(tokenized)

        self._bm25_cache[version] = (bm25, doc_ids, documents)
        return bm25, doc_ids, documents

    def search(
        self, query: str, version: str = "3.8.8", top_k: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Hybrid search: BM25 + vector, merged with RRF.
        Returns Top-K relevant chunks with content, source URL, and section title.
        """
        logger.info(
            f"Searching docs for '{query}' in version {version} (top_k={top_k})"
        )

        try:
            # Retrieve more candidates for fusion, then trim to top_k
            candidate_k = min(top_k * 4, 50)

            # --- Vector search path ---
            query_embedding = self.embedding_service.get_embeddings([query])[0]
            collection = self.vector_store.get_or_create_collection(version)

            vector_results = collection.query(
                query_embeddings=[query_embedding],
                n_results=candidate_k,
                include=["documents", "metadatas", "distances"],
            )

            vector_ids = vector_results["ids"][0] if vector_results["ids"] else []
            vector_docs = (
                vector_results["documents"][0] if vector_results["documents"] else []
            )
            vector_metas = (
                vector_results["metadatas"][0] if vector_results["metadatas"] else []
            )
            vector_dists = (
                vector_results["distances"][0] if vector_results["distances"] else []
            )

            # Build lookup maps
            id_to_doc = {}
            id_to_meta = {}
            id_to_score = {}

            for i, doc_id in enumerate(vector_ids):
                id_to_doc[doc_id] = vector_docs[i]
                id_to_meta[doc_id] = vector_metas[i]
                id_to_score[doc_id] = max(0, 1.0 - vector_dists[i])

            # --- BM25 search path ---
            bm25_ranked = []
            try:
                bm25_data = self._get_bm25_index(version)
                if bm25_data and bm25_data[0] is not None:
                    bm25, all_ids, all_docs = bm25_data
                    query_tokens = tokenize(query)
                    if query_tokens:
                        bm25_scores = bm25.get_scores(query_tokens)
                        scored_pairs = sorted(
                            zip(all_ids, bm25_scores, all_docs),
                            key=lambda x: x[1],
                            reverse=True,
                        )[:candidate_k]
                        for doc_id, score, doc in scored_pairs:
                            bm25_ranked.append(doc_id)
                            if doc_id not in id_to_doc:
                                # Need to fetch metadata for BM25-only results
                                id_to_doc[doc_id] = doc
                                id_to_score[doc_id] = 0.0  # No vector score
            except Exception as e:
                logger.warning(f"BM25 search failed, falling back to vector-only: {e}")

            # Fetch metadata for BM25-only results that aren't in vector results
            bm25_only_ids = [did for did in bm25_ranked if did not in id_to_meta]
            if bm25_only_ids:
                try:
                    extra = collection.get(ids=bm25_only_ids, include=["metadatas"])
                    for i, doc_id in enumerate(extra["ids"]):
                        id_to_meta[doc_id] = extra["metadatas"][i]
                except Exception:
                    pass

            # --- RRF fusion ---
            if bm25_ranked:
                fused_ids = reciprocal_rank_fusion(
                    [vector_ids, bm25_ranked], id_to_score
                )
            else:
                fused_ids = vector_ids

            # --- Format results ---
            formatted_results = []
            for doc_id in fused_ids[:top_k]:
                metadata = id_to_meta.get(doc_id, {})
                content = id_to_doc.get(doc_id, "")
                score = id_to_score.get(doc_id, 0.0)

                formatted_results.append(
                    {
                        "content": content,
                        "source_url": metadata.get("url", ""),
                        "section_title": metadata.get("breadcrumbs", ""),
                        "relevance_score": round(score, 4),
                        "version": version,
                    }
                )

            return formatted_results

        except Exception as e:
            logger.error(f"Search failed: {e}")
            raise


# ---------------------------------------------------------------------------
# Source Code Search Service (new)
# ---------------------------------------------------------------------------


class CodeSearchService:
    """Search engine source code chunks with hybrid BM25+vector search.

    The pipeline is:
        vector recall  ─┐
                        ├─▶ RRF fusion ─▶ LLM rerank (optional) ─▶ top_k
        BM25 recall   ─┘

    LLM rerank is on by default. Disable per-call with `rerank=False`, or
    globally by setting env var `COCOS_RAG_RERANK=0`.
    """

    def __init__(self, api_key: str = None):
        self.embedding_service = EmbeddingService(api_key=api_key)
        self.vector_store = VectorStoreManager()
        self._bm25_cache: Dict[str, Any] = {}
        self._reranker = LLMReranker()
        self._rerank_default = os.environ.get("COCOS_RAG_RERANK", "1") != "0"

    def _get_collection_name(self, version: str) -> str:
        return f"code_{version.replace('.', '_')}"

    def _get_bm25_index(self, collection_name: str):
        """Build or retrieve cached BM25 index for a code collection."""
        if collection_name in self._bm25_cache:
            return self._bm25_cache[collection_name]

        collection = self.vector_store.get_or_create_named_collection(collection_name)
        all_data = collection.get(include=["documents"])

        if not all_data["ids"]:
            return None, [], []

        doc_ids = all_data["ids"]
        documents = all_data["documents"]

        tokenized = [tokenize(doc) for doc in documents]
        bm25 = BM25Okapi(tokenized)

        self._bm25_cache[collection_name] = (bm25, doc_ids, documents)
        return bm25, doc_ids, documents

    def search(
        self,
        query: str,
        version: str = "3.8.8",
        top_k: int = 5,
        language: Optional[str] = None,
        class_name: Optional[str] = None,
        rerank: Optional[bool] = None,
    ) -> List[Dict[str, Any]]:
        """
        Hybrid search over source code chunks.

        Args:
            query: Search query string.
            version: Engine version ('3.8.8' or '3.7.3').
            top_k: Number of results to return.
            language: Optional filter: 'typescript', 'cpp', or None for all.
            class_name: Optional filter: restrict to a specific class.
            rerank: Whether to apply LLM reranking. Defaults to env-controlled
                value (`COCOS_RAG_RERANK`, default on).

        Returns:
            List of result dicts with code content, metadata, and relevance scores.
        """
        collection_name = self._get_collection_name(version)
        logger.info(
            f"Searching code for '{query}' in {collection_name} "
            f"(top_k={top_k}, language={language}, class_name={class_name})"
        )

        try:
            candidate_k = min(top_k * 4, 50)

            # Build where filter for metadata
            where_filter = self._build_where_filter(language, class_name)

            # --- Vector search path ---
            query_embedding = self.embedding_service.get_embeddings([query])[0]
            collection = self.vector_store.get_or_create_named_collection(
                collection_name
            )

            query_kwargs = {
                "query_embeddings": [query_embedding],
                "n_results": candidate_k,
                "include": ["documents", "metadatas", "distances"],
            }
            if where_filter:
                query_kwargs["where"] = where_filter

            vector_results = collection.query(**query_kwargs)

            vector_ids = vector_results["ids"][0] if vector_results["ids"] else []
            vector_docs = (
                vector_results["documents"][0] if vector_results["documents"] else []
            )
            vector_metas = (
                vector_results["metadatas"][0] if vector_results["metadatas"] else []
            )
            vector_dists = (
                vector_results["distances"][0] if vector_results["distances"] else []
            )

            # Build lookup maps
            id_to_doc = {}
            id_to_meta = {}
            id_to_score = {}

            for i, doc_id in enumerate(vector_ids):
                id_to_doc[doc_id] = vector_docs[i]
                id_to_meta[doc_id] = vector_metas[i]
                id_to_score[doc_id] = max(0, 1.0 - vector_dists[i])

            # --- BM25 search path ---
            bm25_ranked = []
            try:
                bm25_data = self._get_bm25_index(collection_name)
                if bm25_data and bm25_data[0] is not None:
                    bm25, all_ids, all_docs = bm25_data
                    query_tokens = tokenize(query)
                    if query_tokens:
                        bm25_scores = bm25.get_scores(query_tokens)
                        scored_pairs = list(zip(all_ids, bm25_scores, all_docs))
                        scored_pairs.sort(key=lambda x: x[1], reverse=True)

                        # Apply language/class_name filter on BM25 results post-hoc
                        # (BM25 doesn't support metadata filters natively)
                        count = 0
                        for doc_id, score, doc in scored_pairs:
                            if count >= candidate_k:
                                break
                            bm25_ranked.append(doc_id)
                            if doc_id not in id_to_doc:
                                id_to_doc[doc_id] = doc
                                id_to_score[doc_id] = 0.0
                            count += 1
            except Exception as e:
                logger.warning(f"BM25 search failed for code: {e}")

            # Fetch metadata for BM25-only results
            bm25_only_ids = [did for did in bm25_ranked if did not in id_to_meta]
            if bm25_only_ids:
                try:
                    extra = collection.get(
                        ids=bm25_only_ids[:100], include=["metadatas"]
                    )
                    for i, doc_id in enumerate(extra["ids"]):
                        id_to_meta[doc_id] = extra["metadatas"][i]
                except Exception:
                    pass

            # Post-filter BM25 results by metadata (language, class_name)
            if where_filter and bm25_ranked:
                bm25_ranked = self._filter_by_metadata(
                    bm25_ranked, id_to_meta, language, class_name
                )

            # --- RRF fusion ---
            if bm25_ranked:
                fused_ids = reciprocal_rank_fusion(
                    [vector_ids, bm25_ranked], id_to_score
                )
            else:
                fused_ids = vector_ids

            # --- Format results ---
            # If reranking is enabled we keep more candidates, format them all,
            # rerank, then slice. Otherwise we just slice the fused list directly.
            do_rerank = self._rerank_default if rerank is None else rerank
            slice_k = max(top_k * 4, 12) if do_rerank else top_k

            formatted_results = []
            github_base = "https://github.com/cocos/cocos-engine/blob"

            for doc_id in fused_ids[:slice_k]:
                meta = id_to_meta.get(doc_id, {})
                content = id_to_doc.get(doc_id, "")
                score = id_to_score.get(doc_id, 0.0)

                file_path = meta.get("file_path", "")
                line_start = meta.get("line_start", 0)
                tag = version
                source_url = (
                    f"{github_base}/{tag}/{file_path}#L{line_start}"
                    if file_path
                    else ""
                )

                formatted_results.append(
                    {
                        "content": meta.get("raw_code", content),
                        "embedding_text": content,
                        "source_url": source_url,
                        "file_path": file_path,
                        "chunk_type": meta.get("chunk_type", ""),
                        "class_name": meta.get("class_name", ""),
                        "method_name": meta.get("method_name", ""),
                        "signature": meta.get("signature", ""),
                        "language": meta.get("language", ""),
                        "relevance_score": round(score, 4),
                        "version": version,
                    }
                )

            if do_rerank and len(formatted_results) > 1:
                formatted_results = self._reranker.rerank(
                    query=query,
                    candidates=formatted_results,
                    top_k=top_k,
                    text_field="embedding_text",
                    score_field="relevance_score",
                )
            else:
                formatted_results = formatted_results[:top_k]

            return formatted_results

        except Exception as e:
            logger.error(f"Code search failed: {e}")
            raise

    def _build_where_filter(
        self, language: Optional[str], class_name: Optional[str]
    ) -> Optional[dict]:
        """Build ChromaDB where filter from optional parameters."""
        conditions = []
        if language and language != "all":
            conditions.append({"language": language})
        if class_name:
            conditions.append({"class_name": class_name})

        if not conditions:
            return None
        if len(conditions) == 1:
            return conditions[0]
        return {"$and": conditions}

    def _filter_by_metadata(
        self,
        ids: List[str],
        id_to_meta: Dict,
        language: Optional[str],
        class_name: Optional[str],
    ) -> List[str]:
        """Post-filter a list of IDs by metadata criteria."""
        filtered = []
        for doc_id in ids:
            meta = id_to_meta.get(doc_id, {})
            if language and language != "all" and meta.get("language") != language:
                continue
            if class_name and meta.get("class_name") != class_name:
                continue
            filtered.append(doc_id)
        return filtered
