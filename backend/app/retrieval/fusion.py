"""Weighted RRF 融合（M4 lexical combined 初版，M6 复用，spec §18）。"""

from __future__ import annotations

from collections import defaultdict


def weighted_rrf(
    ranked_lists: dict[str, list[str]],
    *,
    rrf_k: int = 60,
    weights: dict[str, float] | None = None,
) -> list[tuple[str, float, dict[str, int | None]]]:
    """多路排名融合。

    ranked_lists: {source_name: [item_id 按 rank 排序]}
    weights: {source_name: weight}，缺省 1.0
    返回 [(item_id, rrf_score, {source: rank_or_None})]，按分数降序。

    score(d) = sum_i w_i / (rrf_k + rank_i(d))
    """
    weights = weights or {}
    scores: dict[str, float] = defaultdict(float)
    ranks: dict[str, dict[str, int | None]] = defaultdict(dict)
    for source, ids in ranked_lists.items():
        w = weights.get(source, 1.0)
        for pos, item_id in enumerate(ids, start=1):
            scores[item_id] += w / (rrf_k + pos)
            ranks[item_id][source] = pos
    for item_id in set().union(*[set(ids) for ids in ranked_lists.values()]) if ranked_lists else []:
        for source in ranked_lists:
            ranks[item_id].setdefault(source, None)

    ordered = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    return [(item_id, score, ranks[item_id]) for item_id, score in ordered]
