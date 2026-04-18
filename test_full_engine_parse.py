"""Full-engine parse smoke test (subprocess-guarded, 10-min cap).

Runs `process_engine_directory` on the full 3.8.8 engine tree and writes
the JSONL output to .data/processed/. If the worker hangs or explodes the
parent will kill it after the hard cap.
"""

from __future__ import annotations

import multiprocessing as mp
import os
import sys
import time
import traceback


HARD_TIMEOUT_SEC = 600  # 10 minutes


def _worker(version, engine_dir, out_file, q):
    try:
        from src.code_parser import process_engine_directory

        t0 = time.time()
        n = process_engine_directory(engine_dir, out_file, version)
        q.put({"ok": True, "chunks": n, "elapsed": time.time() - t0})
    except Exception:
        q.put({"ok": False, "error": traceback.format_exc()})


def parse_version(version: str) -> int:
    engine_dir = f".data/engine/{version}"
    out_file = f".data/processed/code_chunks_{version}.jsonl"
    if not os.path.isdir(engine_dir):
        print(f"engine dir missing: {engine_dir}")
        return 2
    ctx = mp.get_context("spawn")
    q: mp.Queue = ctx.Queue()
    p = ctx.Process(
        target=_worker, args=(version, engine_dir, out_file, q), daemon=True
    )
    print(f"Parsing full engine {version} in subprocess (cap {HARD_TIMEOUT_SEC}s)...")
    p.start()
    p.join(HARD_TIMEOUT_SEC)
    if p.is_alive():
        print(f"TIMEOUT after {HARD_TIMEOUT_SEC}s -- killing subprocess")
        p.terminate()
        p.join(5)
        if p.is_alive():
            p.kill()
            p.join(2)
        return 1
    try:
        r = q.get_nowait()
    except Exception:
        print("subprocess exited without producing result")
        return 1
    if not r.get("ok"):
        print(f"FAIL:\n{r.get('error')}")
        return 1
    print(f"OK: {r['chunks']} chunks in {r['elapsed']:.1f}s")
    print(f"output: {out_file}")
    try:
        size = os.path.getsize(out_file)
        print(f"file size: {size / 1024 / 1024:.2f} MB")
    except OSError:
        pass
    return 0


def main() -> int:
    versions = sys.argv[1:] if len(sys.argv) > 1 else ["3.8.8", "3.7.3"]
    rc = 0
    for v in versions:
        print(f"\n========== {v} ==========")
        code = parse_version(v)
        if code != 0:
            rc = code
    return rc


if __name__ == "__main__":
    sys.exit(main())
