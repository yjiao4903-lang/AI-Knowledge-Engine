"""Qwen3-Embedding-0.6B Provider（M0）。

- 基于 transformers 原生实现（官方 model card 用法），last-token pooling；
- 查询侧必须携带任务指令（instruction-aware），文档侧不加；
- 输出 L2 normalized 向量，维度 1024。
"""

from __future__ import annotations

import logging

import torch
from transformers import AutoModel, AutoTokenizer

logger = logging.getLogger(__name__)

DEFAULT_QUERY_INSTRUCTION = (
    "Given a query for a private research knowledge base, retrieve the most "
    "relevant passages from Chinese and English technical, semiconductor, AI, "
    "macroeconomic, industry, and investment research reports. Preserve exact "
    "entities, model names, technical terms, causal relationships, "
    "quantitative indicators, and evidence levels."
)

DTYPE_MAP = {"float16": torch.float16, "bfloat16": torch.bfloat16, "float32": torch.float32}


def _last_token_pool(last_hidden_states: torch.Tensor, attention_mask: torch.Tensor) -> torch.Tensor:
    # left padding: 序列末尾即最后一个真实 token
    last_hidden = last_hidden_states.masked_fill(~attention_mask[..., None].bool(), 0.0)
    return last_hidden[:, -1]


class TorchEmbeddingProvider:
    """统一的 Embedding 推理入口（rocm/cpu 共用，dtype 与 batch 由配置决定）。"""

    def __init__(
        self,
        model_path: str,
        device: str = "cpu",
        dtype_gpu: str = "float16",
        max_length: int = 4096,
        query_instruction: str = DEFAULT_QUERY_INSTRUCTION,
    ) -> None:
        self.model_path = model_path
        self.device = device
        self.query_instruction = query_instruction
        self.max_length = max_length

        dtype_str = dtype_gpu if device != "cpu" else "float32"
        torch_dtype = DTYPE_MAP[dtype_str]

        self.tokenizer = AutoTokenizer.from_pretrained(model_path, padding_side="left")
        self.model = AutoModel.from_pretrained(model_path, torch_dtype=torch_dtype)
        self.model.to(device)
        self.model.eval()

    def _encode(self, texts: list[str], batch_size: int) -> list[list[float]]:
        out: list[list[float]] = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            inputs = self.tokenizer(
                batch, padding=True, truncation=True, max_length=self.max_length, return_tensors="pt"
            ).to(self.device)
            with torch.no_grad():
                hidden = self.model(**inputs).last_hidden_state
                emb = _last_token_pool(hidden, inputs["attention_mask"])
                emb = torch.nn.functional.normalize(emb, p=2, dim=1)
            out.extend(emb.cpu().float().tolist())
        return out

    def embed_documents(self, texts: list[str], batch_size: int = 8) -> list[list[float]]:
        # 文档侧不加 query instruction
        return self._encode(texts, batch_size)

    def embed_query(self, query: str, batch_size: int = 1) -> list[float]:
        text = f"Instruct: {self.query_instruction}\nQuery: {query}"
        return self._encode([text], batch_size)[0]

    def health(self) -> dict:
        return {"device": self.device, "model_path": self.model_path, "dtype": str(next(self.model.parameters()).dtype)}
