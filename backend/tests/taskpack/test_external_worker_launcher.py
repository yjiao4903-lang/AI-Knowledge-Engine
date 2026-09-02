"""P1 External Worker Launcher deterministic contracts."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from app.taskpack.launcher import (
    ExternalWorkerLauncher,
    LauncherUnavailableError,
)
from app.taskpack.worker_supervisor import (
    _FIXED_INSTRUCTION,
    build_external_command,
    finalize_after_exit,
    run_supervisor,
)


def _ready_pack(tmp_path: Path, task_id: str = "20260902_120000_test") -> tuple[Path, Path]:
    root = tmp_path / "taskpacks"
    pack = root / "outbox" / task_id
    (pack / "result").mkdir(parents=True)
    (pack / "AGENT_INSTRUCTION.md").write_text(
        "SECRET LONG TASKPACK PROMPT THAT MUST NOT BE COPIED TO COMMAND LINE\n",
        encoding="utf-8",
    )
    return root, pack


def test_launcher_registry_is_fixed_and_reports_availability(tmp_path):
    root, _ = _ready_pack(tmp_path)
    mapping = {
        "codex": "C:/tools/codex.cmd",
        "claude": None,
        "pwsh": "C:/Program Files/PowerShell/7/pwsh.exe",
    }
    launcher = ExternalWorkerLauncher(root, which=lambda name: mapping.get(name))

    rows = launcher.describe()
    assert [row.id for row in rows] == ["codex", "claude", "terminal"]
    assert [row.available for row in rows] == [True, False, True]


def test_launch_ready_moves_to_processing_and_spawns_only_supervisor(tmp_path):
    root, pack = _ready_pack(tmp_path)
    calls = []

    class FakeProcess:
        pid = 4321

    def fake_popen(argv, **kwargs):
        calls.append((argv, kwargs))
        return FakeProcess()

    launcher = ExternalWorkerLauncher(
        root,
        which=lambda name: "C:/tools/codex.cmd" if name == "codex" else None,
        popen=fake_popen,
    )
    result = launcher.launch_ready(pack.name, "codex")

    assert not pack.exists()
    assert result.task_path == root / "processing" / pack.name
    assert result.task_path.is_dir()
    assert result.pid == 4321

    argv, kwargs = calls[0]
    assert "worker_supervisor.py" in Path(argv[1]).name
    assert argv[-1] == "C:/tools/codex.cmd"
    assert kwargs["cwd"] == str(root.resolve())
    assert kwargs["shell"] is False
    # Browser/task prompt content is never copied into the launcher command line.
    assert "SECRET LONG TASKPACK PROMPT" not in " ".join(str(item) for item in argv)


def test_supervisor_spawn_failure_rolls_back_processing_to_ready(tmp_path):
    root, pack = _ready_pack(tmp_path)

    def boom(*_args, **_kwargs):
        raise OSError("cannot create supervisor")

    launcher = ExternalWorkerLauncher(
        root,
        which=lambda name: "C:/tools/codex.exe" if name == "codex" else None,
        popen=boom,
    )

    with pytest.raises(OSError, match="cannot create supervisor"):
        launcher.launch_ready(pack.name, "codex")

    assert pack.is_dir()
    assert not (root / "processing" / pack.name).exists()


def test_unavailable_launcher_does_not_move_taskpack(tmp_path):
    root, pack = _ready_pack(tmp_path)
    launcher = ExternalWorkerLauncher(root, which=lambda _name: None)

    with pytest.raises(LauncherUnavailableError):
        launcher.launch_ready(pack.name, "claude")

    assert pack.is_dir()
    assert not (root / "processing" / pack.name).exists()


def test_worker_commands_are_fixed_headless_entrypoints():
    codex = build_external_command("codex", "/usr/local/bin/codex")
    claude = build_external_command("claude", "/usr/local/bin/claude")

    assert codex[:3] == ["/usr/local/bin/codex", "exec", "--skip-git-repo-check"]
    assert codex[-1] == _FIXED_INSTRUCTION
    assert claude[:2] == ["/usr/local/bin/claude", "-p"]
    assert claude[-1] == _FIXED_INSTRUCTION
    assert "AGENT_INSTRUCTION.md" in _FIXED_INSTRUCTION
    assert len(_FIXED_INSTRUCTION) < 300

    with pytest.raises(ValueError):
        build_external_command("arbitrary", "/tmp/evil")


def test_supervisor_completed_marker_moves_processing_to_completed(tmp_path):
    root, source = _ready_pack(tmp_path)
    processing = root / "processing" / source.name
    processing.parent.mkdir(parents=True)
    source.rename(processing)

    def fake_external(_argv, **kwargs):
        cwd = Path(kwargs["cwd"])

        class FakeProcess:
            def wait(self):
                (cwd / "result" / "DONE").write_text("\n", encoding="utf-8")
                return 0

        return FakeProcess()

    rc = run_supervisor(
        root=root,
        task_id=processing.name,
        launcher="codex",
        executable="/usr/local/bin/codex",
        popen=fake_external,
    )

    assert rc == 0
    assert not processing.exists()
    assert (root / "completed" / source.name / "result" / "DONE").exists()


def test_missing_worker_marker_becomes_failed_with_diagnostic(tmp_path):
    root, source = _ready_pack(tmp_path)
    processing = root / "processing" / source.name
    processing.parent.mkdir(parents=True)
    source.rename(processing)

    target = finalize_after_exit(processing, root, launcher="codex", exit_code=0)

    assert target == root / "failed" / source.name
    assert (target / "result" / "FAILED").exists()
    assert (target / "result" / "launcher_error.json").exists()
