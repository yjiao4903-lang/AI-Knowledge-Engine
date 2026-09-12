"""External Worker launch policy for the personal Research OS.

TaskPack preparation/import remains supported, but project-controlled API/agent
paths MUST NOT start external identity-bound workers.  Real external execution is
a user-presence boundary and is represented as ``USER_RUN_REQUIRED``.

This module intentionally keeps the historical launcher registry/result types for
API compatibility, while making the execution path fail closed *before* PATH
resolution, TaskPack lifecycle mutation, or subprocess creation.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Literal

from app.taskpack.schemas import is_safe_task_id

LauncherKind = Literal["codex", "claude", "terminal"]
LAUNCHER_KINDS: tuple[LauncherKind, ...] = ("codex", "claude", "terminal")
USER_RUN_REQUIRED = "USER_RUN_REQUIRED"


class LauncherError(RuntimeError):
    """Base launcher error exposed as a readable API failure."""


class LauncherUnavailableError(LauncherError):
    """Requested launcher identifier is not part of the fixed registry."""


class LauncherStateError(LauncherError):
    """TaskPack cannot be launched from its current lifecycle state."""


class ExternalExecutionPolicyError(LauncherError):
    """Project-controlled external execution is prohibited by P0 policy."""


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

_POLICY_MESSAGE = (
    "USER_RUN_REQUIRED: project/API/agent-controlled external Worker launch is disabled. "
    "Prepare the TaskPack only; if a real external run is necessary, the user must "
    "perform it manually outside agent/window control and return the artifacts."
)


class ExternalWorkerLauncher:
    """Compatibility facade that deliberately cannot execute external workers.

    ``which`` and ``popen`` remain injectable only so existing callers/tests do not
    need a constructor migration.  P0 policy requires that neither callback is
    invoked by ``describe`` or ``launch_ready``.
    """

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

    def describe(self) -> list[LauncherInfo]:
        """Return the historical registry without advertising API executability."""

        return [
            LauncherInfo(id=kind, label=_LABELS[kind], available=False)
            for kind in LAUNCHER_KINDS
        ]

    def launch_ready(self, task_id: str, kind: LauncherKind) -> LaunchResult:
        """Fail closed before any external-resource or filesystem side effect."""

        if kind not in LAUNCHER_KINDS:
            raise LauncherUnavailableError(f"不支持的 launcher: {kind}")
        if not is_safe_task_id(task_id):
            raise LauncherStateError(f"非法 task_id: {task_id}")
        raise ExternalExecutionPolicyError(_POLICY_MESSAGE)
