"""End-to-end validation of CodeSearchService against the indexed Chroma store.

Sends a handful of realistic Cocos queries (mixed Chinese / English, TS + C++)
and prints the top hits with file path, class/method, score, and source URL.
"""

from __future__ import annotations

import json
import os
import sys
import time

# src/ must be importable the same way other scripts are run (`uv run src/...`)
sys.path.insert(0, "src")

from core.config import load_env  # noqa: E402
from core.search import CodeSearchService  # noqa: E402


QUERIES = [
    # (query, version, language_filter, class_filter, expected_keywords_any_of)
    (
        "Node 节点如何添加子节点 addChild",
        "3.8.8",
        "typescript",
        None,
        ["addChild", "node.ts", "Node"],
    ),
    (
        "获取节点的世界坐标 worldPosition",
        "3.8.8",
        "typescript",
        None,
        ["worldPosition", "node.ts"],
    ),
    (
        "Sprite 如何设置精灵的图片 spriteFrame",
        "3.8.8",
        "typescript",
        None,
        ["spriteFrame", "Sprite"],
    ),
    (
        "物理射线检测 raycast 怎么用",
        "3.8.8",
        None,
        None,
        ["raycast", "PhysicsSystem", "physics"],
    ),
    (
        "typescript 事件发射 emit 监听 on 写法",
        "3.8.8",
        "typescript",
        None,
        ["emit", "on("],
    ),
    (
        "Camera 相机渲染流程 C++ 实现",
        "3.8.8",
        "cpp",
        None,
        ["Camera", "camera", "render"],
    ),
    # 3.7.3 sanity check
    ("节点坐标变换 setPosition", "3.7.3", "typescript", None, ["setPosition", "Node"]),
]


def truncate(s: str, n: int) -> str:
    s = (s or "").replace("\n", " ").strip()
    return s if len(s) <= n else s[: n - 1] + "…"


def main() -> int:
    load_env()
    svc = CodeSearchService()

    # Optional A/B: set RERANK=0 to disable LLM rerank for the run.
    use_rerank = os.environ.get("RERANK", "1") != "0"
    print(f"(rerank={'ON' if use_rerank else 'OFF'})")

    failures: list[str] = []
    for q, ver, lang, cls, expect_any in QUERIES:
        print("=" * 88)
        print(f"Q: {q}  (v={ver}, lang={lang or 'all'}, class={cls or '-'})")
        t0 = time.time()
        try:
            results = svc.search(
                query=q,
                version=ver,
                top_k=5,
                language=lang,
                class_name=cls,
                rerank=use_rerank,
            )
        except Exception as e:
            print(f"  [ERROR] {e}")
            failures.append(q)
            continue
        elapsed = time.time() - t0
        print(f"   {len(results)} hits in {elapsed:.2f}s")

        if not results:
            failures.append(f"{q} (no results)")
            continue

        for i, r in enumerate(results, 1):
            score_part = f"score={r.get('relevance_score')}"
            if "rerank_score" in r:
                score_part += f"  rerank={r['rerank_score']}"
            if "llm_score" in r:
                score_part += f"  llm={r['llm_score']}"
            print(
                f"  {i}. [{r.get('chunk_type', '?')}] "
                f"{r.get('class_name', '') or '-'}"
                f"{'.' + r['method_name'] if r.get('method_name') else ''}"
                f"  ({r.get('language', '?')})  {score_part}"
            )
            print(f"     file: {r.get('file_path', '')}")
            print(f"     url : {r.get('source_url', '')}")
            sig = r.get("signature") or ""
            if sig:
                print(f"     sig : {truncate(sig, 120)}")
            print(f"     embed head: {truncate(r.get('embedding_text', ''), 140)}")

        # Loose relevance check: top-3 embedding_text OR file_path should mention
        # at least one of the expected keywords (case-insensitive substring).
        blob = " ".join(
            (
                r.get("embedding_text", "")
                + " "
                + r.get("file_path", "")
                + " "
                + (r.get("class_name") or "")
                + " "
                + (r.get("method_name") or "")
            )
            for r in results[:3]
        ).lower()
        hit_kw = [kw for kw in expect_any if kw.lower() in blob]
        if not hit_kw:
            failures.append(f"{q} (none of {expect_any} found in top-3)")
            print(f"   [WARN] none of {expect_any} in top-3 context")
        else:
            print(f"   [OK] matched: {hit_kw}")

    print("=" * 88)
    if failures:
        print(f"RELEVANCE FAILURES ({len(failures)}):")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("ALL OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
