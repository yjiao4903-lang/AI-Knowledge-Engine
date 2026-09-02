"""Local append-only retrieval feedback ledger for Personal Research OS.

This is intentionally lightweight telemetry for one local user. It records search
impressions and explicit usefulness / Evidence selection actions so retrieval can be
tuned later from real usage rather than synthetic guesses.

The ledger is JSONL under ``paths.data_dir`` and is not part of formal Cognition.
Writing feedback must never affect retrieval ranking or trigger model work.
"""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

FEEDBACK_FILE_NAME = "retrieval_feedback.jsonl"
FEEDBACK_SCHEMA_VERSION = "1.0"
_APPEND_LOCK = threading.Lock()


def feedback_path(data_dir: str | Path) -> Path:
    """Return the local feedback ledger path without introducing a new config tree."""

    return Path(data_dir) / FEEDBACK_FILE_NAME


def append_feedback_events(
    path: str | Path,
    events: Iterable[Mapping[str, Any]],
) -> int:
    """Append events atomically enough for the local single-process FastAPI runtime.

    A server-side UTC timestamp is added to every row. Existing rows are never
    rewritten, which keeps the ledger easy to inspect, back up, and analyze later.
    """

    rows = [dict(event) for event in events]
    if not rows:
        return 0

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    recorded_at = datetime.now(timezone.utc).isoformat(timespec="milliseconds")

    with _APPEND_LOCK:
        with target.open("a", encoding="utf-8", newline="\n") as handle:
            for row in rows:
                row["schema_version"] = FEEDBACK_SCHEMA_VERSION
                row["timestamp"] = recorded_at
                handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")))
                handle.write("\n")
    return len(rows)


def build_impression_events(
    *,
    search_id: str,
    query: str,
    mode: str,
    rerank: bool,
    results: Iterable[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Build one impression row per returned result using final displayed rank."""

    events: list[dict[str, Any]] = []
    for result in results:
        chunk_id = str(result.get("chunk_id") or "").strip()
        rank = result.get("rank")
        if not chunk_id or not isinstance(rank, int) or rank < 1:
            continue
        events.append(
            {
                "search_id": search_id,
                "query": query,
                "chunk_id": chunk_id,
                "document_id": result.get("document_id"),
                "rank": rank,
                "mode": mode,
                "rerank": rerank,
                "event_type": "impression",
                "useful": None,
                "selected_as_evidence": None,
            }
        )
    return events
