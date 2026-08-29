"""下载 Qwen3 模型到 D:/AI-Models（M0-04/05 前置）。

首次下载后可设置 HF_HUB_OFFLINE=1 完全离线运行。
"""

from __future__ import annotations

import sys
from pathlib import Path

from huggingface_hub import snapshot_download

MODELS = {
    "Qwen/Qwen3-Embedding-0.6B": "D:/AI-Models/Qwen3-Embedding-0.6B",
    "Qwen/Qwen3-Reranker-0.6B": "D:/AI-Models/Qwen3-Reranker-0.6B",
}


def main() -> int:
    failed = []
    for repo, local in MODELS.items():
        target = Path(local)
        if (target / "config.json").exists():
            print(f"[skip] {repo} already at {local}")
            continue
        print(f"[download] {repo} -> {local}")
        try:
            snapshot_download(repo_id=repo, local_dir=str(target))
        except Exception as exc:
            print(f"[error] {repo}: {exc}")
            failed.append(repo)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
