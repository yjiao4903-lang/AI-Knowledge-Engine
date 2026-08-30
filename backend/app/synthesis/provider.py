"""Synthesis Provider 抽象（主计划 §12/§13/§40）。

- `SynthesisProvider` 接口：`chat(...)` 返回模型文本；`is_available()` 探活。
- L1A 真实实现：`OllamaProvider`（OpenAI 兼容 `/v1/chat/completions`）。
- `MockProvider`：确定性、可复现，仅用于单测与离线 Golden Harness（provider=mock），
  不接入任何真实模型（主计划 §13 的 provider 抽象允许）。它从 user 消息中解析
  已显式提供的 chunk_id 并生成合法 Draft，从而在无真实模型时也能验证
  grounding/validator/api 全链路与 L1A 自动指标。
- 传输/HTTP/超时异常统一转换为 `SynthesisUnavailableError`（§38：不创建 Draft）。
"""

from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass

import httpx

from app.core.config import SynthesisConfig
from app.core.errors import SynthesisUnavailableError

_NS = 1_000_000.0  # ns -> ms


@dataclass
class ProviderMetrics:
    """单次 LLM 调用的相位级计量（来自 ollama 原生 /api/chat 的 duration/count 字段）。

    - load_ms       ：模型加载（warm 常驻时 ~0，冷启动/被换出时显著 >0）
    - prefill_ms    ：prompt 预填充（非流式下 ≈ TTFT 代理）
    - generation_ms ：生成阶段
    - input/output_tokens：prompt_eval_count / eval_count
    - *_tok_per_s   ：预填充 / 生成吞吐
    """

    model: str | None = None
    load_ms: float = 0.0
    prefill_ms: float = 0.0
    generation_ms: float = 0.0
    total_ms: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    prefill_tok_per_s: float | None = None
    gen_tok_per_s: float | None = None

    def update_from_ollama(self, data: dict) -> None:
        d = data or {}
        self.load_ms = (d.get("load_duration") or 0) / _NS
        self.prefill_ms = (d.get("prompt_eval_duration") or 0) / _NS
        self.generation_ms = (d.get("eval_duration") or 0) / _NS
        self.total_ms = (d.get("total_duration") or 0) / _NS
        self.input_tokens = d.get("prompt_eval_count") or 0
        self.output_tokens = d.get("eval_count") or 0
        if self.input_tokens and self.prefill_ms:
            self.prefill_tok_per_s = self.input_tokens / (self.prefill_ms / 1000)
        if self.output_tokens and self.generation_ms:
            self.gen_tok_per_s = self.output_tokens / (self.generation_ms / 1000)

# 匹配 Envelope 证据行 `[E1] EVIDENCE id=<chunk_id>（…）` 里的 chunk_id。
# 限定 "EVIDENCE id=" 前缀，避免误抓 prompt 里 "`id=`" 之类字样。
# chunk_id 可含中文（如 GPU产业技术源流_最终报告:ch3-1:0014），捕获到 `（` 或空白为止。
_CHUNK_ID_RE = re.compile(r"EVIDENCE id=([^\s（(]+)")


class SynthesisProvider(ABC):
    provider_name = "abstract"

    def __init__(self, cfg: SynthesisConfig) -> None:
        self.cfg = cfg

    @abstractmethod
    def chat(
        self,
        messages: list[dict],
        *,
        model: str | None = None,
    ) -> str:
        """调用模型，返回生成文本。transport/超时/HTTP 非 2xx 抛 SynthesisUnavailableError。"""

    def is_available(self) -> bool:
        return True


