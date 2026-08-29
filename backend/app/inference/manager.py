"""Inference Manager（M7，Addendum §11-18）。

管理独立 GPU Worker 进程：
- call(type, payload)：请求-应答（task_id 匹配，带超时）；
- watchdog：is_alive 监控，崩溃 -> restart（连续 max_consecutive_crashes 次
  崩溃后转 CPU fallback 设备重启 worker）；
- 崩溃/超时不允许杀死 Backend 主进程。
"""

from __future__ import annotations

import itertools
import logging
import multiprocessing as mp
import queue as queue_mod
import threading
import time
import uuid

from app.core.config import Config
from app.core.errors import GpuError

logger = logging.getLogger(__name__)


class WorkerCrashed(GpuError):
    code = "GPU_ERROR"


class WorkerTimeout(GpuError):
    code = "GPU_ERROR"


class InferenceManager:
    def __init__(self, cfg: Config, *, device_override: str | None = None,
                 auto_start: bool = True) -> None:
        self.cfg = cfg
        self._device_override = device_override
        self._ctx = mp.get_context("spawn")
        self._tasks: mp.Queue | None = None
        self._results: mp.Queue | None = None
        self._proc = None
        self._lock = threading.Lock()
        self._task_counter = itertools.count(1)
        self.consecutive_crashes = 0
        self.total_restarts = 0
        self.fallback_to_cpu = False
        self.device: str | None = None
        self.device_kind: str | None = None
        self._pending: dict[str, dict] = {}
        if auto_start:
            self.start()

    # ---- 生命周期 ----
    def start(self, *, timeout: float | None = None) -> None:
        self._tasks = self._ctx.Queue()
        self._results = self._ctx.Queue()
        self._proc = self._ctx.Process(
            target=_worker_entry,
            args=(self.cfg.model_dump_json(), self._tasks, self._results, self._device_override),
            daemon=True,
            name="inference-worker",
        )
        self._proc.start()
        # 等 ready 事件（模型加载可能 1-2 分钟）
        deadline = time.monotonic() + (timeout or self.cfg.inference.worker_start_timeout_seconds)
        while time.monotonic() < deadline:
            try:
                msg = self._results.get(timeout=0.5)
            except queue_mod.Empty:
                if not self._proc.is_alive():
                    raise WorkerCrashed("worker 在启动阶段死亡")
                continue
            if msg.get("event") == "ready":
                self.device = msg["device"]
                self.device_kind = msg["device_kind"]
                self.consecutive_crashes = 0
                logger.info("inference worker ready: device=%s load=%.0fms (%s)",
                            msg["device"], msg["load_ms"], msg["reason"])
                return
            if msg.get("event") == "error":
                raise GpuError(f"worker 启动失败: {msg['error']}")
        raise WorkerTimeout("worker 启动超时")

    def is_alive(self) -> bool:
        return self._proc is not None and self._proc.is_alive()

    def shutdown(self) -> None:
        if self.is_alive():
            try:
                self._tasks.put_nowait({"task_id": "shutdown", "type": "shutdown"})
                self._proc.join(timeout=5)
            except Exception:
                pass
        if self._proc is not None and self._proc.is_alive():
            self._proc.terminate()
        self._proc = None

    def restart(self, *, device_override: str | None = None) -> None:
        self.shutdown()
        if device_override is not None:
            self._device_override = device_override
        self.total_restarts += 1
        self.start()

    # ---- 请求-应答 ----
    def call(self, task_type: str, payload: dict | None = None,
             timeout: float | None = None) -> dict:
        """同步调用。崩溃时自动 restart 重试一次；连续崩溃转 CPU fallback。"""
        timeout = timeout or self.cfg.inference.worker_timeout_seconds
        with self._lock:
            return self._call_locked(task_type, payload or {}, timeout)

    def _call_locked(self, task_type: str, payload: dict, timeout: float) -> dict:
        if self._proc is None:
            self.start()
        task_id = f"t{next(self._task_counter)}-{uuid.uuid4().hex[:6]}"
        self._tasks.put({"task_id": task_id, "type": task_type, "payload": payload})
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            # watchdog
            if not self.is_alive():
                self._handle_crash()
                raise WorkerCrashed(f"worker 在执行 {task_type} 时死亡（已 restart）")
            try:
                msg = self._results.get(timeout=0.25)
            except queue_mod.Empty:
                continue
            if "event" in msg:  # 非应答事件
                continue
            self._pending[msg["task_id"]] = msg  # 缓存其他 task 的应答
            if msg["task_id"] != task_id:
                continue
            if not msg["ok"]:
                raise GpuError(f"worker 任务失败: {msg['error']}")
            return msg["result"]
        raise WorkerTimeout(f"worker 任务超时: {task_type} ({timeout}s)")

    def _handle_crash(self) -> None:
        self.consecutive_crashes += 1
        logger.warning("worker crash #%d", self.consecutive_crashes)
        if self.consecutive_crashes >= self.cfg.inference.max_consecutive_crashes \
                and not self.fallback_to_cpu and self._device_override != "cpu":
            logger.warning("连续崩溃 %d 次 -> CPU fallback", self.consecutive_crashes)
            self.fallback_to_cpu = True
            self.restart(device_override="cpu")
        else:
            self.restart()
        # 写 runtime_profile（Addendum §17）
        self._write_profile()

    def _write_profile(self) -> None:
        try:
            from pathlib import Path
            import json

            p = Path(self.cfg.paths.data_dir) / "runtime_profile.json"
            profile = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
            profile["worker"] = {
                "fallback_to_cpu": self.fallback_to_cpu,
                "total_restarts": self.total_restarts,
                "consecutive_crashes": self.consecutive_crashes,
                "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            }
            p.write_text(json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            logger.exception("runtime_profile 写入失败")

    # ---- 便捷接口 ----
    def health(self) -> dict:
        info = {
            "alive": self.is_alive(), "device": self.device,
            "device_kind": self.device_kind, "fallback_to_cpu": self.fallback_to_cpu,
            "total_restarts": self.total_restarts,
        }
        if self.is_alive():
            try:
                info["detail"] = self.call("health", timeout=10)
            except Exception as exc:
                info["detail_error"] = str(exc)
        return info


def _worker_entry(cfg_json: str, tasks, results, device_override) -> None:  # noqa: ANN001
    """spawn 入口：子进程重新 import 本模块后调用 run_worker。"""
    from app.inference.worker import run_worker

    run_worker(cfg_json, tasks, results, device_override)
