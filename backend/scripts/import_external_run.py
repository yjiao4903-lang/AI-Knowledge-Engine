"""将外部 TaskPack 候选集安全导入 data/taskpack_golden/runs。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT / "backend") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app.taskpack.external_run_importer import import_external_run  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("run_id")
    parser.add_argument(
        "--runs-root",
        type=Path,
        default=PROJECT_ROOT / "data" / "taskpack_golden" / "runs",
    )
    args = parser.parse_args()
    target = import_external_run(args.source, args.runs_root, args.run_id)
    print(target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
