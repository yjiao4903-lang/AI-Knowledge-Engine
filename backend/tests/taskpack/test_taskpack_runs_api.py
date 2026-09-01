from app.api import taskpack_runs


def test_run_task_summary_is_read_only_and_metadata_only(tmp_path, monkeypatch):
    root = tmp_path / "runs" / "run-one" / "task_001" / "result"
    root.mkdir(parents=True)
    (root / "DONE").write_text("", encoding="utf-8")
    (root / "result.json").write_text(
        '{"task_id":"x","task_type":"summary","query":"q",'
        '"worker":{"tool":"codex","model":"m"},"claims":[{}],"tensions":[]}', encoding="utf-8")
    (root / "run_meta.json").write_text('{"worker_tool":"codex","model":"m"}', encoding="utf-8")
    monkeypatch.setattr(taskpack_runs, "RUNS_ROOT", tmp_path / "runs")
    response = taskpack_runs.get_run_task("run-one", "task_001")
    assert response["status"] == "COMPLETED"
    assert response["claims_count"] == 1
    assert "claims" not in response


def test_run_rejects_path_traversal(tmp_path, monkeypatch):
    monkeypatch.setattr(taskpack_runs, "RUNS_ROOT", tmp_path)
    try:
        taskpack_runs.get_run("..")
    except Exception as exc:
        assert getattr(exc, "status_code", None) == 404
    else:
        raise AssertionError("expected 404")
