"""P0 Issue #56: external-resource execution must be USER_RUN_REQUIRED."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api.synthesis import LaunchWorkerRequest, get_worker_launchers, launch_worker
from app.taskpack.importer import READY


class _Importer:
    def __init__(self, root: Path, pack: Path, *, status: str = READY) -> None:
        self.root = root
        self._pack = pack
        self._status = status

    def locate(self, task_id: str):
        return self._pack if task_id == self._pack.name else None

    def status_of(self, _pack: Path) -> str:
        return self._status


def _request(tmp_path: Path, *, status: str = READY):
    root = tmp_path / "taskpacks"
    pack = root / "outbox" / "20260912_120000_policy"
    (pack / "result").mkdir(parents=True)
    (pack / "AGENT_INSTRUCTION.md").write_text("fixture\n", encoding="utf-8")
    importer = _Importer(root, pack, status=status)
    state = SimpleNamespace(
        cfg=SimpleNamespace(taskpack=SimpleNamespace(enabled=True)),
        taskpack_builder=object(),
        taskpack_importer=importer,
    )
    return SimpleNamespace(app=SimpleNamespace(state=state)), pack


def test_launcher_discovery_exposes_user_run_required_and_no_available_launcher(tmp_path):
    request, _pack = _request(tmp_path)

    body = get_worker_launchers(request)

    assert body["execution_policy"] == "USER_RUN_REQUIRED"
    assert body["agent_launch_allowed"] is False
    assert [row["id"] for row in body["launchers"]] == ["codex", "claude", "terminal"]
    assert all(row["available"] is False for row in body["launchers"])


@pytest.mark.parametrize("kind", ["codex", "claude", "terminal"])
def test_api_launch_is_403_and_taskpack_stays_ready(tmp_path, kind):
    request, pack = _request(tmp_path)

    with pytest.raises(HTTPException) as caught:
        launch_worker(pack.name, LaunchWorkerRequest(launcher=kind), request)

    assert caught.value.status_code == 403
    assert "USER_RUN_REQUIRED" in str(caught.value.detail)
    assert pack.is_dir()
    assert not (pack.parents[1] / "processing" / pack.name).exists()


def test_non_ready_state_still_fails_before_policy_execution(tmp_path):
    request, pack = _request(tmp_path, status="PROCESSING")

    with pytest.raises(HTTPException) as caught:
        launch_worker(pack.name, LaunchWorkerRequest(launcher="codex"), request)

    assert caught.value.status_code == 409
    assert "当前状态=PROCESSING" in str(caught.value.detail)
    assert pack.is_dir()


def test_missing_task_still_returns_404(tmp_path):
    request, _pack = _request(tmp_path)

    with pytest.raises(HTTPException) as caught:
        launch_worker("missing-task", LaunchWorkerRequest(launcher="codex"), request)

    assert caught.value.status_code == 404
