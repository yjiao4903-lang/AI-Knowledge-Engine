# Implementation Status

## Current Milestone
M3 Semantic Chunker（下一步）

## Completed
- [x] M0 环境与硬件验证（2026-08-29）
- [x] M1 项目骨架与 Storage（2026-08-29）
- [x] M2 Markdown Parser（2026-08-29）

## In Progress
- [ ] M3

## M2 交付物
- `app/parser/metadata_parser.py`：YAML front matter + 旧式 blockquote（`**键**：值`，
  支持一行多对、`｜` 分隔、反引号清理、report_code 前缀提取 M04_... -> M04）
- `app/parser/heading_tree.py`：section_id 生成（"第 3 章"->ch3、"3.2"->ch3-2、
  "(1)"->父:o1、无编号->全局序号兜底）+ section_type 分类规则
- `app/parser/special_blocks.py`：prose/table/code/mermaid/formula/ascii_diagram
  块级识别（fence 逐字符匹配、表格连续 | 行、$$ 公式块、ASCII 图特征字符）
- `app/parser/evidence.py`：[L1]-[L5] 解析（min level + 完整数组）
- `app/parser/markdown_parser.py`：主入口，全部 Section/Block 保留 1-based 行号；
  heading_path 以文档标题为根（spec §10.3，已链到根的不重复前置）

## M2 验收结果（M04 fixture，816 行）
- 64 sections（8×H1 / 23×H2 / 33×H3），无重复 section_id，无 warnings
- metadata：report_code=M04、domain=Domain II、completed_at=2026-08-27 全部正确
- 执行摘要/目录/监测看板/参考文献/审计 分别识别为 summary/toc/monitoring/
  reference/audit
- 130 blocks：103 prose、12 ascii_diagram（顶部因果拓扑图）、8 code、6 table、
  1 mermaid；行号全部在文档范围内

## Tests
- pytest: 31 passed
  - metadata_parser 4、heading_tree 3、m04 验收 6、
  - migrations 5、repositories 6、qdrant 集成 1、health 2、sqlite capability 4

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
