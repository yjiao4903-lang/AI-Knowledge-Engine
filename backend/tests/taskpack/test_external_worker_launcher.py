"""External Worker deterministic contracts, including P0 launch policy."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from app.taskpack.launcher import (
    USER_RUN_REQUIRED,
    ExternalExecutionPolicyError,
    ExternalWorkerLauncher,
    LauncherStateError,
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


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_launcher_registry_is_fixed_but_never_advertises_api_availability(tmp_path):
    root, _ = _ready_pack(tmp_path)
    which_calls: list[str] = []

    def forbidden_which(name: str):
        which_calls.append(name)
        raise AssertionError("P0 policy must fail before PATH/executable discovery")

    launcher = ExternalWorkerLauncher(root, which=forbidden_which)
    rows = launcher.describe()

    assert [row.id for row in rows] == ["codex", "claude", "terminal"]
    assert [row.available for row in rows] == [False, False, False]
    assert which_calls == []


@pytest.mark.parametrize("kind", ["codex", "claude", "terminal"])
def test_launch_ready_is_user_run_required_before_path_move_or_spawn(tmp_path, kind):
    root, pack = _ready_pack(tmp_path)
    calls = {"which": 0, "popen": 0}

    def forbidden_which(_name: str):
        calls["which"] += 1
        raise AssertionError("executable discovery must not run")

    def forbidden_popen(*_args, **_kwargs):
        calls["popen"] += 1
        raise AssertionError("subprocess creation must not run")

    launcher = ExternalWorkerLauncher(root, which=forbidden_which, popen=forbidden_popen)

    with pytest.raises(ExternalExecutionPolicyError, match=USER_RUN_REQUIRED):
        launcher.launch_ready(pack.name, kind)

    assert calls == {"which": 0, "popen": 0}
    assert pack.is_dir()
    assert not (root / "processing" / pack.name).exists()


def test_invalid_task_id_still_fails_before_external_policy(tmp_path):
    root, _ = _ready_pack(tmp_path)
    launcher = ExternalWorkerLauncher(root)

    with pytest.raises(LauncherStateError, match="非法 task_id"):
        launcher.launch_ready("../escape", "codex")


def test_unknown_launcher_still_fails_closed(tmp_path):
    root, pack = _ready_pack(tmp_path)
    launcher = ExternalWorkerLauncher(root)

    with pytest.raises(LauncherUnavailableError, match="不支持的 launcher"):
        launcher.launch_ready(pack.name, "arbitrary")  # type: ignore[arg-type]

    assert pack.is_dir()
    assert not (root / "processing" / pack.name).exists()


def test_worker_commands_are_fixed_headless_entrypoints_for_deterministic_unit_testing():
    """Command construction remains testable without executing any external process."""

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


def test_supervisor_completed_marker_moves_processing_to_completed_with_fake_process(tmp_path):
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


def test_supervisor_seals_only_deterministic_run_meta_hashes(tmp_path):
    root, source = _ready_pack(tmp_path)
    (source / "manifest.json").write_text('{"task_id":"test"}\n', encoding="utf-8")
    processing = root / "processing" / source.name
    processing.parent.mkdir(parents=True)
    source.rename(processing)

    def fake_external(_argv, **kwargs):
        cwd = Path(kwargs["cwd"])

        class FakeProcess:
            def wait(self):
                meta = {
                    "worker_tool": "codex",
                    "provider": "openai",
                    "model": "fixture-model",
                    "model_version": None,
                    "started_at": "2026-09-06T01:00:00+00:00",
                    "completed_at": "2026-09-06T01:01:00+00:00",
                    "prompt_version": "taskpack-synthesis-v1",
                    "prompt_sha256": None,
                    "task_manifest_sha256": None,
                    "input_tokens": None,
                    "output_tokens": None,
                }
                (cwd / "result" / "run_meta.json").write_text(
                    json.dumps(meta), encoding="utf-8"
                )
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
    completed = root / "completed" / source.name
    meta = json.loads((completed / "result" / "run_meta.json").read_text(encoding="utf-8"))
    assert meta["prompt_sha256"] == _sha256(completed / "AGENT_INSTRUCTION.md")
    assert meta["task_manifest_sha256"] == _sha256(completed / "manifest.json")
    assert meta["worker_tool"] == "codex"
    assert meta["model"] == "fixture-model"
    assert meta["started_at"] == "2026-09-06T01:00:00+00:00"
    assert meta["input_tokens"] is None


def test_supervisor_does_not_fabricate_missing_run_meta(tmp_path):
    root, source = _ready_pack(tmp_path)
    (source / "manifest.json").write_text('{"task_id":"test"}\n', encoding="utf-8")
    processing = root / "processing" / source.name
    processing.parent.mkdir(parents=True)
    source.rename(processing)
    (processing / "result" / "DONE").write_text("\n", encoding="utf-8")

    target = finalize_after_exit(processing, root, launcher="codex", exit_code=0)

    assert target == root / "completed" / source.name
    assert not (target / "result" / "run_meta.json").exists()


def test_missing_worker_marker_becomes_failed_with_diagnostic(tmp_path):
    root, source = _ready_pack(tmp_path)
    processing = root / "processing" / source.name
    processing.parent.mkdir(parents=True)
    source.rename(processing)

    target = finalize_after_exit(processing, root, launcher="codex", exit_code=0)

    assert target == root / "failed" / source.name
    assert (target / "result" / "FAILED").exists()
    assert (target / "result" / "launcher_error.json").exists()
