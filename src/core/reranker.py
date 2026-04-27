"""
LLM-based cross-encoder style reranker for hybrid search results.

Sends the user query plus a compact list of candidate snippets to an OpenAI
chat model and asks it to score each candidate's relevance on a 0-10 scale.
The returned scores are blended with the original retrieval score and used
to re-sort the candidates.

Why an LLM rerank instead of a local cross-encoder?
- Zero extra dependencies (we already use OpenAI for embeddings).
- Single network round trip per query, ~1-2s, costs fractions of a cent.
- Excellent multilingual quality (Chinese + English mixed code/docs).

A local cross-encoder (e.g. BAAI/bge-reranker-base) can be swapped in later
behind the same `Reranker.rerank()` interface; nothing else has to change.
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Dict, List, Optional

import openai

logger = logging.getLogger(__name__)


# Default model: cheap + fast. Override via OPENAI_RERANK_MODEL.
_DEFAULT_MODEL = os.environ.get("OPENAI_RERANK_MODEL", "gpt-4o-mini")


class LLMReranker:
    """LLM-based reranker. Stateless aside from the OpenAI client config."""

    def __init__(self, model: str = _DEFAULT_MODEL, max_snippet_chars: int = 600):
        self.model = model
        self.max_snippet_chars = max_snippet_chars

    # --- public API ---------------------------------------------------------

    def rerank(
        self,
        query: str,
        candidates: List[Dict[str, Any]],
        *,
        top_k: int,
        text_field: str = "embedding_text",
        score_field: str = "relevance_score",
        blend_weight: float = 0.7,
    ) -> List[Dict[str, Any]]:
        """Rerank `candidates` by LLM relevance and return the top `top_k`.

        Args:
            query: original user query.
            candidates: list of result dicts (already scored by hybrid retriever).
            top_k: number of results to return.
            text_field: which field of each candidate to send to the LLM.
            score_field: existing score field used for blending and as a fallback.
            blend_weight: weight of LLM score in the final blend (0..1). The
                retrieval score gets `(1 - blend_weight)`. Both are normalized
                to 0..1 before blending.

        On any failure the original candidates are returned, simply truncated
        to `top_k`. Reranking is best-effort, never blocks the search path.
        """
        if not candidates:
            return []
        if len(candidates) == 1:
            return candidates[:top_k]

        try:
            llm_scores = self._score_with_llm(query, candidates, text_field)
        except Exception as e:
            logger.warning(f"LLM rerank failed, falling back to original order: {e}")
            return candidates[:top_k]

        # Normalize retrieval scores to 0..1 within this candidate set.
        retrieval_scores = [float(c.get(score_field, 0.0) or 0.0) for c in candidates]
        max_r = max(retrieval_scores) if retrieval_scores else 1.0
        if max_r <= 0:
            max_r = 1.0
        norm_retrieval = [s / max_r for s in retrieval_scores]

        # Build blended scores.
        for idx, cand in enumerate(candidates):
            llm = llm_scores.get(idx)
            llm_norm = (llm / 10.0) if llm is not None else None

            if llm_norm is None:
                blended = norm_retrieval[idx]  # no LLM score -> retrieval only
            else:
                blended = (
                    blend_weight * llm_norm + (1.0 - blend_weight) * norm_retrieval[idx]
                )
            cand["rerank_score"] = round(blended, 4)
            if llm is not None:
                cand["llm_score"] = llm

        candidates.sort(key=lambda c: c.get("rerank_score", 0.0), reverse=True)
        return candidates[:top_k]

    # --- internals ----------------------------------------------------------

    def _score_with_llm(
        self,
        query: str,
        candidates: List[Dict[str, Any]],
        text_field: str,
    ) -> Dict[int, float]:
        """Call the LLM once and return {candidate_index: score_0_10}."""
        # Compact each candidate into a short blob.
        items = []
        for i, c in enumerate(candidates):
            text = (c.get(text_field) or "")[: self.max_snippet_chars]
            file_hint = c.get("file_path") or c.get("source_url") or ""
            cls = c.get("class_name") or ""
            mth = c.get("method_name") or ""
            header = " ".join(s for s in (file_hint, cls, mth) if s)
            items.append(f"[{i}] {header}\n{text}")

        joined = "\n---\n".join(items)
        prompt = (
            "You are a relevance grader. Given a user query and a list of candidate "
            "documentation/code snippets, rate each snippet's relevance to the query "
            "on a 0-10 integer scale (10 = exactly answers the query, 0 = totally "
            "unrelated). Only consider how well it answers the query, not snippet "
            "length or formatting.\n\n"
            f"User query: {query}\n\n"
            "Candidates:\n"
            f"{joined}\n\n"
            "Return ONLY a compact JSON object mapping candidate index (as string) "
            'to integer score, e.g. {"0": 9, "1": 3, ...}. No commentary.'
        )

        resp = openai.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            max_tokens=400,
            timeout=15.0 # Set explicit timeout so it fails fast instead of hanging
        )
        raw = (resp.choices[0].message.content or "").strip()
        return self._parse_scores(raw, n=len(candidates))

    @staticmethod
    def _parse_scores(raw: str, n: int) -> Dict[int, float]:
        """Best-effort JSON parse, with a regex fallback."""
        # Strip code fences if any.
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        payload = m.group(0) if m else raw
        scores: Dict[int, float] = {}
        try:
            data = json.loads(payload)
            for k, v in data.items():
                try:
                    idx = int(str(k).strip())
                    val = float(v)
                except (TypeError, ValueError):
                    continue
                if 0 <= idx < n:
                    scores[idx] = max(0.0, min(10.0, val))
            if scores:
                return scores
        except Exception:
            pass
        # Fallback: regex pairs like "0": 9
        for m in re.finditer(r'"?(\d+)"?\s*:\s*(\d+(?:\.\d+)?)', payload):
            idx = int(m.group(1))
            if 0 <= idx < n:
                scores[idx] = max(0.0, min(10.0, float(m.group(2))))
        return scores
