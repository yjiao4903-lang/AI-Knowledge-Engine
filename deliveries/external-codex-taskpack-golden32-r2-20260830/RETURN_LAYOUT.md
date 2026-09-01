# Golden32 R2 返回目录

外部 Worker 只应将结果写入包根目录下的：

```text
RETURN/
└─ codex-external-golden32-r2/
   ├─ task_001/result/result.json
   ├─ task_001/result/run_meta.json
   ├─ task_001/result/DONE       # 失败时为 FAILED + error.json
   ├─ task_002/result/...
   ├─ ...
   └─ task_032/result/...
```

每个任务的 result 目录相互独立，不要合并 result.json，不要改动或覆盖输入包。用户只需把完整 `RETURN/` 文件夹带回本地；本地负责人将按每个原始任务的 manifest、Importer Gate 以及 Task 10 语义规则复核。
