"""M7 Worker 冒烟 + Reranker batch benchmark（Addendum §20/§27）。"""

from __future__ import annotations

import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app.core.config import load_config  # noqa: E402
from app.inference.manager import InferenceManager  # noqa: E402


def main() -> int:
    cfg = load_config()
    print("==> 1. start worker (spawn, GPU)")
    mgr = InferenceManager(cfg)
    print(f"    ready: device={mgr.device} kind={mgr.device_kind} restarts={mgr.total_restarts}")

    print("==> 2. health")
    h = mgr.health()
    print(f"    {h}")

    print("==> 3. embed_query")
    t0 = time.perf_counter()
    vec = mgr.call("embed_query", {"query": "HBM4 的接口位宽是多少？"})
    print(f"    dim={len(vec)} ms={round((time.perf_counter()-t0)*1000,1)}")

    print("==> 4. rerank batch benchmark (24 candidate docs, batch 1/2/4/8)")
    docs = [
        f"样本文档 {i}：HBM4 接口位宽 2048-bit，CoWoS-L 中介层面积 3.3 倍，"
        f"先进封装产能 {'紧张' if i % 3 else '正常'}，证据等级 [L1]。" * 3
        for i in range(24)
    ]
    benchmark = {}
    for batch in (1, 2, 4, 8):
        t0 = time.perf_counter()
        scores = mgr.call("rerank", {
            "query": "HBM4 的接口位宽是多少？", "documents": docs, "batch_size": batch,
        })
        ms = (time.perf_counter() - t0) * 1000
        ok = all(isinstance(s, float) and s == s for s in scores)  # finite
        benchmark[batch] = {"ms": round(ms, 1), "finite": ok}
        print(f"    batch={batch}: {benchmark[batch]['ms']}ms finite={ok}")

    print("==> 5. crash -> watchdog restart")
    try:
        mgr.call("test_crash", timeout=30)
        print("    ERROR: crash 未生效")
    except Exception as exc:
        print(f"    captured: {type(exc).__name__}")
    time.sleep(1)
    h2 = mgr.health()
    print(f"    after crash: alive={h2['alive']} device={mgr.device} restarts={mgr.total_restarts}")
    vec2 = mgr.call("embed_query", {"query": "restart 后仍可推理"})
    print(f"    post-restart embed dim={len(vec2)}")

    print("==> 6. timeout guard")
    try:
        mgr.call("test_sleep", {"seconds": 8}, timeout=3)
        print("    ERROR: 超时未生效")
    except Exception as exc:
        print(f"    captured: {type(exc).__name__}")

    print("==> 7. shutdown")
    mgr.shutdown()
    print(f"    alive={mgr.is_alive()}")

    print(f"\nselected batch: {max(b for b, v in benchmark.items() if v['finite'])} (stable, finite)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
