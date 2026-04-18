"""Stability-first test of the code parser.

Each parser call runs in its own subprocess with a hard timeout. If a file
hangs or leaks memory, the watchdog kills it and the test fails loudly
instead of locking up the developer machine.

Run with:   uv run python test_code_parser.py
"""

from __future__ import annotations

import multiprocessing as mp
import os
import sys
import time
import traceback
from typing import Any


# ---------------------------------------------------------------------------
# Subprocess workers
# ---------------------------------------------------------------------------


def _worker_parse_file(lang: str, file_path: str, version: str, base_dir: str, q):
    """Parse one file and ship back a compact summary via the queue."""
    try:
        # Import inside the subprocess so a hang doesn't poison the parent.
        from src.code_parser import TypeScriptCodeParser, CppCodeParser

        parser = TypeScriptCodeParser() if lang == "ts" else CppCodeParser()
        t0 = time.time()
        chunks = parser.parse_file(file_path, version, base_dir)
        elapsed = time.time() - t0

        summary = {
            "ok": True,
            "elapsed": elapsed,
            "n_chunks": len(chunks),
            "sample": [
                {
                    "chunk_type": c.get("chunk_type"),
                    "class_name": c.get("class_name"),
                    "method_name": c.get("method_name"),
                    "embedding_len": len(c.get("embedding_text", "")),
                    "line_start": c.get("line_start"),
                    "line_end": c.get("line_end"),
                }
                for c in chunks[:5]
            ],
            "first_embed": chunks[0]["embedding_text"][:500] if chunks else "",
        }
        q.put(summary)
    except Exception:
        q.put({"ok": False, "error": traceback.format_exc()})


def _worker_parse_dir(ts_dir: str, version: str, base_dir: str, q):
    try:
        from src.code_parser import TypeScriptCodeParser

        parser = TypeScriptCodeParser()
        total = 0
        files = 0
        t0 = time.time()
        for fn in os.listdir(ts_dir):
            if not fn.endswith(".ts") or fn.endswith(".d.ts"):
                continue
            files += 1
            chunks = parser.parse_file(os.path.join(ts_dir, fn), version, base_dir)
            total += len(chunks)
        q.put(
            {"ok": True, "files": files, "chunks": total, "elapsed": time.time() - t0}
        )
    except Exception:
        q.put({"ok": False, "error": traceback.format_exc()})


# ---------------------------------------------------------------------------
# Harness
# ---------------------------------------------------------------------------


def run_with_timeout(target, args: tuple, timeout: float) -> dict[str, Any]:
    """Run `target(*args, q)` in a subprocess; kill after `timeout` seconds."""
    ctx = mp.get_context("spawn")  # 'spawn' is safe on Windows
    q: mp.Queue = ctx.Queue()
    p = ctx.Process(target=target, args=(*args, q), daemon=True)
    p.start()
    p.join(timeout)
    if p.is_alive():
        p.terminate()
        p.join(5)
        if p.is_alive():
            p.kill()
            p.join(2)
        return {"ok": False, "error": f"TIMEOUT after {timeout}s"}
    try:
        return q.get_nowait()
    except Exception:
        return {"ok": False, "error": "no result from subprocess"}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

BASE_DIR = ".data/engine/3.8.8"
VERSION = "3.8.8"

FAILURES: list[str] = []


def check(label: str, result: dict, *, min_chunks: int = 0) -> None:
    if not result.get("ok"):
        msg = f"[FAIL] {label}: {result.get('error', 'unknown')[:400]}"
        print(msg)
        FAILURES.append(label)
        return
    n = result.get("n_chunks", result.get("chunks", 0))
    elapsed = result.get("elapsed", 0)
    print(f"[OK]   {label}: {n} chunks in {elapsed:.2f}s")
    for s in result.get("sample", [])[:3]:
        print(f"         - {s}")
    if n < min_chunks:
        FAILURES.append(f"{label} (only {n} chunks, expected >= {min_chunks})")
        print(f"[WARN] {label}: expected >= {min_chunks} chunks, got {n}")


def test_ts_small_file() -> None:
    r = run_with_timeout(
        _worker_parse_file,
        ("ts", f"{BASE_DIR}/cocos/scene-graph/node-enum.ts", VERSION, BASE_DIR),
        timeout=20,
    )
    check("TS node-enum.ts", r, min_chunks=1)


def test_ts_large_file() -> None:
    r = run_with_timeout(
        _worker_parse_file,
        ("ts", f"{BASE_DIR}/cocos/scene-graph/node.ts", VERSION, BASE_DIR),
        timeout=45,
    )
    check("TS node.ts (large)", r, min_chunks=5)
    if r.get("ok") and r.get("first_embed"):
        print("         --- first embedding text ---")
        for line in r["first_embed"].splitlines()[:8]:
            print(f"         {line}")
        print("         ----------------------------")


def test_cpp_header() -> None:
    r = run_with_timeout(
        _worker_parse_file,
        ("cpp", f"{BASE_DIR}/native/cocos/scene/Camera.h", VERSION, BASE_DIR),
        timeout=20,
    )
    check("C++ Camera.h", r, min_chunks=1)


def test_scene_graph_dir() -> None:
    r = run_with_timeout(
        _worker_parse_dir,
        (f"{BASE_DIR}/cocos/scene-graph", VERSION, BASE_DIR),
        timeout=90,
    )
    check("TS dir scene-graph/", r, min_chunks=10)


def main() -> int:
    # sanity
    if not os.path.isdir(BASE_DIR):
        print(f"engine dir missing: {BASE_DIR}")
        return 2

    print("=== running parser stability tests (each in subprocess w/ timeout) ===\n")
    test_ts_small_file()
    test_ts_large_file()
    test_cpp_header()
    test_scene_graph_dir()

    print()
    if FAILURES:
        print(f"FAILED ({len(FAILURES)}): {FAILURES}")
        return 1
    print("ALL OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