class OllamaProvider(SynthesisProvider):
    """OpenAI 兼容 HTTP 接口，走 http://127.0.0.1:11434/v1。"""

    provider_name = "ollama"

    def __init__(self, cfg: SynthesisConfig) -> None:
        super().__init__(cfg)
        self.base_url = cfg.base_url.rstrip("/")

    def chat(
        self,
        messages: list[dict],
        *,
        model: str | None = None,
    ) -> str:
        """调用模型，返回生成文本（等价于 chat_with_metrics 的 .text）。"""
        text, _ = self.chat_with_metrics(messages, model=model)
        return text

    def _native_api_url(self) -> str:
        """由 OpenAI 兼容 base_url 推导 ollama 原生端点：…/v1 -> …/api/chat。"""
        base = self.base_url
        if base.endswith("/v1"):
            base = base[:-3]
        return base.rstrip("/") + "/api/chat"

    def chat_with_metrics(
        self,
        messages: list[dict],
        *,
        model: str | None = None,
    ) -> tuple[str, ProviderMetrics]:
        """走 ollama 原生 /api/chat，返回 (文本, 相位计量)。

        native 响应额外携带 load_duration / prompt_eval_count(_duration) /
        eval_count(_duration)，OpenAI 兼容端点不返回这些字段，故计量需走原生接口。
        transport/超时/HTTP 非 2xx 抛 SynthesisUnavailableError。
        """
        cfg = self.cfg
        payload = {
            "model": model or cfg.model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": cfg.temperature,
                "num_predict": cfg.max_tokens,
            },
        }
        try:
            with httpx.Client(timeout=cfg.timeout_seconds) as client:
                resp = client.post(self._native_api_url(), json=payload)
        except httpx.HTTPError as exc:
            raise SynthesisUnavailableError(f"LLM provider 请求失败: {exc!r}") from exc
        if resp.status_code != 200:
            raise SynthesisUnavailableError(
                f"LLM provider 返回 {resp.status_code}: {resp.text[:200]}"
            )
        data = resp.json()
        try:
            content = data["message"]["content"]
        except (KeyError, TypeError) as exc:
            raise SynthesisUnavailableError(
                f"LLM provider 响应结构异常: {exc!r}"
            ) from exc
        metrics = ProviderMetrics(model=model or cfg.model)
        metrics.update_from_ollama(data)
        return content, metrics

    def is_available(self) -> bool:
        try:
            with httpx.Client(timeout=3.0) as client:
                resp = client.get(f"{self.base_url}/models")
            return resp.status_code == 200
        except httpx.HTTPError:
            return False


class MockProvider(SynthesisProvider):
    """确定性 Provider：从 user 消息解析提供证据，生成可验证通过的合法 Draft。

    仅供单测 / 离线 Golden Harness（provider=mock），不产出真实内容。
    """

    provider_name = "mock"

    def chat(
        self,
        messages: list[dict],
        *,
        model: str | None = None,
    ) -> str:
        provided: list[str] = []
        for msg in messages:
            for m in _CHUNK_ID_RE.findall(msg.get("content", "")):
                if m not in provided:
                    provided.append(m)
        if not provided:
            provided = ["M04:ch3-2:o1:0040"]
        draft = {
            "claims": [
                {
                    "id": "claim_001",
                    "text": "（确定性 Mock 摘要）综合上述证据的核心理念。",
                    "epistemic_state": "supported",
                    "evidence_refs": provided[: min(2, len(provided))],
                    "rationale": "Mock provider 生成，用于链路验证。",
                }
            ],
            "tensions": [],
            "uncertainties": [],
            "open_questions": [],
            "summary": "（确定性 Mock 输出）来自 provider=mock 的合成草稿。",
        }
        return json.dumps(draft, ensure_ascii=False)


def get_provider(cfg: SynthesisConfig) -> SynthesisProvider:
    """按 cfg.provider 返回对应 Provider 实例。"""
    by_name = {
        "ollama": OllamaProvider,
        "mock": MockProvider,
    }
    cls = by_name.get(cfg.provider)
    if cls is None:
        raise SynthesisUnavailableError(f"未知 synthesis provider: {cfg.provider}")
    return cls(cfg)