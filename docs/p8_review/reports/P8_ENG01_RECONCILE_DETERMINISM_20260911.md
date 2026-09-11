# P8-ENG-01 · Reconcile 确定性修复报告（2026-09-11）

**Issue**：LOCAL-DEV #32（父控制 #30）
**分支**：`local-dev/32-reconcile-determinism`（基于权威 `main` `41838aa0`）
**执行者**：LOCAL-DEV
**性质**：引擎缺陷修复，不改变架构 / schema / 公开契约；不改 Legacy Golden；不做全量破坏性重建。

## 0. 结论

`backend/app/indexing/docid_policy.py::build_index_plan` 只在**本批候选内**保证 doc_id 唯一，
对 catalog 既有文档只在「同 sha 重复拷贝」时消歧。由此产生两个缺陷：

1. **跨批次同 id 不同内容静默覆盖**（主因）。
   新文件的 `default_doc_id` 与库内既有文档相同但内容不同时，裸 id 被分配给新文件；
   `index_file` 随即 `DELETE FROM chunks WHERE document_id=?` 并替换 documents 行，
   **既有文档被删除**。下一次 reconcile 又把旧文件当 NEW 写回，形成 45↔77 抖动。
2. **重复拷贝组残留未分配候选**。
   当某 sha 组的 canonical 与库内同 sha 时，代码 `continue` 直接跳过，
   未把该组其余路径标记为重复；`apply_scan` 对未分配路径回退到默认 doc_id 再次写入，
   造成 manifest `source_path` 抖动（M04）。

## 1. 真实语料复现（只读，未写库）

在冻结语料（3,566 docs / 296,380 chunks，Qdrant `kb_chunks_full_v1`）上只读运行
`scan()` + `build_index_plan()`：

| 项 | 修复前 | 修复后 |
|---|---|---|
| 库内 `M09` | `M09_Transformer…_最终报告.md`（77 chunks） | 不变 |
| 磁盘新增 `M09_男女身体构造差异_最终报告.md` | 解析 `report_code=M09`，**分配裸 id `M09`** → 覆盖既有文档 | 分配 `M09__14936ea1` |
| 磁盘新增 `…\_最终报告.md`（通用 stem） | 分配裸 id `_最终报告`，覆盖库内同类文档 | 分配 `_最终报告__e3e6f8dd` |
| 计划未覆盖候选 | 1 条（旗舰备份 M04 副本，回退写入） | 0 条 |

- 两个 M09 文件：`M09_Transformer…` = **77 chunks / 61 sections**；`M09_男女身体构造差异…` = **45 chunks / 34 sections**。
  与 P8 报告记录的 `M09 45↔77` 完全一致。
- 根因层定位：`doc_id policy / 跨批次碰撞`（Issue 预期调查层 §2），非 parser/chunker 非确定性；
  同一文件重复解析结果稳定。

## 2. 修复

`build_index_plan`：

- 将 ADR-013 已有的「同 doc_id 不同内容 → sha8 消歧」规则**延伸到 catalog 既有文档**：
  库内文档保留裸 id，新候选一律 `id__sha8`，从源头阻止 DELETE+替换覆盖。
- 同 sha 组判定为库内内容重复时，**整组路径**记为 `EXCLUDED_DUPLICATE`，不留未分配候选。
- `MODIFIED` 且路径等于库内 `source_path` 的候选仍沿用原 id（正常更新不受影响）。

`pipeline.py` / `catalog_pipeline.py::apply_scan`：

- 计划未分配身份的候选**禁止回退到默认 doc_id**，改为抛出 `IndexInconsistencyError`
  并计入 `stats["errors"]`（最小containment boundary，杜绝静默覆盖）。

## 3. 验证

| 项 | 命令 / 方式 | 结果 |
|---|---|---|
| 新增确定性单测 | `pytest tests/test_docid_policy.py` | 通过（含 4 个 P8-ENG-01 用例） |
| 新增端到端回归 | `pytest tests/test_p8_reconcile_determinism.py` | 通过（M09 覆盖 / 通用 `_最终报告` / 幂等） |
| 反证（修复前） | 还原 3 个源文件后跑新用例 | 5 个用例中 4 个失败 → 用例非空转 |
| 既有 lightweight 套件 | CI 同款 pytest 列表 | 119 passed |
| 沙箱真实 Qdrant 冒烟 | 临时 catalog + 临时 collection + fake embedder，6 次 reconcile | 既有 M09 恒 5 chunks；新文档 `M09__…` 3 chunks；SQLite==FTS==Qdrant；幂等 |
| 真实环境一致性（只读） | SQLite vs Qdrant 全量计数 | documents 3,566 / chunks 296,380 / Qdrant 296,380，`consistent=true`；M04/M09 四表一致 |
| Legacy 金标可解析（不改金标） | 50 题 `relevant_sections` 对照 sections 表 | 68/68 解析，`unresolved=0`；gold sha256 `aa0412a2…` 与冻结值一致 |
| 编译 | `compileall app/indexing` | OK |

CI 已把 `tests/test_docid_policy.py`、`tests/test_p8_reconcile_determinism.py` 纳入轻量套件。

## 4. 边界与未做

- 未修改 `data/catalog_full.db`、未做全量重抽取/重分块/重索引（无 WEB-CONTROL 授权）。
- 未修改 Legacy Golden（sha 未变）。
- 未改动 Qdrant 生产 collection（冒烟用临时 collection 并已删除）。
- 未改动架构 / schema / 公开 API 契约。
- 验证时冻结的真实 catalog 仍为 296,380（修复只影响后续 reconcile 的计划，不影响现有数据）。
- 本地无关改动 `config/config.yaml`、`docker-compose.yml` 未纳入本次提交。

## 5. 影响面（同类的其他碰撞）

只读扫描确认另有两类同源碰撞已被同一修复覆盖：
- 通用 stem `_最终报告.md`（磁盘 14 个，多个主题），此前会争用同一 doc_id `_最终报告`；
- 跨层 M 系列副本（旗舰备份 / 版本存档）此前在 canonical 与库内同 sha 时残留未分配候选。

修复后这些候选分别走 sha8 消歧或整组重复排除，不再写入既有文档。
