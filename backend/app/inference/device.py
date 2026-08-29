"""设备选择与检测（M0）。

原则：
- GPU 只是加速器，不是单点故障；
- 本模块是唯一允许探测 torch 设备的地方，业务代码不得散落 .cuda()；
- ROCm torch 在 Windows 上沿用 torch.cuda 命名空间（torch.version.hip 存在）。

已知平台问题（本机实测）：
- Ryzen 7600X3D 核显（AMD Radeon(TM) Graphics）被 HIP 枚举为 device 0，
  torch 默认在 device 0 上启动 gfx1100 kernel 会直接 0xC0000005 崩溃；
- 因此必须在枚举后按显存选择独显，并全程使用显式 device 字符串 "cuda:<idx>"，
  不依赖 HIP_VISIBLE_DEVICES（该 env 必须在首次 CUDA 查询前设置，时序脆弱）。
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class TorchNotAvailable(RuntimeError):
    """torch 未安装或导入失败。"""


def torch_info() -> dict:
    """返回 torch / ROCm(HIP) 版本信息；未安装时返回 available=False。"""
    try:
        import torch
    except Exception as exc:  # pragma: no cover - 环境相关
        return {"available": False, "error": f"{type(exc).__name__}: {exc}"}

    return {
        "available": True,
        "torch_version": torch.__version__,
        "hip_version": getattr(torch.version, "hip", None),
        "cuda_version": getattr(torch.version, "cuda", None),
        "is_rocm": bool(getattr(torch.version, "hip", None)),
    }


def detect_gpu(preferred: str = "rocm") -> tuple[str | None, str]:
    """探测可用 GPU 设备，返回 (torch_device_str, reason)。

    torch_device_str 为 "cuda:<idx>"（选择最大显存的设备）或 None。
    preferred 仅支持 "rocm"（本项目架构锁定 AMD）与 "cpu"。
    枚举只做属性查询，不启动 kernel，iGPU 上不会崩溃。
    """
    info = torch_info()
    if not info["available"]:
        return None, f"TORCH_NOT_AVAILABLE: {info.get('error')}"

    if preferred == "cpu":
        return None, "preferred_device=cpu，按要求跳过 GPU"

    try:
        import torch

        if not torch.cuda.is_available():
            return None, "CUDA/HIP Runtime 不可用（torch.cuda.is_available()=False）"

        count = torch.cuda.device_count()
        props = [torch.cuda.get_device_properties(i) for i in range(count)]
        best = max(range(count), key=lambda i: props[i].total_memory)
        names = {i: props[i].name for i in range(count)}
        reason = f"GPU 可用: {names[best]} (device {best}/{count})"
        if count > 1:
            reason += f"；多设备 {names}，已按最大显存选择，iGPU 已排除"
        return f"cuda:{best}", reason
    except Exception as exc:
        return None, f"GPU 探测失败: {type(exc).__name__}: {exc}"


def select_device(preferred: str = "rocm", fallback: str = "cpu") -> tuple[str, str]:
    """选择推理设备，GPU 不可用时回退 fallback。

    返回 (device_str, reason)：device_str ∈ {"cuda:<idx>", "cpu"}。
    """
    device, reason = detect_gpu(preferred)
    if device is not None:
        return device, reason
    logger.warning("GPU 不可用，回退 %s。原因: %s", fallback, reason)
    return fallback, f"GPU_PROVIDER_FAILED -> {fallback}: {reason}"


def device_kind(device_str: str) -> str:
    """逻辑设备类型：rocm / cuda / cpu（用于日志与 runtime_profile）。"""
    if device_str == "cpu":
        return "cpu"
    info = torch_info()
    return "rocm" if info.get("hip_version") else "cuda"
