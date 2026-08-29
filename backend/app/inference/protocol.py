"""Inference Worker 协议（M7，Addendum §14）。

任务消息：{"task_id": str, "type": str, "payload": dict}
结果消息：{"task_id": str, "ok": bool, "result": any, "error": str}
事件消息（非应答）：{"event": "ready"|"error", ...}

任务类型：embed_query / embed_documents / rerank / health / shutdown /
test_crash（测试用，os._exit(1)）/ test_sleep（测试用，模拟 hang）。
"""

TASK_EMBED_QUERY = "embed_query"
TASK_EMBED_DOCS = "embed_documents"
TASK_RERANK = "rerank"
TASK_HEALTH = "health"
TASK_SHUTDOWN = "shutdown"
