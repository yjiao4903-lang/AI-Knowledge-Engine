"""KE-owned validation cache for completed TaskPacks.

The Task Center polls ``GET /api/synthesis/tasks`` and therefore calls
``Importer.scan()`` frequently. A valid COMPLETED TaskPack intentionally has no
success marker, so the base importer would otherwise repeat the full deterministic
Gate pipeline on every poll.

Validation reuse is KE authority, not Worker evidence. Cache state therefore lives
outside every TaskPack/Worker result directory under ``_ke_state/validation_cache``.
A cache hit is accepted only when a deterministic binding over the manifest, every
manifest-declared immutable input, ``result.json`` and ``run_meta.json`` matches.
Legacy ``result/validation_cache.json`` files are never read as authority.

Explicit rescan always bypasses the cache. The stale-evidence Gate is deliberately
re-checked on every cache hit because the catalog can change independently of the
immutable TaskPack/result bytes.
"""

from __future__ import annotations

import hashlib
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
from app.taskpack.schemas import is_safe_task_id

VALIDATION_VERSION = "taskpack-gates-v2"
VALIDATION_STATE_DIR = "_ke_state/validation_cache"
LEGACY_VALIDATION_CACHE_FILE = "result/validation_cache.json"

_STATIC_GATE_NAMES = {
    "evidence_parse",
    "manifest",
    "result_schema",
    "task_id",
    "prompt_sha",
    "evidence_membership",
    "citation_invalid",
    "citation_coverage",
    "unsupported_claim",
}


class CachingTaskPackImporter(TaskPackImporter):
    """TaskPackImporter with deterministic KE-owned static validation reuse."""

    @staticmethod
    def _result_hash(pack: Path) -> str | None:
        path = pack / "result" / "result.json"
        if not path.exists():
            return None
        try:
            return sha256_file(path)
        except OSError:
            return None

    def _cache_path(self, pack: Path) -> Path | None:
        """Return the KE-owned cache path; never place authority under ``result/``."""

        if not is_safe_task_id(pack.name):
            return None
        return self.root / VALIDATION_STATE_DIR / f"{pack.name}.json"

    def _validation_binding(self, pack: Path) -> str | None:
        """Bind cached authority to every byte used by the static Gate pipeline."""

        manifest = self._read_manifest(pack)
        if manifest is None or manifest.files is None:
            return None

        names = set(manifest.files)
        names.update({"manifest.json", "result/result.json", "result/run_meta.json"})
        hashes: dict[str, str] = {}
        try:
            for name in sorted(names):
                path = pack / name
                if not path.is_file():
                    return None
                hashes[name] = sha256_file(path)
        except OSError:
            return None

        payload = {
            "task_id": pack.name,
            "files": hashes,
        }
        canonical = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(canonical).hexdigest()

    def _read_cached_report(self, pack: Path, binding_hash: str) -> ImportReport | None:
        path = self._cache_path(pack)
        if path is None or not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if payload.get("validation_version") != VALIDATION_VERSION:
                return None
            if payload.get("task_id") != pack.name:
                return None
            if payload.get("authority_binding_hash") != binding_hash:
                return None
            raw = payload.get("report") or {}
            if not isinstance(raw, dict) or raw.get("task_id") != pack.name:
                return None
            report = ImportReport(
                task_id=pack.name,
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
            static_gates = [g for g in report.gates if g.name != "stale"]
            static_names = {g.name for g in static_gates}
            if not report.passed:
                return None
            if not _STATIC_GATE_NAMES.issubset(static_names):
                return None
            if any(not g.passed for g in static_gates):
                return None
            return report
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            return None

    def _write_cached_report(
        self,
        pack: Path,
        binding_hash: str,
        report: ImportReport,
    ) -> None:
        """Persist successful static authority atomically in the KE-owned namespace."""

        if not report.passed:
            return
        path = self._cache_path(pack)
        if path is None:
            return
        static_names = {g.name for g in report.gates if g.name != "stale" and g.passed}
        if not _STATIC_GATE_NAMES.issubset(static_names):
            return

        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "validation_version": VALIDATION_VERSION,
            "task_id": pack.name,
            "authority_binding_hash": binding_hash,
            "result_hash": self._result_hash(pack),
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
        temp = path.with_suffix(path.suffix + ".tmp")
        temp.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temp.replace(path)

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
        """Reuse matching KE state; ``force=True`` executes the full Gate pipeline."""

        binding_hash = self._validation_binding(pack)
        if not force and binding_hash is not None:
            cached = self._read_cached_report(pack, binding_hash)
            if cached is not None:
                report = self._refresh_live_stale_gate(pack, cached)
                if not report.passed:
                    self._mark_invalid(pack, report)
                return report

        report = super().import_task(pack)
        if report.passed:
            # Recompute after authoritative Gates to avoid persisting a binding
            # derived before a concurrent local file change.
            binding_hash = self._validation_binding(pack)
            if binding_hash is not None:
                self._write_cached_report(pack, binding_hash, report)
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
