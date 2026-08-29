# Implementation Status

## Current Milestone
M1 项目骨架与 Storage（下一步）

## Completed
- [x] M0 环境与硬件验证（2026-08-29）

## In Progress
- [ ] M1

## M0 交付物
- 依赖管理：pip + `backend/pyproject.toml` + `backend/requirements-lock.txt`（76 项锁定）
- PyTorch ROCm：`torch==2.9.1+rocm7.13.0` + `rocm-sdk-*-7.13.0`（gfx1100，Windows）
- Qdrant：Docker `qdrant/qdrant:v1.19.0`，Named Volume，127.0.0.1:6333/6334
- 模型：`D:/AI-Models/Qwen3-Embedding-0.6B`、`D:/AI-Models/Qwen3-Reranker-0.6B`（各 1.2 GB）
- 推理层：`backend/app/inference/`（device.py / embedding_provider.py / reranker_provider.py）
- 诊断：`data/diagnostic_m0.json`、`data/runtime_profile.json`（GPU 正式版）、
  `data/diagnostic_m0_cpu_fallback.json`（CPU 回退验证）
- 测试：`backend/tests/test_sqlite_capability.py`（4 passed）

## M0 验收结果
- GPU 可生成 1024d embedding：PASS（norm=1.0001，finite）
- Reranker 返回 finite score：PASS（[0.9985, 0.0]，区分度好，顺序正确）
- CPU fallback 可工作：PASS
- Qdrant health OK：PASS（healthz check passed，v1.19.0）
- FTS5 trigram OK：PASS（pytest 4/4）

## Tests
- pytest: 4 passed
- M0 smoke (GPU cuda:1)：5/5 checks ok（torch/gpu_matmul/embedding/reranker）
- M0 smoke (CPU fallback)：通过

## Known Issues
1. **核显导致 GPU kernel 崩溃**：Ryzen 7600X3D 核显被 HIP 枚举为 device 0，
   torch 在其上启动 gfx1100 kernel 直接 0xC0000005 崩溃。
   已在 `device.py` 按最大显存自动选择 `cuda:1`（RX 7900 XTX）规避。
   所有推理代码必须使用 device.py 返回的设备字符串，禁止裸写 "cuda"。
2. **rocm-sdk 10.0.0（stable index whl-next）Windows 回归**：kernel launch 段错误
   （amdhip64_7.dll，见 TheRock issue #4958）。已锁定 7.13.0。
   升级前必须重跑 `scripts/run_m0_smoke.ps1`。
3. **FTS5 查询语法**：含 `-` / `:` 的标识符（CoWoS-L、EXE:5000）必须用双引号包裹，
   否则被解析为 column filter。M4 查询解析器需处理。
4. rocm-sdk test 的 hipconfig 控制台脚本存在 GBK 编码报错（UnicodeDecodeError），
   不影响运行时，属于 SDK 测试工具自身问题。

## Decisions
- ADR-001 依赖管理：pip + pyproject.toml + requirements-lock.txt；不引入 poetry/uv，
  torch 不写入 pyproject dependencies（避免 PyPI CUDA wheel 覆盖），经 AMD 索引单独安装。
- ADR-002 ROCm 版本：锁定 torch 2.9.1+rocm7.13.0（legacy stable index），
  10.0.0 存在 Windows kernel-launch 崩溃回归，等待 AMD 修复后评估升级。
- ADR-003 设备选择：多 GPU（含 iGPU）场景按最大显存选择并以显式 "cuda:<idx>" 传递；
  GPU 崩溃是进程级故障，包装脚本 `run_m0_smoke.ps1` 负责 CPU fallback 重跑。
