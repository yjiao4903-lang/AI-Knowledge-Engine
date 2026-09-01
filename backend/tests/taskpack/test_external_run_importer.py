from pathlib import Path

import pytest

from app.taskpack import external_run_importer as mod


def _candidate(root: Path, ids: list[str]) -> Path:
    source = root / "candidate"
    for task_id in ids:
        pack = source / task_id / "result"
        pack.mkdir(parents=True)
        (source / task_id / "task.yaml").write_text("task_id: x\n", encoding="utf-8")
        (pack / "result.json").write_text("{}", encoding="utf-8")
        (pack / "run_meta.json").write_text("{}", encoding="utf-8")
        (pack / "DONE").write_text("", encoding="utf-8")
    return source


def test_success_publishes_only_after_all_preflight(tmp_path, monkeypatch):
    ids = ["task_001", "task_002"]
    source = _candidate(tmp_path, ids)
    monkeypatch.setattr(mod, "_preflight", lambda importer, pack: object())
    target = mod.import_external_run(source, tmp_path / "runs", "run-ok", expected_ids=ids)
    assert target.is_dir()
    assert sorted(p.name for p in target.iterdir()) == ids
    assert not list((tmp_path / "runs").glob(".run-ok.stage-*"))


def test_collision_does_not_overwrite(tmp_path, monkeypatch):
    ids = ["task_001"]
    source = _candidate(tmp_path, ids)
    runs = tmp_path / "runs"
    target = runs / "run-collision"
    target.mkdir(parents=True)
    (target / "sentinel").write_text("keep", encoding="utf-8")
    with pytest.raises(FileExistsError):
        mod.import_external_run(source, runs, "run-collision", expected_ids=ids)
    assert (target / "sentinel").read_text(encoding="utf-8") == "keep"


def test_preflight_failure_cleans_stage_and_leaves_no_run(tmp_path, monkeypatch):
    ids = ["task_001", "task_002"]
    source = _candidate(tmp_path, ids)
    calls = 0

    def fail_second(importer, pack):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise ValueError("bad result")
        return object()

    monkeypatch.setattr(mod, "_preflight", fail_second)
    runs = tmp_path / "runs"
    with pytest.raises(ValueError, match="bad result"):
        mod.import_external_run(source, runs, "run-fail", expected_ids=ids)
    assert not (runs / "run-fail").exists()
    assert not list(runs.glob(".run-fail.stage-*"))
