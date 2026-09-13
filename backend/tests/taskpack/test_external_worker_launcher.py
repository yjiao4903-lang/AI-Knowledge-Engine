"""External Worker deterministic contracts and P0 execution-policy regressions."""

from __future__ import annotations

import ast
import hashlib
import json
import sys
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
    build_external_command,
    finalize_after_exit,
    main as supervisor_main,
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


def _processing_pack(tmp_path: Path) -> tuple[Path, Path]:
    root, source = _ready_pack(tmp_path)
    processing = root / "processing" / source.name
    processing.parent.mkdir(parents=True)
    source.rename(processing)
    return root, processing


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _snapshot(path: Path) -> list[tuple[str, bytes | None]]:
    rows: list[tuple[str, bytes | None]] = []
    for item in sorted(path.rglob("*")):
        rel = item.relative_to(path).as_posix()
        rows.append((rel, item.read_bytes() if item.is_file() else None))
    return rows


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


@pytest.mark.parametrize("kind", ["codex", "claude", "terminal"])
def test_command_builder_never_returns_external_worker_argv(kind):
    with pytest.raises(ExternalExecutionPolicyError, match=USER_RUN_REQUIRED):
        build_external_command(kind, f"/should/not/be/inspected/{kind}")


@pytest.mark.parametrize("kind", ["codex", "claude", "terminal"])
def test_direct_supervisor_callable_is_user_run_required_with_zero_side_effects(tmp_path, kind):
    root, processing = _processing_pack(tmp_path)
    before = _snapshot(root)
    calls = {"popen": 0}

    def forbidden_popen(*_args, **_kwargs):
        calls["popen"] += 1
        raise AssertionError("P0 supervisor path must never create a subprocess")

    with pytest.raises(ExternalExecutionPolicyError, match=USER_RUN_REQUIRED):
        run_supervisor(
            root=root,
            task_id=processing.name,
            launcher=kind,
            executable=f"/fake/{kind}",
            popen=forbidden_popen,
        )

    assert calls["popen"] == 0
    assert processing.is_dir()
    assert _snapshot(root) == before
    result = processing / "result"
    assert not (result / "launcher_stdout.log").exists()
    assert not (result / "launcher_stderr.log").exists()
    assert not (result / "launcher_error.json").exists()
    assert not (result / "DONE").exists()
    assert not (result / "FAILED").exists()
    assert not (root / "completed" / processing.name).exists()
    assert not (root / "failed" / processing.name).exists()


def test_direct_supervisor_cli_returns_nonzero_without_moving_taskpack(
    tmp_path, monkeypatch, capsys
):
    root, processing = _processing_pack(tmp_path)
    before = _snapshot(root)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "worker_supervisor",
            "--root",
            str(root),
            "--task-id",
            processing.name,
            "--launcher",
            "codex",
            "--executable",
            "/fake/codex",
        ],
    )

    rc = supervisor_main()

    captured = capsys.readouterr()
    assert rc != 0
    assert USER_RUN_REQUIRED in captured.err
    assert processing.is_dir()
    assert _snapshot(root) == before


def test_static_taskpack_runtime_contains_no_process_spawn_calls():
    """Regression guard against reintroducing executable TaskPack orchestration."""

    taskpack_dir = Path(__file__).resolve().parents[2] / "app" / "taskpack"
    forbidden = {
        "subprocess.Popen",
        "subprocess.run",
        "subprocess.call",
        "subprocess.check_call",
        "subprocess.check_output",
        "os.system",
        "os.popen",
    }
    violations: list[str] = []

    for path in sorted(taskpack_dir.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        aliases: dict[str, str] = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name in {"subprocess", "os"}:
                        aliases[alias.asname or alias.name] = alias.name
            elif isinstance(node, ast.ImportFrom) and node.module in {"subprocess", "os"}:
                for alias in node.names:
                    aliases[alias.asname or alias.name] = f"{node.module}.{alias.name}"

        def resolve(expr: ast.expr) -> str | None:
            if isinstance(expr, ast.Name):
                return aliases.get(expr.id, expr.id)
            if isinstance(expr, ast.Attribute):
                base = resolve(expr.value)
                return f"{base}.{expr.attr}" if base else expr.attr
            return None

        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = resolve(node.func)
            if name in forbidden or (isinstance(node.func, ast.Attribute) and node.func.attr == "popen"):
                violations.append(f"{path.name}:{node.lineno}:{name}")

    assert violations == []


def test_deterministic_finalizer_seals_existing_run_meta_without_external_execution(tmp_path):
    root, processing = _processing_pack(tmp_path)
    (processing / "manifest.json").write_text('{"task_id":"test"}\n', encoding="utf-8")
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
    (processing / "result" / "run_meta.json").write_text(json.dumps(meta), encoding="utf-8")
    (processing / "result" / "DONE").write_text("\n", encoding="utf-8")

    target = finalize_after_exit(processing, root, launcher="manual", exit_code=0)

    assert target == root / "completed" / processing.name
    sealed = json.loads((target / "result" / "run_meta.json").read_text(encoding="utf-8"))
    assert sealed["prompt_sha256"] == _sha256(target / "AGENT_INSTRUCTION.md")
    assert sealed["task_manifest_sha256"] == _sha256(target / "manifest.json")
    assert sealed["worker_tool"] == "codex"
    assert sealed["model"] == "fixture-model"
    assert sealed["started_at"] == "2026-09-06T01:00:00+00:00"
    assert sealed["input_tokens"] is None


def test_deterministic_finalizer_does_not_fabricate_missing_run_meta(tmp_path):
    root, processing = _processing_pack(tmp_path)
    (processing / "manifest.json").write_text('{"task_id":"test"}\n', encoding="utf-8")
    (processing / "result" / "DONE").write_text("\n", encoding="utf-8")

    target = finalize_after_exit(processing, root, launcher="manual", exit_code=0)

    assert target == root / "completed" / processing.name
    assert not (target / "result" / "run_meta.json").exists()


def test_missing_return_marker_becomes_failed_with_diagnostic(tmp_path):
    root, processing = _processing_pack(tmp_path)

    target = finalize_after_exit(processing, root, launcher="manual", exit_code=0)

    assert target == root / "failed" / processing.name
    assert (target / "result" / "FAILED").exists()
    assert (target / "result" / "launcher_error.json").exists()
