"""External Worker Launcher for the personal Research OS.

The launcher is deliberately *not* a model provider.  It knows only three fixed
local targets (Codex CLI, Claude Code CLI, or a terminal), moves one READY
TaskPack into ``processing/``, and starts a detached stdlib-only supervisor.

No arbitrary executable, shell command, model API key, or prompt body comes from
the browser.  The external worker receives only a short fixed instruction to
read the TaskPack's own ``AGENT_INSTRUCTION.md``.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Literal

from app.taskpack.schemas import is_safe_task_id

LauncherKind = Literal["codex", "claude", "terminal"]
LAUNCHER_KINDS: tuple[LauncherKind, ...] = ("codex", "claude", "terminal")


class LauncherError(RuntimeError):
    """Base launcher error exposed as a readable API failure."""


class LauncherUnavailableError(LauncherError):
    """Requested fixed launcher executable is not installed / not on PATH."""


class LauncherStateError(LauncherError):
    """TaskPack cannot be launched from its current lifecycle state."""


@dataclass(frozen=True)
class LauncherInfo:
    id: LauncherKind
    label: str
    available: bool


@dataclass(frozen=True)
class LaunchResult:
    launcher: LauncherKind
    pid: int
    task_path: Path


_LABELS: dict[LauncherKind, str] = {
    "codex": "Codex CLI",
    "claude": "Claude Code",
    "terminal": "Terminal",
}


class ExternalWorkerLauncher:
    """Move a READY TaskPack to processing and start a detached supervisor."""

    def __init__(
        self,
        root: str | Path,
        *,
        which: Callable[[str], str | None] = shutil.which,
        popen: Callable[..., subprocess.Popen] = subprocess.Popen,
    ) -> None:
        self.root = Path(root).resolve()
        self.which = which
        self.popen = popen

    def _resolve_executable(self, kind: LauncherKind) -> str | None:
        if kind == "codex":
            return self.which("codex")
        if kind == "claude":
            return self.which("claude")
        return self.which("pwsh") or self.which("powershell.exe") or self.which("powershell")

    def describe(self) -> list[LauncherInfo]:
        return [
            LauncherInfo(id=kind, label=_LABELS[kind], available=self._resolve_executable(kind) is not None)
            for kind in LAUNCHER_KINDS
        ]

    def launch_ready(self, task_id: str, kind: LauncherKind) -> LaunchResult:
        if kind not in LAUNCHER_KINDS:
            raise LauncherUnavailableError(f"不支持的 launcher: {kind}")
        if not is_safe_task_id(task_id):
            raise LauncherStateError(f"非法 task_id: {task_id}")

        executable = self._resolve_executable(kind)
        if executable is None:
            raise LauncherUnavailableError(f"{_LABELS[kind]} 可执行文件未找到，请先安装并确保已加入 PATH")

        outbox = (self.root / "outbox").resolve()
        processing = (self.root / "processing").resolve()
        source = (outbox / task_id).resolve()
        target = processing / task_id

        if source.parent != outbox or not source.is_dir():
            raise LauncherStateError("只有 outbox/ 中的 READY TaskPack 可以启动外部 Worker")
        instruction = source / "AGENT_INSTRUCTION.md"
        if not instruction.is_file():
            raise LauncherStateError("AGENT_INSTRUCTION.md 缺失，拒绝启动")

        processing.mkdir(parents=True, exist_ok=True)
        if target.exists():
            raise LauncherStateError(f"processing 目标已存在: {target}")

        # Rename first so the Task Center immediately reflects PROCESSING and the
        # external worker receives the canonical processing path.  If supervisor
        # creation itself fails, roll back atomically to READY.
        source.rename(target)
        try:
            supervisor = Path(__file__).with_name("worker_supervisor.py").resolve()
            argv = [
                sys.executable,
                str(supervisor),
                "--root",
                str(self.root),
                "--task-id",
                task_id,
                "--launcher",
                kind,
                "--executable",
                executable,
            ]
            kwargs: dict = {
                # The supervisor must not use the moving TaskPack as *its own* cwd;
                # otherwise Windows can prevent processing/ -> completed/failed rename.
                "cwd": str(self.root),
                "stdin": subprocess.DEVNULL,
                "stdout": subprocess.DEVNULL,
                "stderr": subprocess.DEVNULL,
                "shell": False,
                "close_fds": True,
            }
            if os.name == "nt":
                kwargs["creationflags"] = (
                    getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
                    | getattr(subprocess, "DETACHED_PROCESS", 0)
                    | getattr(subprocess, "CREATE_NO_WINDOW", 0)
                )
            else:
                kwargs["start_new_session"] = True
            process = self.popen(argv, **kwargs)
        except BaseException:
            # A launcher must never strand a TaskPack in PROCESSING merely because
            # the supervisor process could not be created.
            if target.exists() and not source.exists():
                target.rename(source)
            raise

        return LaunchResult(launcher=kind, pid=int(process.pid), task_path=target)
