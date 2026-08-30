"""Synthesis 编排 Service（主计划 §38）：resolve → prompt → provider → validate → 日志。

失败行为（§38/§39）：
- Timeout / Provider 不可用 → SynthesisUnavailableError（不创建 Draft）；
- Invalid Schema → 允许有限自动 retry，仍失败则 SynthesisInvalidError；
- 主模型失败 → 尝试 fallback_model（若有）；
- 任何情况下都不写 Cognition（L1A 硬约束）。

日志（§37）：记录 request_id/task_type/model/prompt_version/evidence_count/latency/
schema_valid/citation_coverage/unsupported_claim_rate；不落 Cognition 与 Evidence 全文。
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import time

from app.core.errors import (
    SynthesisInvalidError,
    SynthesisUnavailableError,
)
from app.synthesis.grounding import EvidenceResolver, provided_chunk_ids
from app.synthesis.provider import ProviderMetrics, SynthesisProvider
from app.synthesis.prompt import build_messages
from app.synthesis.schemas import (
    GeneratorInfo,
    SynthesisDraft,
    SynthesisRequest,
)
from app.synthesis.validator import ValidationReport, extract_partial, validate_draft

logger = logging.getLogger(__name__)

_FENCE_RE = re.compile(r"^```(?:json)?\s*(.*?)\s*```$", re.DOTALL | re.MULTILINE)
# qwen3 思考模式产物：模型在正式回答前输出 <think>…</think> 推理块
_THINK_RE = re.compile(r"<think>|<THINK>|/\w*think\w*", re.IGNORECASE)


def _ms(t0: float) -> int:
    return int((time.time() - t0) * 1000)


class SynthesisService:
    def __init__(
        self,
        cfg,
        provider: SynthesisProvider,
        resolver: EvidenceResolver,
    ) -> None:
        self.cfg = cfg.synthesis if hasattr(cfg, "synthesis") else cfg
        self.provider = provider
        self.resolver = resolver

    # ---- generator 任务级溯源（§36）----
    def _generator(self, model: str) -> GeneratorInfo:
        return GeneratorInfo(
            provider=self.provider.provider_name,
            model=model,
            prompt_version=self.cfg.prompt_version,
        )

    def synthesize(
        self,
        req: SynthesisRequest,
        *,
        request_id: str | None = None,
        timing: dict | None = None,
    ) -> SynthesisDraft:
        """生成 SynthesisDraft；`timing` 若传入则被填充为逐相位耗时/计量字典。

        timing keys（供 eval harness 聚合）：
        resolve_ms / prompt_build_ms / llm_total_ms / validate_ms / total_ms /
        llm_calls / retries / model / fallback_used /
        load_ms / prefill_ms / generation_ms / ttft_ms（=prefill 代理）/
        input_tokens / output_tokens / prefill_tok_per_s / gen_tok_per_s / thinking_detected。
        """
        started = time.time()
        rid = request_id or _short_id(req.query)
        t = {} if timing is None else timing
        t0 = started

        resolved = self.resolver.resolve(
            req.evidence_refs,
            max_evidence=self.cfg.max_evidence,
            evidence_max_chars=self.cfg.evidence_max_chars,
        )
        t["resolve_ms"] = _ms(t0)
        provided = provided_chunk_ids(resolved)

        messages = build_messages(req.task_type, req.query, req.cognition_context, resolved)
        t["prompt_build_ms"] = _ms(t0)

        # 主模型 try -> fallback -> retry invalid schema / invalid citation（§38）
        used_model: str | None = None
        candidate: tuple[SynthesisDraft, ValidationReport] | None = None
        final_raw: str | None = None
        llm_calls = 0
        llm_total_ms = 0.0
        validate_ms = 0.0
        metrics_list: list[ProviderMetrics | None] = []
        fallback_used = False
        for i, model in enumerate(self._model_sequence()):
            if i > 0:
                fallback_used = True
            for _ in range(self.cfg.max_invalid_retries + 1):
                c0 = time.time()
                try:
                    raw, calls = self._call_with_schema_retry(messages, model, metrics_list)
                except SynthesisUnavailableError:
                    logger.warning("synthesis provider model=%s unavailable; fallback", model)
                    raw, calls = None, 0
                    break
                llm_calls += calls
                llm_total_ms += (time.time() - c0) * 1000
                if raw is None:
                    break
                final_raw = raw
                v0 = time.time()
                draft = self._build_draft(req, resolved, model, raw, rid)
                report = validate_draft(draft, provided)
                validate_ms += (time.time() - v0) * 1000
                used_model = model
                candidate = (draft, report)
                if not report.citation_invalid:
                    break
            if candidate is not None and not candidate[1].citation_invalid:
                break
        if candidate is None:
            raise SynthesisUnavailableError("synthesis provider 不可用", detail={"request_id": rid})

        draft, report = candidate

        # 相位计量（评估窗口用）
        final_m = next((m for m in reversed(metrics_list) if m is not None), None)
        t.update({
            "model": used_model,
            "fallback_used": fallback_used,
            "llm_calls": llm_calls,
            "retries": max(0, llm_calls - 1),
            "llm_total_ms": round(llm_total_ms),
            "validate_ms": round(validate_ms),
            "total_ms": int((time.time() - started) * 1000),
            "load_ms": round(final_m.load_ms, 1) if final_m else None,
            "prefill_ms": round(final_m.prefill_ms, 1) if final_m else None,
            "generation_ms": round(final_m.generation_ms, 1) if final_m else None,
            "ttft_ms": round(final_m.prefill_ms, 1) if final_m else None,
            "input_tokens": final_m.input_tokens if final_m else None,
            "output_tokens": final_m.output_tokens if final_m else None,
            "prefill_tok_per_s": round(final_m.prefill_tok_per_s, 1)
            if final_m and final_m.prefill_tok_per_s is not None else None,
            "gen_tok_per_s": round(final_m.gen_tok_per_s, 1)
            if final_m and final_m.gen_tok_per_s is not None else None,
            "thinking_detected": bool(_THINK_RE.search(final_raw or "")),
        })

        # 日志（§37：不进全文）
        logger.info(
            "synthesis id=%s task=%s model=%s pv=%s evidence=%d latency_ms=%d "
            "schema=%s cov=%s unsup=%s invalid_cites=%d calls=%d "
            "in_tok=%s out_tok=%s gen_tok/s=%s",
            rid, req.task_type, used_model, self.cfg.prompt_version, len(resolved),
            int((time.time() - started) * 1000), report.schema_valid,
            report.citation_coverage, report.unsupported_claim_rate,
            len(report.citation_invalid), llm_calls,
            t.get("input_tokens"), t.get("output_tokens"), t.get("gen_tok_per_s"),
        )
        return draft

    def _model_sequence(self) -> list[str]:
        seq = [self.cfg.model]
        fb = (self.cfg.fallback_model or "").strip()
        if fb and fb != self.cfg.model:
            seq.append(fb)
        return seq

    def _call_with_schema_retry(
        self,
        messages: list[dict],
        model: str,
        metrics_list: list,
    ) -> tuple[str | None, int]:
        """返回能通过部分校验的原始文本（及调用次数）；重试用尽返回 (None, n)。"""
        calls = 0
        for attempt in range(self.cfg.max_invalid_retries + 1):
            text, m = self._invoke_provider(messages, model)
            calls += 1
            metrics_list.append(m)
            payload = _parse_json(text)
            if payload is None:
                if attempt < self.cfg.max_invalid_retries:
                    continue
                return None, calls
            try:
                extract_partial(payload)  # schema 前瞻校验
                return text, calls
            except Exception:
                if attempt < self.cfg.max_invalid_retries:
                    continue
                return None, calls
        return None, calls

    def _invoke_provider(
        self, messages: list[dict], model: str
    ) -> tuple[str, object | None]:
        """一次 provider 调用；有计量能力的返回 (text, ProviderMetrics)，否则 (text, None)。"""
        caller = getattr(self.provider, "chat_with_metrics", None)
        if caller is not None:
            return caller(messages, model=model)
        return self.provider.chat(messages, model=model), None

    def _build_draft(
        self,
        req: SynthesisRequest,
        resolved: list,
        model: str,
        raw: str,
        rid: str,
    ) -> SynthesisDraft:
        payload = _parse_json(raw)
        if payload is None:
            raise SynthesisInvalidError("模型输出不是有效 JSON", detail={"request_id": rid})
        partial = extract_partial(payload)
        # 兼容：模型若写成 E1..En 标签，则归一化为对应 chunk_id（E 标签 1:1 对应
        # Context Envelope 中显式提供的证据，仍属 grounded；见 prompt 的严格提示）。
        label_map = {r.ref_id: r.chunk_id for r in resolved}
        for claim in partial.get("claims", []) or []:
            claim["evidence_refs"] = [
                label_map.get(r, r) for r in (claim.get("evidence_refs") or [])
            ]
        for tension in partial.get("tensions", []) or []:
            tension["evidence_refs"] = [
                label_map.get(r, r) for r in (tension.get("evidence_refs") or [])
            ]
        base = {
            "id": rid,
            "task_type": req.task_type,
            "query": req.query,
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "generator": self._generator(model),
            "evidence": [r.evidence_ref for r in resolved],
            "status": "draft",
            "claims": partial.get("claims", []),
            "tensions": partial.get("tensions", []),
            "uncertainties": partial.get("uncertainties", []),
            "open_questions": partial.get("open_questions", []),
            "summary": partial.get("summary", ""),
        }
        try:
            return SynthesisDraft.model_validate(base)
        except Exception as exc:
            raise SynthesisInvalidError(
                f"Draft schema 校验失败: {exc}", detail={"request_id": rid}
            ) from exc


def _parse_json(text: str) -> dict | None:
    """尽力解析模型输出 JSON（容忍 Markdown 代码块包裹）。"""
    if not text:
        return None
    stripped = text.strip()
    m = _FENCE_RE.match(stripped)
    if m:
        stripped = m.group(1).strip()
    try:
        data = json.loads(stripped)
    except json.JSONDecodeError:
        # 尝试截取第一个 { 到最后一个 }
        s, e = stripped.find("{"), stripped.rfind("}")
        if s != -1 and e > s:
            try:
                data = json.loads(stripped[s : e + 1])
            except json.JSONDecodeError:
                return None
        else:
            return None
    return data if isinstance(data, dict) else None


def _short_id(query: str) -> str:
    h = hashlib.sha1(query.strip().encode("utf-8")).hexdigest()[:10]
    return f"synthesis_{h}"