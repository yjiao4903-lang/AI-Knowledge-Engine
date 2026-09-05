import subprocess
import sys


def test_real_base_runtime_without_qdrant_or_model_stack():
    """A fresh Python process must complete the base Research OS path model-free.

    This is deliberately stronger than monkeypatching ``InferenceManager``. The
    child interpreter blocks Qdrant and local-model imports before importing the
    FastAPI application, uses only temporary paths, enters the real lifespan, and
    exercises report lexical retrieval, Cognition lexical retrieval, Evidence
    read, and TaskPack creation.
    """

    code = r'''
import importlib.abc
import sys
import tempfile
from pathlib import Path


class BlockSemanticStack(importlib.abc.MetaPathFinder):
    BLOCKED = ("qdrant_client", "torch", "transformers", "sentence_transformers")

    def find_spec(self, fullname, path=None, target=None):
        if any(fullname == name or fullname.startswith(name + ".") for name in self.BLOCKED):
            raise ImportError(f"{fullname} intentionally blocked by DL-01F smoke")
        return None


sys.meta_path.insert(0, BlockSemanticStack())

from fastapi.testclient import TestClient

from app.cognition.scanner import scan as cognition_scan
from app.core.config import Config
from app.main import create_app


REPORT_MARKER = "BASESMOKE_REPORT_917"
COGNITION_MARKER = "BASESMOKE_COG_918"

with tempfile.TemporaryDirectory(prefix="aike-dl01f-") as temp:
    root = Path(temp)
    reports = root / "reports"
    cognition = root / "cognition"
    questions = cognition / "03_问题池"
    data = root / "data"
    taskpacks = data / "taskpacks"
    logs = root / "logs"
    reports.mkdir(parents=True)
    questions.mkdir(parents=True)

    report_path = reports / "SMOKE_REPORT.md"
    report_path.write_text(
        "# Base Runtime Report\n\n"
        "## Evidence\n\n"
        f"The lexical base runtime marker is {REPORT_MARKER}. "
        "This passage exists only for the isolated process smoke.\n",
        encoding="utf-8",
    )
    cognition_path = questions / "smoke_question.md"
    cognition_path.write_text(
        "# Base Runtime Cognition\n\n"
        "## Open Question\n\n"
        f"Can the read-only cognition catalog find {COGNITION_MARKER}?\n",
        encoding="utf-8",
    )

    cfg = Config()
    cfg.paths.data_dir = str(data)
    cfg.paths.log_dir = str(logs)
    cfg.paths.model_dir = str(root / "missing-models")
    cfg.sqlite.path = str(data / "catalog.db")
    cfg.knowledge_base.roots = [str(reports)]
    cfg.qdrant.url = "http://127.0.0.1:1"
    cfg.embedding.local_path = str(root / "missing-models" / "embedding")
    cfg.reranker.local_path = str(root / "missing-models" / "reranker")
    cfg.indexing.startup_scan = False
    cfg.indexing.periodic_reconcile_seconds = 0
    cfg.indexing.watcher_enabled = False

    cfg.cognition.enabled = True
    cfg.cognition.root = str(cognition)
    cfg.cognition.catalog_path = str(data / "catalog_cognition.db")
    cfg.cognition.include_dirs = ["03_问题池"]
    cfg.cognition.startup_scan = False
    cfg.cognition.periodic_reconcile_seconds = 0

    cfg.taskpack.enabled = True
    cfg.taskpack.root_dir = str(taskpacks)
    cfg.taskpack.periodic_scan_seconds = 0

    app = create_app(cfg)
    with TestClient(app) as client:
        # Real lifespan entered while qdrant/model imports are blocked.
        assert client.app.state.qdrant_available is False
        assert client.app.state.pipeline is None
        assert client.app.state.manager.is_alive() is False
        assert "torch" not in sys.modules
        assert "transformers" not in sys.modules

        # Report catalog: real API scan -> lexical search.
        scan_response = client.post("/api/index/scan")
        assert scan_response.status_code == 200, scan_response.text
        assert scan_response.json()["applied"]["indexed"] == 1

        report_search = client.post(
            "/api/search",
            json={
                "query": REPORT_MARKER,
                "options": {"mode": "lexical", "rerank": False, "top_k": 10},
            },
        )
        assert report_search.status_code == 200, report_search.text
        report_hits = report_search.json()["results"]
        assert report_hits
        assert any(REPORT_MARKER in (hit.get("snippet") or "") for hit in report_hits)

        # Evidence read uses the actual catalog chunk created above.
        chunks_response = client.get("/api/documents/SMOKE_REPORT/chunks")
        assert chunks_response.status_code == 200, chunks_response.text
        chunks = chunks_response.json()["chunks"]
        assert chunks
        evidence = next(chunk for chunk in chunks if REPORT_MARKER in chunk["plain_text"])
        chunk_response = client.get(f"/api/chunks/{evidence['id']}")
        assert chunk_response.status_code == 200, chunk_response.text
        assert REPORT_MARKER in chunk_response.json()["plain_text"]

        # Cognition catalog is independently populated through the real model-free
        # scanner/catalog, then queried through the public lexical API.
        cog = client.app.state.cognition
        assert cog["enabled"] is True
        assert cog["semantic_available"] is False
        result = cognition_scan(cfg, cog["conn"])
        stats = cog["catalog_pipeline"].apply_scan(result)
        assert stats["indexed"] == 1

        cognition_search = client.post(
            "/api/search/cognition",
            json={
                "query": COGNITION_MARKER,
                "options": {"mode": "lexical", "rerank": False, "top_k": 10},
            },
        )
        assert cognition_search.status_code == 200, cognition_search.text
        cognition_hits = cognition_search.json()["results"]
        assert cognition_hits
        assert any(COGNITION_MARKER in (hit.get("snippet") or "") for hit in cognition_hits)
        assert cognition_search.json()["scope"] == "cognition"

        # Planning/TaskPack path consumes explicit Evidence without any model call.
        task_response = client.post(
            "/api/synthesis/tasks",
            json={
                "task_type": "summary",
                "query": "Summarize the isolated base-runtime evidence.",
                "evidence_context_mode": "none",
                "evidence_refs": [
                    {
                        "source_type": "report",
                        "document_id": "SMOKE_REPORT",
                        "section_id": evidence["section_id"],
                        "chunk_id": evidence["id"],
                        "start_line": evidence["start_line"],
                        "end_line": evidence["end_line"],
                    }
                ],
                "cognition_context": [],
            },
        )
        assert task_response.status_code == 200, task_response.text
        task = task_response.json()
        assert task["status"] == "READY"
        task_path = Path(task["task_path"])
        assert task_path.is_dir()
        assert (task_path / "task.json").exists()
        assert (task_path / "evidence.jsonl").exists()

        task_detail = client.get(f"/api/synthesis/tasks/{task['task_id']}")
        assert task_detail.status_code == 200, task_detail.text
        assert task_detail.json()["status"] == "READY"
        assert task_detail.json()["evidence_count"] >= 1

        # No base operation above is allowed to start the inference process.
        assert client.app.state.manager.is_alive() is False
        assert "torch" not in sys.modules
        assert "transformers" not in sys.modules

print("DL01F_BASE_RUNTIME_OK")
'''

    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=".",
        text=True,
        capture_output=True,
        check=False,
        timeout=60,
    )

    assert result.returncode == 0, f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    assert "DL01F_BASE_RUNTIME_OK" in result.stdout
