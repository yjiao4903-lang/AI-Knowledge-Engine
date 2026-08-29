"""GPU Inference Worker（M7，Addendum §11-18）。

独立 OS 进程（spawn）：同时加载 Embedding + Reranker 模型，
经 multiprocessing.Queue 收发任务。任何 0xC0000005 崩溃只杀本进程，
由 InferenceManager 检测并 restart / CPU fallback。

必须以模块级函数作为 spawn 入口（Windows）。
"""

from __future__ import annotations

import json
import os
import queue as queue_mod
import sys
import time
from pathlib import Path

# spawn 子进程导入本模块时确保可 import app.*
_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))


def run_worker(cfg_json: str, tasks, results, device_override: str | None = None) -> None:  # noqa: ANN001
    """Worker 主循环。cfg_json 为 Config JSON（避免在 Windows spawn 下传复杂对象）。"""
    import logging

    logging.basicConfig(level=logging.INFO)
    try:
        from app.core.config import Config
        from app.inference.device import device_kind, get_inference_device
        from app.inference.embedding_provider import TorchEmbeddingProvider
        from app.inference.reranker_provider import TorchRerankerProvider

        cfg = Config.model_validate(json.loads(cfg_json))
        device, reason = get_inference_device(
            force_device=device_override or cfg.inference.force_device,
            preferred_device=cfg.inference.preferred_device,
            preferred_gpu_name=cfg.inference.preferred_gpu_name,
            fallback=cfg.embedding.fallback_device,
        )
        t0 = time.perf_counter()
        embedder = TorchEmbeddingProvider(
            cfg.embedding.local_path, device=device, dtype_gpu=cfg.embedding.dtype_gpu,
            max_length=cfg.embedding.max_tokens, query_instruction=cfg.embedding.query_instruction,
        )
        reranker = TorchRerankerProvider(
            cfg.reranker.local_path, device=device, dtype_gpu=cfg.reranker.dtype_gpu,
            max_length=cfg.reranker.max_tokens,
        )
        load_ms = (time.perf_counter() - t0) * 1000
        results.put({
            "event": "ready", "device": device, "device_kind": device_kind(device),
            "reason": reason, "load_ms": round(load_ms, 1),
        })
    except Exception as exc:  # 模型加载失败：上报后退出
        results.put({"event": "error", "error": f"{type(exc).__name__}: {exc}"})
        return

    while True:
        try:
            task = tasks.get(timeout=1.0)
        except queue_mod.Empty:
            continue
        except (EOFError, OSError):
            return
        if task is None or task.get("type") == "shutdown":
            results.put({"event": "shutdown"})
            return
        ttype = task.get("type", "")
        try:
            payload = task.get("payload") or {}
            if ttype == "embed_query":
                result = embedder.embed_query(payload["query"])
            elif ttype == "embed_documents":
                result = embedder.embed_documents(
                    payload["texts"], batch_size=payload.get("batch_size", 8))
            elif ttype == "rerank":
                result = reranker.score(
                    payload["query"], payload["documents"],
                    batch_size=payload.get("batch_size", 1),
                    instruction=payload.get("instruction", ""),
                )
            elif ttype == "health":
                result = {
                    "device": device, "device_kind": device_kind(device),
                    "embedding": embedder.health(), "reranker": reranker.health(),
                    "pid": os.getpid(),
                }
            elif ttype == "test_crash":  # 测试：模拟 0xC0000005 级进程崩溃
                os._exit(1)
            elif ttype == "test_sleep":  # 测试：模拟 GPU hang
                time.sleep(float(payload.get("seconds", 5)))
                result = {"slept": payload.get("seconds", 5)}
            else:
                raise ValueError(f"unknown task type: {ttype}")
            results.put({"task_id": task.get("task_id"), "ok": True, "result": result})
        except Exception as exc:
            results.put({
                "task_id": task.get("task_id"), "ok": False,
                "error": f"{type(exc).__name__}: {exc}",
            })
