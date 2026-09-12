# -*- coding: utf-8 -*-
"""P8-CORPUS-01 · F/G：文本级（粒度归一化）配对评测。

复用 p8_trace_shadow 的检索原语与臂构造（逐字节同逻辑），
但相关性判定改为【文本包含】：retrieved chunk 的 plain_text 包含任一 gold
anchor 子串即相关 —— 消除 baseline/shadow chunk 粒度差异的混杂。
输出 Hit@1/3/5、MRR、NDCG@10（二值）、top-10 FR 占比（竞争分解）。
"""
from __future__ import annotations
import json, sys, time, math, pathlib

sys.path.insert(0, r'D:/AI-Knowledge-Engine/backend')
import p8_trace_shadow as T
from app.core.config import load_config
from app.inference.manager import InferenceManager
from app.lexical.fts_search import LexicalSearcher
from app.retrieval.dense import DenseRetriever
from app.retrieval.rerank import RerankerService

def dcg(scores):
    return sum(s / math.log2(i + 2) for i, s in enumerate(scores))

def metrics_for(ranked_chunks, anchors, fr_prefixes):
    """ranked_chunks: [(chunk_id, plain_text, is_fr)]；anchors: [substr]."""
    rel = []
    for cid, text, is_fr in ranked_chunks:
        hit = any(a in text for a in anchors)
        rel.append((hit, is_fr))
    out = {}
    for k in (1, 3, 5, 10):
        out[f'hit{k}'] = 1.0 if any(h for h, _ in rel[:k]) else 0.0
    mrr = 0.0
    for i, (h, _) in enumerate(rel):
        if h:
            mrr = 1.0 / (i + 1)
            break
    out['mrr'] = mrr
    out['ndcg'] = dcg([1.0 if h else 0.0 for h, _ in rel[:10]]) / dcg([1.0] * min(len(anchors), 10))
    top10 = rel[:10]
    out['fr_share_top10'] = (sum(1 for _, f in top10 if f) / len(top10)) if top10 else 0.0
    first_fr = next((i + 1 for i, (_, f) in enumerate(rel) if f), None)
    out['first_fr_rank'] = first_fr
    return out

