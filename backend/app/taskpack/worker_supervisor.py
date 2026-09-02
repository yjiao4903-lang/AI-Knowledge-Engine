"""Detached lifecycle supervisor for one externally launched TaskPack.

This module is intentionally stdlib-only so the API can spawn it with the current
Python interpreter and then return immediately.  It runs one fixed external CLI,
waits for it to exit, and converts ``processing/`` into ``completed/`` or
``failed/`` according to the TaskPack's DONE / FAILED markers.

It is orchestration, not a model provider: no API clients, credentials, model
selection, retrieval, or Cognition writes live here.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

_FIXED_INSTRUCTION = (
    "Read and follow AGENT_INSTRUCTION.md in the current working directory. "
    "Complete this TaskPack only from its provided files and write the required "
    "result files and DONE or FAILED marker into result/."
)
_TASK_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")


def _safe_task_id(value: str) -> bool:
    return ".." not in value and _TASK_ID_RE.fullmatch(value) is not None


def _validate_executable(kind: str, executable: str) -> None:
    stem = Path(executable).stem.lower()
    if kind == "codex" and stem != "codex":
        raise ValueError("codex launcher executable mismatch")
    if kind == "claude" and stem != "claude":
        raise ValueError("claude launcher executable mismatch")
    if kind == "terminal" and stem not in {"pwsh", "powershell"}:
        raise ValueError("terminal launcher executable mismatch")


def build_external_command(kind: str, executable: str) -> list[str]:
    """Return the fixed external command; no browser/user command is accepted."""

    if kind not in {"codex", "claude", "terminal"}:
        raise ValueError(f"unsupported launcher: {kind}")
    _validate_executable(kind, executable)

    if kind == "codex":
        args = [executable, "exec", "--skip-git-repo-check", _FIXED_INSTRUCTION]
    elif kind == "claude":
        args = [executable, "-p", _FIXED_INSTRUCTION]
    else:
        args = [
            executable,
            "-NoLogo",
            "-NoExit",
            "-Command",
            "Write-Host 'TaskPack ready. Read AGENT_INSTRUCTION.md and run the external worker here.'",
        ]

    # npm-installed CLIs are commonly .cmd wrappers on Windows.  Invoke those
    # explicitly through COMSPEC while still keeping shell=False and a fixed argv.
    if os.name == "nt" and Path(executable).suffix.lower() in {".cmd", ".bat"}:
        comspec = os.environ.get("COMSPEC") or "cmd.exe"
        return [comspec, "/d", "/c", *args]
    return args


def _write_launcher_error(pack: Path, *, launcher: str, exit_code: int | None, message: str) -> None:
    result = pack / "result"
    result.mkdir(parents=True, exist_ok=True)
    payload = {
        "launcher": launcher,
        "exit_code": exit_code,
        "message": message,
        "recorded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    (result / "launcher_error.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _move_final(pack: Path, root: Path, destination: str) -> Path:
    target_dir = root / destination
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / pack.name
    if target.exists():
        raise FileExistsError(f"TaskPack lifecycle target already exists: {target}")
    pack.rename(target)
    return target


def finalize_after_exit(pack: Path, root: Path, *, launcher: str, exit_code: int) -> Path:
    """Map the external process outcome to the existing TaskPack directory state."""

    done = pack / "result" / "DONE"
    failed = pack / "result" / "FAILED"

    if done.exists() and not failed.exists():
        return _move_final(pack, root, "completed")

    if not failed.exists():
        _write_launcher_error(
            pack,
            launcher=launcher,
            exit_code=exit_code,
            message=(
                "external worker exited without result/DONE or result/FAILED; "
                "TaskPack marked FAILED by launcher supervisor"
            ),
        )
        failed.write_text("launcher supervisor: missing DONE/FAILED marker\n", encoding="utf-8")
    return _move_final(pack, root, "failed")


def run_supervisor(
    *,
    root: Path,
    task_id: str,
    launcher: str,
    executable: str,
    popen=subprocess.Popen,
) -> int:
    if not _safe_task_id(task_id):
        raise ValueError(f"unsafe task_id: {task_id}")
    root = root.resolve()
    processing = (root / "processing").resolve()
    pack = (processing / task_id).resolve()
    if pack.parent != processing or not pack.is_dir():
        raise FileNotFoundError(f"processing TaskPack not found: {task_id}")

    command = build_external_command(launcher, executable)
    result = pack / "result"
    result.mkdir(parents=True, exist_ok=True)

    try:
        if launcher == "terminal":
            kwargs: dict = {"cwd": str(pack), "shell": False}
            if os.name == "nt":
                kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
            process = popen(command, **kwargs)
            exit_code = int(process.wait())
        else:
            stdout_path = result / "launcher_stdout.log"
            stderr_path = result / "launcher_stderr.log"
            with stdout_path.open("w", encoding="utf-8") as stdout, stderr_path.open(
                "w", encoding="utf-8"
            ) as stderr:
                process = popen(
                    command,
                    cwd=str(pack),
                    stdin=subprocess.DEVNULL,
                    stdout=stdout,
                    stderr=stderr,
                    shell=False,
                )
                exit_code = int(process.wait())
    except BaseException as exc:
        _write_launcher_error(pack, launcher=launcher, exit_code=None, message=f"launch failed: {exc}")
        (result / "FAILED").write_text("launcher supervisor: launch failed\n", encoding="utf-8")
        _move_final(pack, root, "failed")
        return 1

    try:
        finalize_after_exit(pack, root, launcher=launcher, exit_code=exit_code)
    except BaseException as exc:
        # Keep the pack in processing if lifecycle finalization itself fails; this
        # is safer than copying/deleting and makes the filesystem state inspectable.
        if pack.exists():
            _write_launcher_error(
                pack,
                launcher=launcher,
                exit_code=exit_code,
                message=f"lifecycle finalization failed: {exc}",
            )
        return 2
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--launcher", required=True, choices=("codex", "claude", "terminal"))
    parser.add_argument("--executable", required=True)
    args = parser.parse_args()
    return run_supervisor(
        root=Path(args.root),
        task_id=args.task_id,
        launcher=args.launcher,
        executable=args.executable,
    )


if __name__ == "__main__":
    raise SystemExit(main())
