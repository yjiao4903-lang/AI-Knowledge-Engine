"""Lightweight validation cache for completed TaskPacks.

The Task Center polls ``GET /api/synthesis/tasks`` and therefore calls Importer.scan()
frequently. A valid COMPLETED TaskPack intentionally has no success marker, so the
base importer would otherwise repeat the full deterministic Gate pipeline on every
poll.

This module keeps the existing TaskPack protocol intact and adds one sidecar cache:
``result/validation_cache.json``. The cache is reusable only when both
``result_hash`` and ``validation_version`` match. Explicit rescan always bypasses
it. The stale-evidence Gate is deliberately re-checked on cache hits because the
catalog can change independently of ``result.json``.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from app.taskpack.importer import (
    COMPLETED_DIR,
    DONE_MARKER,
    INVALID_MARKER,
    GateResult,
    ImportReport,
    TaskPackImporter,
)
from app.taskpack.manifest import sha256_file

VALIDATION_VERSION = "taskpack-gates-v1"
VALIDATION_CACHE_FILE = "result/validation_cache.json"


class CachingTaskPackImporter(TaskPackImporter):
    """TaskPackImporter with deterministic result-hash based validation reuse."""

    @staticmethod
    def _result_hash(pack: Path) -> str | None:
        path = pack / "result" / "result.json"
        if not path.exists():
            return None
        try:
            return sha256_file(path)
        except OSError:
            return None

    @staticmethod
    def _cache_path(pack: Path) -> Path:
        return pack / VALIDATION_CACHE_FILE

    def _read_cached_report(self, pack: Path, result_hash: str) -> ImportReport | None:
        path = self._cache_path(pack)
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if payload.get("validation_version") != VALIDATION_VERSION:
                return None
            if payload.get("result_hash") != result_hash:
                return None
            raw = payload.get("report") or {}
            report = ImportReport(
                task_id=str(raw.get("task_id") or pack.name),
                task_path=pack,
                passed=bool(raw.get("passed")),
                schema_valid=bool(raw.get("schema_valid")),
                citation_invalid=int(raw.get("citation_invalid") or 0),
                citation_coverage=raw.get("citation_coverage"),
                unsupported_claim_rate=raw.get("unsupported_claim_rate"),
                stale=bool(raw.get("stale")),
                details=dict(raw.get("details") or {}),
            )
            report.gates = [
                GateResult(
                    name=str(item["name"]),
                    passed=bool(item["passed"]),
                    failure=item.get("failure"),
                )
                for item in (raw.get("gates") or [])
                if isinstance(item, dict) and item.get("name")
            ]
            return report
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            return None

    def _write_cached_report(self, pack: Path, result_hash: str, report: ImportReport) -> None:
        path = self._cache_path(pack)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "validation_version": VALIDATION_VERSION,
            "result_hash": result_hash,
            "validated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "report": {
                "task_id": report.task_id,
                "passed": report.passed,
                "schema_valid": report.schema_valid,
                "citation_invalid": report.citation_invalid,
                "citation_coverage": report.citation_coverage,
                "unsupported_claim_rate": report.unsupported_claim_rate,
                "stale": report.stale,
                "details": report.details,
                "gates": [
                    {"name": g.name, "passed": g.passed, "failure": g.failure}
                    for g in report.gates
                ],
            },
        }
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def _refresh_live_stale_gate(self, pack: Path, report: ImportReport) -> ImportReport:
        """Re-check only catalog staleness while reusing all static validation Gates."""

        static_gates = [g for g in report.gates if g.name != "stale"]
        if any(not g.passed for g in static_gates):
            report.gates = static_gates
            report.passed = False
            report.stale = False
            return report

        stale_gates = self._gate_stale(pack)
        report.gates = static_gates + stale_gates
        report.stale = any(g.name == "stale" and not g.passed for g in stale_gates)
        report.passed = all(g.passed for g in report.gates)
        return report

    def import_task(self, pack: Path, *, force: bool = False) -> ImportReport:
        """Reuse a matching cached report; ``force=True`` executes the full Gate pipeline."""

        result_hash = self._result_hash(pack)
        if not force and result_hash is not None:
            cached = self._read_cached_report(pack, result_hash)
            if cached is not None:
                report = self._refresh_live_stale_gate(pack, cached)
                if not report.passed:
                    self._mark_invalid(pack, report)
                return report

        report = super().import_task(pack)
        if result_hash is not None:
            self._write_cached_report(pack, result_hash, report)
        return report

    def rescan_task(self, task_id: str) -> ImportReport | None:
        """Explicit rescan is a user request for fresh validation, so bypass the cache."""

        pack = self.locate(task_id)
        if pack is None:
            return None
        if pack.relative_to(self.root).parts[0] != COMPLETED_DIR:
            return None
        if not (pack / DONE_MARKER).exists():
            return None
        invalid_marker = pack / INVALID_MARKER
        if invalid_marker.exists():
            invalid_marker.unlink()
        return self.import_task(pack, force=True)