def run(cfg_path, questions_path, exp):
    cfg = load_config(cfg_path)
    T.CATALOG = pathlib.Path(cfg.sqlite.path)
    conn = T.ro_conn()
    section_of = {r['id']: r['section_id'] for r in conn.execute('SELECT id, section_id FROM chunks')}
    fr_docs = {r[0] for r in conn.execute("SELECT id FROM documents WHERE domain='外资研报'")}
    questions = T.load_questions(pathlib.Path(questions_path), 'development')
    # anchors per query: content_anchors or legacy heading_contains -> 用 production gold 文本？
    # legacy: heading_contains 语义为 section 标题包含 —— 文本级代理：直接沿用 chunk 文本包含锚点。
    # 此处 legacy 用 relevant_sections 的 heading_contains 作为【heading 文本】锚：
    # 匹配 retrieved chunk 的 heading_path 字符串。
    anchor_mode = 'text'
    dense = DenseRetriever(cfg)
    mgr = InferenceManager(cfg)
    reranker = RerankerService(cfg, mgr)
    lexical = LexicalSearcher(conn)

    per_arm = {a: [] for a in T.ARMS}
    rows_out = []
    for n, q in enumerate(questions, 1):
        if 'relevant_sections' in q:
            anchors = [it['heading_contains'] for it in q['relevant_sections'] if it.get('grade', 0) >= 2]
            mode = 'heading'
        else:
            anchors = [it['anchor_contains'] for it in q['gold']['content_anchors'] if it.get('grade', 0) >= 2]
            mode = 'text'
        t0 = time.perf_counter()
        dense_hits, _ = dense.search(q['query'], k=cfg.retrieval.dense_k, filters=None,
                                     collection=cfg.qdrant.chunks_collection)
        terms_hits = lexical.search_terms(q['query'], k=cfg.retrieval.fts_terms_k, filters=None)
        trigram_hits = lexical.search_trigram(q['query'], k=cfg.retrieval.fts_trigram_k, filters=None)
        lists = {
            'dense': [h['payload']['chunk_id'] for h in dense_hits],
            'terms': [h.chunk_id for h in terms_hits],
            'trigram': [h.chunk_id for h in trigram_hits],
        }
        boost_prefixes = None
        if cfg.fusion.parent_boost_enabled:
            sec_hits, _ = dense.search(q['query'], k=cfg.fusion.parent_boost_sections_k,
                                       collection=cfg.qdrant.sections_collection)
            boost_prefixes = {f"{h['payload']['document_id']}:{h['payload']['section_id']}:" for h in sec_hits}
        fused_all, _ = T.fuse(lists, cfg, boost_prefixes)
        fused_nb, _ = T.fuse(lists, cfg, None)
        fused_k = cfg.retrieval.fused_k
        fused_top = fused_all[:fused_k]
        rows = T.fetch_rows(conn, list(dict.fromkeys(lists['dense'] + lists['terms'] + lists['trigram'] + fused_top)))
        def text_of(cid):
            r = rows.get(cid)
            return (r['plain_text'] if r else '')
        final_order = list(fused_top)
        if fused_top:
            cands = [{'chunk_id': c, 'title': rows[c]['title'], 'heading_path': rows[c]['heading_path'],
                      'content_type': rows[c]['content_type'], 'evidence_level': rows[c]['evidence_level'],
                      'plain_text': rows[c]['plain_text']} for c in fused_top if c in rows]
            reranked = reranker.rerank(q['query'], cands)
            sb = {x['chunk_id']: x['reranker_score'] for x in reranked}
            final_order = sorted(fused_top, key=lambda c: sb.get(c, float('-inf')), reverse=True)
        def chunk_meta(cid):
            r = rows.get(cid)
            txt = r['plain_text'] if r else ''
            hp = r['heading_path'] if r else ''
            return cid, txt, hp
        def is_fr(cid):
            return any(cid.startswith(d + ':') for d in fr_docs)
        def ranked_with(arm):
            if arm == 'terms': ids = lists['terms'][:10]
            elif arm == 'trigram': ids = lists['trigram'][:10]
            elif arm == 'lexical': ids = T.fuse({'terms': lists['terms'], 'trigram': lists['trigram']}, cfg)[0][:10]
            elif arm == 'dense': ids = lists['dense'][:10]
            elif arm == 'hybrid': ids = fused_nb[:fused_k][:10]
            elif arm == 'hybrid_boost': ids = fused_top[:10]
            else: ids = final_order[:10]
            return [(cid, rows[cid]['plain_text'] if cid in rows else '', is_fr(cid)) for cid in ids]
        rec = {'id': q['id'], 'mode': mode}
        for arm in T.ARMS:
            rl = ranked_with(arm)
            if mode == 'heading':
                # legacy：锚匹配 heading_path 或正文
                rel = []
                for cid, txt, _hp in rl:
                    r = rows.get(cid)
                    hp = r['heading_path'] if r else ''
                    rel.append((any(a in hp or a in txt for a in anchors), is_fr(cid)))
                # recompute with heading anchors
                out = {}
                for kk in (1, 3, 5, 10):
                    out[f'hit{kk}'] = 1.0 if any(h for h, _ in rel[:kk]) else 0.0
                out['mrr'] = next((1.0 / (i + 1) for i, (h, _) in enumerate(rel) if h), 0.0)
                out['ndcg'] = dcg([1.0 if h else 0.0 for h, _ in rel[:10]]) / dcg([1.0] * min(len(anchors), 10))
                out['fr_share_top10'] = (sum(1 for _, f in rel[:10] if f) / max(1, len(rel[:10])))
                out['first_fr_rank'] = next((i + 1 for i, (_, f) in enumerate(rel) if f), None)
                m = out
            else:
                m = metrics_for(rl, anchors, fr_docs)
            per_arm[arm].append(m)
            rec[arm] = {k: m[k] for k in ('hit1', 'hit3', 'hit5', 'mrr', 'ndcg', 'fr_share_top10', 'first_fr_rank')}
        rows_out.append(rec)
        print(f"  [{n}/{len(questions)}] {q['id']} rerank hit5={rec['hybrid_rerank']['hit5']} mrr={rec['hybrid_rerank']['mrr']:.3f} frshare={rec['hybrid_rerank']['fr_share_top10']:.1f}")
    summary = {}
    for arm, ms in per_arm.items():
        if not ms: continue
        summary[arm] = {}
        for k in ms[0]:
            vals = [m[k] for m in ms if isinstance(m[k], (int, float))]
            if vals:
                summary[arm][k] = round(sum(vals) / len(vals), 4)
                if k == 'first_fr_rank':
                    summary[arm][f'{k}_n'] = len(vals)
    outdir = pathlib.Path(rf'D:/AIKE-local-a-corpus01/shadow/experiments/{exp}')
    outdir.mkdir(parents=True, exist_ok=True)
    json.dump({'exp': exp, 'n': len(questions), 'summary': summary, 'per_query': rows_out},
              open(outdir / 'textlevel.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print(json.dumps(summary, ensure_ascii=False, indent=1))

if __name__ == '__main__':
    run(sys.argv[1], sys.argv[2], sys.argv[3])
