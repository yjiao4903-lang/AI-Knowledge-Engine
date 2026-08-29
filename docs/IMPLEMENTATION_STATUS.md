# Implementation Status

## Current Milestone
M2 Markdown Parser（下一步）

## Completed
- [x] M0 环境与硬件验证（2026-08-29）
- [x] M1 项目骨架与 Storage（2026-08-29）

## In Progress
- [ ] M2

## M1 交付物
- core：`app/core/config.py`（pydantic + YAML）、`logging.py`（console + JSON lines）、
  `errors.py`（spec §46 错误分类）、`health.py`
- storage：`sqlite.py`（WAL/FK/query_only）、`migrations.py`（幂等 schema + meta +
  FTS 能力探针）、`qdrant.py`（QdrantStore，ensure_collections 幂等）
- repositories：`repositories/knowledge.py`（Document/Section/Chunk/IndexJob +
  FTS terms/trigram 同步 + 文档删除级联）
- API 骨架：`app/main.py`（`/api/health`）
- schema：documents / sections / chunks / indexing_jobs / document_tombstones /
  chunks_fts_terms / chunks_fts_trigram / meta（spec §8）

## M1 验收结果
- pytest storage passes：18 passed（migrations 5、repositories 6、qdrant 集成 1、
  health 2、sqlite capability 4）
- clean init works：PASS
- second init idempotent：PASS（重复 init 不破坏已有数据）
- Qdrant ensure_collections 幂等：PASS（v1.19.0 实测）
- 真机启动：uvicorn + /api/health 返回 status=ok（sqlite/qdrant ok，
  inference device=cuda:1）

## Tests
- pytest: 18 passed
- M0 smoke（GPU）：持续有效（未改动推理层行为，仅新增 device_kind）

## Known Issues
1. **核显导致 GPU kernel 崩溃**：Ryzen 7600X3D 核显被 HIP 枚举为 device 0，
   torch 在其上启动 gfx1100 kernel 直接 0xC0000005 崩溃。
   已在 `device.py` 按最大显存自动选择 `cuda:1`（RX 7900 XTX）规避。
   所有推理代码必须使用 device.py 返回的设备字符串，禁止裸写 "cuda"。
2. **rocm-sdk 10.0.0（stable index whl-next）Windows 回归**：kernel launch 段错误
   （amdhip64_7.dll，见 TheRock issue #4958）。已锁定 7.13.0。
   升级前必须重跑 `scripts/run_m0_smoke.ps1`。
3. **FTS5 查询语法**：含 `-` / `:` 的标识符（CoWoS-L、EXE:5000）必须用双引号包裹，
   否则被解析为 column filter。M4 查询解析器需处理（已在测试中固化）。
4. rocm-sdk test 的 hipconfig 控制台脚本存在 GBK 编码报错（UnicodeDecodeError），
   不影响运行时，属于 SDK 测试工具自身问题。

## Decisions
- ADR-001 依赖管理：pip + pyproject.toml + requirements-lock.txt；不引入 poetry/uv，
  torch 不写入 pyproject dependencies（避免 PyPI CUDA wheel 覆盖），经 AMD 索引单独安装。
- ADR-002 ROCm 版本：锁定 torch 2.9.1+rocm7.13.0（legacy stable index），
  10.0.0 存在 Windows kernel-launch 崩溃回归，等待 AMD 修复后评估升级。
- ADR-003 设备选择：多 GPU（含 iGPU）场景按最大显存选择并以显式 "cuda:<idx>" 传递；
  GPU 崩溃是进程级故障，包装脚本 `run_m0_smoke.ps1` 负责 CPU fallback 重跑。
- ADR-004 SQLite 只读连接用 `PRAGMA query_only=ON`（Windows 上
  `file:...?mode=ro` URI 打开不稳定）；FTS 能力探针使用独立 in-memory 连接。
- ADR-005 FTS 为独立 virtual table（chunk_id UNINDEXED），由 ChunkRepository 与
  chunks 表同事务同步，删除文档时级联清理，避免 external-content 同步复杂性。
