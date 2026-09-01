from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.core.config import Config
from app import main
from app.api import search, taskpack_runs


class _Manager:
    device = "cpu"
    device_kind = "cpu"
    fallback_to_cpu = True
    total_restarts = 0

    def shutdown(self):
        return None

    def is_alive(self):
        return True


def test_app_starts_and_runs_api_when_index_pipeline_unavailable(tmp_path, monkeypatch):
    cfg = Config()
    cfg.paths.data_dir = str(tmp_path / "data")
    cfg.paths.log_dir = str(tmp_path / "logs")
    cfg.sqlite.path = str(tmp_path / "catalog.db")
    cfg.taskpack.enabled = False
    cfg.cognition.enabled = False
    cfg.indexing.startup_scan = False
    cfg.indexing.periodic_reconcile_seconds = 0

    class _UnavailablePipeline:
        def __init__(self, *args, **kwargs):
            raise RuntimeError("qdrant unavailable")

    monkeypatch.setattr(main, "InferenceManager", lambda cfg: _Manager())
    monkeypatch.setattr(main, "DenseRetriever", lambda cfg: object())
    monkeypatch.setattr(main, "RerankerService", lambda cfg, manager: None)
    monkeypatch.setattr(main, "SearchEngine", lambda *args, **kwargs: object())
    monkeypatch.setattr("app.indexing.pipeline.IndexPipeline", _UnavailablePipeline)

    runs = tmp_path / "runs"
    result = runs / "run-one" / "task_001" / "result"
    result.mkdir(parents=True)
    (result / "DONE").write_text("", encoding="utf-8")
    (result / "result.json").write_text('{"task_id":"x","claims":[],"tensions":[]}', encoding="utf-8")
    monkeypatch.setattr(taskpack_runs, "RUNS_ROOT", runs)

    with TestClient(main.create_app(cfg)) as client:
        response = client.get("/api/taskpack/runs")
        assert response.status_code == 200
        assert response.json()["runs"][0]["run_id"] == "run-one"


def test_dense_search_reports_service_unavailable_without_qdrant():
    body = search.SearchRequest(query="test")
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(qdrant_available=False)))
    try:
        search.search(body, request)
    except Exception as exc:
        assert getattr(exc, "status_code", None) == 503
        assert "Qdrant" in str(getattr(exc, "detail", ""))
    else:
        raise AssertionError("dense search should not report a fake success")
