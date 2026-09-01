# R2.1 返回目录

外部 Worker 只应把结果写入：

```text
RETURN/
└─ codex-external-smoke-r2-1/
   └─ task_018/
      └─ result/
         ├─ result.json
         ├─ run_meta.json
         └─ DONE                 # 失败时为 FAILED + error.json
```

原始 `task_018/` 必须保持不变；不要移动、覆盖、合并或追加任何历史结果。用户只需把整个 `RETURN/` 文件夹带回本地。
