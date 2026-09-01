# RETURN Layout

外部 Codex 完成后，将结果复制到：

```text
RETURN/
└─ codex-external-smoke-r2/
   ├─ task_001/result/{result.json,run_meta.json,DONE}
   ├─ task_009/result/{result.json,run_meta.json,DONE}
   ├─ task_018/result/{result.json,run_meta.json,DONE}
   └─ task_025/result/{result.json,run_meta.json,DONE}
```

R2 结果必须有新的 `prompt_sha256` 和 `task_manifest_sha256`；不得从 R1 或现有 runs 复制结果文件。
