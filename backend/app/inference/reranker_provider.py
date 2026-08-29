"""Qwen3-Reranker-0.6B Provider（M0）。

- 基于 transformers 原生实现（官方 model card 用法）；
- 取 last position 上 "yes"/"no" token 的 softmax 概率作为相关性分数；
- GPU batch 从 1 起步，smoke test 后再逐步放开（写入 runtime_profile）。
"""

from __future__ import annotations

import logging

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "Judge whether the Document meets the requirements based on the Query and "
    'the Instruct provided. Note that the answer can only be "yes" or "no".'
)
PREFIX = f"<|im_start|>system\n{SYSTEM_PROMPT}<|im_end|>\n<|im_start|>user\n"
SUFFIX = "<|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>\n\n"


class TorchRerankerProvider:
    """统一的 Reranker 推理入口（rocm/cpu 共用）。"""

    def __init__(
        self,
        model_path: str,
        device: str = "cpu",
        dtype_gpu: str = "float16",
        max_length: int = 3072,
    ) -> None:
        self.model_path = model_path
        self.device = device
        self.max_length = max_length

        dtype_str = dtype_gpu if device != "cpu" else "float32"
        torch_dtype = {"float16": torch.float16, "bfloat16": torch.bfloat16, "float32": torch.float32}[dtype_str]

        self.tokenizer = AutoTokenizer.from_pretrained(model_path, padding_side="left")
        self.model = AutoModelForCausalLM.from_pretrained(model_path, torch_dtype=torch_dtype)
        self.model.to(device)
        self.model.eval()

        self.token_true_id = self.tokenizer.convert_tokens_to_ids("yes")
        self.token_false_id = self.tokenizer.convert_tokens_to_ids("no")

    def format_pair(self, query: str, document: str, instruction: str = "") -> str:
        instruct = f"<|instruct|>\n{instruction}\n" if instruction else ""
        return (
            f"{PREFIX}{instruct}<|Query|>\n{query}\n"
            f"<|Document|>\n{document}{SUFFIX}"
        )

    def score(self, query: str, documents: list[str], batch_size: int = 1, instruction: str = "") -> list[float]:
        texts = [self.format_pair(query, doc, instruction) for doc in documents]
        scores: list[float] = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            inputs = self.tokenizer(
                batch, padding=True, truncation=True, max_length=self.max_length, return_tensors="pt"
            ).to(self.device)
            with torch.no_grad():
                logits = self.model(**inputs).logits[:, -1, :]
                yes_no = torch.stack([logits[:, self.token_false_id], logits[:, self.token_true_id]], dim=-1)
                probs = torch.softmax(yes_no.float(), dim=-1)[:, 1]
            scores.extend(probs.cpu().tolist())
        return scores

    def health(self) -> dict:
        return {"device": self.device, "model_path": self.model_path, "dtype": str(next(self.model.parameters()).dtype)}
