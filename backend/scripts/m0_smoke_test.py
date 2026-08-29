"""M0 冒烟测试 + 诊断输出（spec §30, §54）。

步骤：
1. torch import / ROCm(HIP) 检测 / RX 7900 XTX 检测（iGPU 排除，见 device.py）
2. GPU tensor matmul
3. Qwen3-Embedding-0.6B：两句 embed -> shape (2,1024), finite, norm≈1
4. Qwen3-Reranker-0.6B：两对文本打分 -> finite
5. GPU 崩溃（0xC0000005 属进程级，无法捕获）由 run_m0.ps1 以 --force-device cpu 重跑
6. 输出 data/diagnostic_m0.json 与 data/runtime_profile.json

用法：
  python backend/scripts/m0_smoke_test.py [--force-device cuda|cpu] [--skip-models]
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
import traceback
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app.inference.device import device_kind, select_device, torch_info  # noqa: E402

EMBEDDING_PATH = "D:/AI-Models/Qwen3-Embedding-0.6B"
RERANKER_PATH = "D:/AI-Models/Qwen3-Reranker-0.6B"
EMBED_DIM = 1024


def check_torch() -> dict:
    info = torch_info()
    return {"step": "torch_import", "ok": info["available"], **info}


def check_gpu_matmul(device: str) -> dict:
    import torch

    a = torch.randn(256, 256, device=device, dtype=torch.float32)
    b = torch.randn(256, 256, device=device, dtype=torch.float32)
    c = a @ b
    if device != "cpu":
        torch.cuda.synchronize()
    finite = bool(torch.isfinite(c).all().item())
    return {"step": "gpu_matmul", "ok": finite, "device": device, "shape": list(c.shape)}


def check_embedding(device: str) -> dict:
    from app.inference.embedding_provider import TorchEmbeddingProvider

    provider = TorchEmbeddingProvider(EMBEDDING_PATH, device=device, dtype_gpu="float16")
    t0 = time.perf_counter()
    docs = provider.embed_documents(["HBM4 接口位宽提升至 2048-bit。", "TSMC CoWoS-L uses local silicon interconnect."])
    doc_ms = (time.perf_counter() - t0) * 1000
    t0 = time.perf_counter()
    q = provider.embed_query("HBM4 的接口位宽是多少？")
    query_ms = (time.perf_counter() - t0) * 1000

    shape_ok = len(docs) == 2 and all(len(v) == EMBED_DIM for v in docs) and len(q) == EMBED_DIM
    finite_ok = all(math.isfinite(x) for v in docs for x in v) and all(math.isfinite(x) for x in q)
    norm = sum(x * x for x in q) ** 0.5
    norm_ok = 0.95 <= norm <= 1.05

    return {
        "step": "embedding_smoke",
        "ok": shape_ok and finite_ok and norm_ok,
        "model": EMBEDDING_PATH,
        "dim": EMBED_DIM,
        "shape_ok": shape_ok,
        "finite_ok": finite_ok,
        "query_norm": round(norm, 4),
        "norm_ok": norm_ok,
        "doc_batch_ms": round(doc_ms, 1),
        "query_ms": round(query_ms, 1),
    }


def check_reranker(device: str) -> dict:
    from app.inference.reranker_provider import TorchRerankerProvider

    provider = TorchRerankerProvider(RERANKER_PATH, device=device, dtype_gpu="float16")
    query = "HBM4 的接口位宽是多少？"
    docs = [
        "HBM4 将接口位宽从 1024-bit 提升至 2048-bit，同时保持引脚速度。",
        "CoWoS-L 使用 local silicon interconnect 实现更大的 interposer 面积。",
    ]
    t0 = time.perf_counter()
    scores = provider.score(query, docs, batch_size=1)
    ms = (time.perf_counter() - t0) * 1000

    finite_ok = all(math.isfinite(s) for s in scores)
    order_ok = scores[0] > scores[1]  # 相关文档得分应更高
    return {
        "step": "reranker_smoke",
        "ok": finite_ok,
        "model": RERANKER_PATH,
        "scores": [round(s, 4) for s in scores],
        "finite_ok": finite_ok,
        "expected_order_ok": order_ok,
        "pair_batch1_ms": round(ms, 1),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force-device", choices=["cuda", "cpu"], default=None)
    parser.add_argument("--skip-models", action="store_true")
    parser.add_argument("--tag", default=None, help="输出文件名后缀，如 cpu_fallback -> diagnostic_m0_cpu_fallback.json")
    args = parser.parse_args()

    diag: dict = {"date": time.strftime("%Y-%m-%dT%H:%M:%S"), "checks": [], "fallback_used": False}

    diag["checks"].append(check_torch())

    preferred = args.force_device or "rocm"
    device, reason = select_device(preferred, fallback="cpu")
    diag["device"] = device
    diag["device_kind"] = device_kind(device)
    diag["device_reason"] = reason
    diag["fallback_used"] = device == "cpu" and preferred != "cpu"
    print(f"[device] {device} ({reason})")

    if device != "cpu":
        try:
            diag["checks"].append(check_gpu_matmul(device))
        except Exception as exc:
            diag["checks"].append({"step": "gpu_matmul", "ok": False, "error": str(exc)})
            device = "cpu"
            diag["device"] = "cpu"
            diag["device_kind"] = "cpu"
            diag["fallback_used"] = True
            diag["device_reason"] = f"GPU_PROVIDER_FAILED -> cpu: {exc}"
            print(f"[fallback] {diag['device_reason']}")

    if not args.skip_models:
        try:
            diag["checks"].append(check_embedding(device))
        except Exception as exc:
            diag["checks"].append(
                {"step": "embedding_smoke", "ok": False, "device": device,
                 "error": f"{type(exc).__name__}: {exc}", "traceback": traceback.format_exc(limit=3)}
            )
        try:
            diag["checks"].append(check_reranker(device))
        except Exception as exc:
            diag["checks"].append(
                {"step": "reranker_smoke", "ok": False, "device": device,
                 "error": f"{type(exc).__name__}: {exc}", "traceback": traceback.format_exc(limit=3)}
            )

    diag["ok"] = all(c.get("ok", False) for c in diag["checks"])

    out_dir = PROJECT_ROOT / "data"
    out_dir.mkdir(parents=True, exist_ok=True)
    runtime_profile = {
        "generated_at": diag["date"],
        "inference_device": diag["device"],
        "device_kind": diag["device_kind"],
        "device_reason": diag["device_reason"],
        "fallback_used": diag["fallback_used"],
        "embedding": {
            "model": EMBEDDING_PATH, "dimension": EMBED_DIM, "dtype_gpu": "float16",
            "batch_size_gpu": 8 if diag["device"] != "cpu" else 2, "batch_size_cpu": 2,
        },
        "reranker": {"model": RERANKER_PATH, "dtype_gpu": "float16", "safe_batch_gpu": 1, "candidate_k": 24},
        "torch": {k: v for k, v in diag["checks"][0].items() if k not in ("step", "ok")},
    }
    suffix = f"_{args.tag}" if args.tag else ""
    (out_dir / f"diagnostic_m0{suffix}.json").write_text(json.dumps(diag, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / f"runtime_profile{suffix}.json").write_text(json.dumps(runtime_profile, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps(diag, ensure_ascii=False, indent=2))
    print(f"\nwritten: {out_dir / f'diagnostic_m0{suffix}.json'}")
    return 0 if diag["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
