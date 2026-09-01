# 返回目录约定

外部窗口完成后，用户无需手工合并 JSON，也无需修改原始 TaskPack。请在本包根目录建立以下返回结构：

```text
RETURN/
└─ codex-external-smoke/
   ├─ task_001/result/result.json
   ├─ task_001/result/run_meta.json
   ├─ task_001/result/DONE       # 或 FAILED + error.json
   ├─ task_009/result/...
   ├─ task_018/result/...
   └─ task_025/result/...
```

只将外部 Worker 生成的 `result/` 内容放入对应 `RETURN/codex-external-smoke/task_NNN/result/`。四个原始 `task_NNN/` 目录必须保持不变；不要在原始目录写入结果，不要移动、重命名或合并任务目录。

本地回收时直接带回整个 `RETURN/` 文件夹。主负责人将按任务包内 manifest 和协议重新校验；返回目录中的结果仍不等于 Task 9/10 PASS。
