"""Read-only Research OS integration smoke test.

Usage (both services running):
    python backend/scripts/integration_smoke.py

Environment overrides:
    KE_BASE=http://127.0.0.1:8765
    COGNITION_BASE=http://127.0.0.1:3220

The script performs no Cognition writes. If a validated TaskPack exists it also
checks the I8 proposal-candidate export contract.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

KE_BASE = os.environ.get("KE_BASE", "http://127.0.0.1:8765").rstrip("/")
COG_BASE = os.environ.get("COGNITION_BASE", "http://127.0.0.1:3220").rstrip("/")


def request_json(url: str, *, method: str = "GET", body: dict | None = None, timeout: int = 30):
    data = None
    headers = {}
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            return resp.status, json.loads(raw) if raw else None
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(raw)
        except Exception:
            payload = {"raw": raw}
        return exc.code, payload


def check(name: str, condition: bool, detail: str = "") -> bool:
    print(f"{'PASS' if condition else 'FAIL'}  {name}{' -- ' + detail if detail else ''}")
    return condition


def main() -> int:
    ok = True

    status, ke_health = request_json(f"{KE_BASE}/api/health")
    ok &= check("KE health", status == 200 and isinstance(ke_health, dict), f"http={status}")

    status, cog_health = request_json(f"{COG_BASE}/api/retrieval/health")
    reachable = bool(
        status == 200
        and isinstance(cog_health, dict)
        and isinstance(cog_health.get("retrieval"), dict)
        and cog_health["retrieval"].get("reachable") is True
    )
    ok &= check("Cognition retrieval proxy", reachable, f"http={status}")

    status, search = request_json(
        f"{COG_BASE}/api/retrieval/search",
        method="POST",
        body={"query": "HBM4", "mode": "exact", "top_k": 3},
        timeout=60,
    )
    search_ok = status == 200 and isinstance(search, dict) and isinstance(search.get("results"), list)
    ok &= check("Cognition -> KE search", search_ok, f"http={status}")

    status, tasks = request_json(f"{KE_BASE}/api/synthesis/tasks")
    tasks_ok = status == 200 and isinstance(tasks, dict) and isinstance(tasks.get("tasks"), list)
    ok &= check("TaskPack task list", tasks_ok, f"http={status}")

    if tasks_ok:
        validated = next(
            (t for t in tasks["tasks"] if t.get("status") in {"COMPLETED", "IMPORTED"}),
            None,
        )
        if validated:
            task_id = validated["task_id"]
            status, bridge = request_json(
                f"{KE_BASE}/api/synthesis/tasks/{task_id}/proposal-candidates"
            )
            bridge_ok = (
                status == 200
                and bridge.get("auto_apply") is False
                and isinstance(bridge.get("proposal_payload", {}).get("items"), list)
            )
            ok &= check("TaskPack -> Proposal candidate", bridge_ok, f"task={task_id} http={status}")
        else:
            print("SKIP  TaskPack -> Proposal candidate -- no validated task available")

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
