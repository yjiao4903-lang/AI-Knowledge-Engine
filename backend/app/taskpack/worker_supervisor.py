"""Fail-closed compatibility boundary for historical External Worker supervision.

Project code may prepare TaskPacks, ingest user-supplied results, and perform
pure/local deterministic result finalization.  It must not construct or spawn
Codex, Claude, PowerShell, or any other identity-bound External Worker.

The historical ``build_external_command`` and ``run_supervisor`` symbols remain
only so stale callers fail closed with ``USER_RUN_REQUIRED``.  They deliberately
refuse before executable validation/discovery, command construction, TaskPack
filesystem mutation, or subprocess creation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from app.taskpack.launcher import ExternalExecutionPolicyError, USER_RUN_REQUIRED

_POLICY_MESSAGE = (
    "USER_RUN_REQUIRED: direct worker_supervisor execution is disabled. "
    "Prepare the TaskPack only; the user may manually run an external tool outside "
    "project/agent control and return the resulting local artifacts for import."
)
_SUPPORTED_LAUNCHERS = ("codex", "claude", "terminal")


def _refuse_external_execution() -> None:
    raise ExternalExecutionPolicyError(_POLICY_MESSAGE)


def build_external_command(kind: str, executable: str) -> list[str]:
    """Compatibility shim: never return executable External Worker argv."""

    # Keep the old signature for stale imports, but fail before inspecting the
    # executable or constructing any command line.
    del kind, executable
    _refuse_external_execution()


def _write_launcher_error(pack: Path, *, launcher: str, exit_code: int | None, message: str) -> None:
    """Write a deterministic local lifecycle diagnostic.

    This helper is retained only for local result-finalization compatibility.  It
    is not reachable from the fail-closed execution entrypoints above.
    """

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


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()


def seal_run_meta_hashes(pack: Path) -> bool:
    """Seal deterministic TaskPack-input hashes in an existing run_meta.json.

    This pure/local helper does not fabricate a missing run_meta.json and does not
    execute or discover any external Worker.
    """

    path = pack / "result" / "run_meta.json"
    instruction = pack / "AGENT_INSTRUCTION.md"
    manifest = pack / "manifest.json"
    if not path.is_file() or not instruction.is_file() or not manifest.is_file():
        return False
    try:
        raw = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return False
    if not isinstance(raw, dict):
        return False

    raw["prompt_sha256"] = _sha256_file(instruction)
    raw["task_manifest_sha256"] = _sha256_file(manifest)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(raw, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)
    return True


def _move_final(pack: Path, root: Path, destination: str) -> Path:
    target_dir = root / destination
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / pack.name
    if target.exists():
        raise FileExistsError(f"TaskPack lifecycle target already exists: {target}")
    pack.rename(target)
    return target


def finalize_after_exit(pack: Path, root: Path, *, launcher: str, exit_code: int) -> Path:
    """Finalize already-returned local artifacts without starting any process.

    The name is retained for compatibility with existing deterministic result
    fixtures.  Callers must supply a TaskPack whose result markers already exist;
    this function does not run, discover, or construct an External Worker command.
    """

    done = pack / "result" / "DONE"
    failed = pack / "result" / "FAILED"

    if done.exists() and not failed.exists():
        seal_run_meta_hashes(pack)
        return _move_final(pack, root, "completed")

    if not failed.exists():
        _write_launcher_error(
            pack,
            launcher=launcher,
            exit_code=exit_code,
            message=(
                "returned local artifacts contain neither result/DONE nor result/FAILED; "
                "TaskPack marked FAILED by deterministic finalizer"
            ),
        )
        failed.write_text("deterministic finalizer: missing DONE/FAILED marker\n", encoding="utf-8")
    return _move_final(pack, root, "failed")


def run_supervisor(
    *,
    root: Path,
    task_id: str,
    launcher: str,
    executable: str,
    popen: Callable[..., object] | None = None,
) -> int:
    """Historical callable retained only as a hard fail-closed policy boundary."""

    # Deliberately do not resolve ``root``, inspect ``task_id``/``executable``,
    # create result files, build argv, or call the injected ``popen`` callback.
    del root, task_id, launcher, executable, popen
    _refuse_external_execution()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--launcher", required=True, choices=_SUPPORTED_LAUNCHERS)
    parser.add_argument("--executable", required=True)
    args = parser.parse_args()
    try:
        return run_supervisor(
            root=Path(args.root),
            task_id=args.task_id,
            launcher=args.launcher,
            executable=args.executable,
        )
    except ExternalExecutionPolicyError as exc:
        # Explicit nonzero CLI result without a traceback and, critically, without
        # touching the TaskPack or invoking an external executable.
        print(str(exc), file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
