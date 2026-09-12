# -*- coding: utf-8 -*-
"""P8-CORPUS-01 · B 阶段：确定性 shadow 子集抽样（60–120 篇）。

构成：
  1. forced: Dev20 human-gold 目标文档 ∩ 外资研报（修复臂对象）
  2. forced: Legacy 9 目标文档（其他 tier，原样保留，作 canary 载体）
  3. stratified: 外资研报按 author family × size 四分位 × source_type 分层，
     random.Random(seed) 确定性抽取至外资研报总数 ~80
输出 subset_manifest.json（含规则、seed、来源 sha256、基线身份）。
"""
from __future__ import annotations
import json, sqlite3, random, hashlib
from collections import defaultdict

SEED = 'p8-corpus01-shadow-20260912'
DB = r'D:/AI-Knowledge-Engine/data/catalog_full.db'
AUDIT = r'D:/AIKE-local-a-corpus01/shadow/audit/foreign_research_audit.json'
OUT = r'D:/AIKE-local-a-corpus01/shadow/audit/subset_manifest.json'
N_FR_TOTAL = 80
N_LEGACY_DOCS = 9

def sha(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for c in iter(lambda: f.read(1 << 20), b''):
            h.update(c)
    return h.hexdigest()

def main():
    audit = json.load(open(AUDIT, encoding='utf-8'))
    con = sqlite3.connect(f'file:{DB}?mode=ro', uri=True)
    cur = con.cursor()
    # 1) Dev targets in 外资研报
    dev = [json.loads(l) for l in open(r'D:/AI-Knowledge-Engine/docs/p8_review/benchmark/adjudication/development_calibration_v2/gold_development_v2_human.jsonl', encoding='utf-8')]
    dev_docs = set()
    for g in dev:
        for c in g.get('gold', {}).get('chunks', []):
            cid = c['chunk_id'] if isinstance(c, dict) else str(c)
            dev_docs.add(cid.split(':')[0])
    fr_ids = {r['document_id'] for r in audit}
    forced_dev = sorted(dev_docs & fr_ids)
    # 2) Legacy targets (other tiers)
    legacy = [json.loads(l) for l in open(r'D:/AI-Knowledge-Engine/docs/p8_review/benchmark/legacy_v1/golden_queries.jsonl', encoding='utf-8')]
    legacy_docs = sorted({s['document_id'] for q in legacy for s in q.get('relevant_sections', [])})
    legacy_rows = {}
    for did in legacy_docs:
        r = cur.execute("SELECT id, domain, source_path, sha256 FROM documents WHERE id=?", (did,)).fetchone()
        if r: legacy_rows[did] = r
    # 3) stratified FR sample to fill N_FR_TOTAL - len(forced_dev)
    quota = N_FR_TOTAL - len(forced_dev)
    by_family = defaultdict(list)
    for r in audit:
        if r['document_id'] in forced_dev:
            continue
        fam = r['author'] or 'unknown'
        q = 0 if r['file_size'] < 110669 else (1 if r['file_size'] < 346877 else 2)  # p50 / p95 split
        by_family[(fam, q)].append(r)
    rng = random.Random(SEED)
    fam_keys = sorted(by_family)
    # round-robin over strata for family coverage
    picked = []
    i = 0
    while len(picked) < quota:
        progressed = False
        for k in fam_keys:
            if i < len(by_family[k]):
                picked.append(by_family[k][i])
                progressed = True
                if len(picked) >= quota:
                    break
        if not progressed:
            break
        i += 1
    picked_ids = sorted(r['document_id'] for r in picked)
    # resolve rows
    all_audit = {r['document_id']: r for r in audit}
    subset = {
        'seed': SEED,
        'selection_rule': {
            'forced_dev_targets_in_fr': 'all Dev20 human-gold target docs ∩ 外资研报 (repair arm)',
            'forced_legacy_targets': 'all Legacy 50 target docs (baseline carrier, unrepaired)',
            'stratified_fr': f'round-robin over sorted (author family × file_size quartile[p50=110669,p95=346877]) strata, random.Random(seed) unused order (deterministic round-robin), fill FR total to {N_FR_TOTAL}',
        },
        'counts': {
            'fr_repair_total': len(forced_dev) + len(picked_ids),
            'forced_dev': len(forced_dev),
            'stratified_fr': len(picked_ids),
            'legacy_carrier': len(legacy_rows),
            'subset_total_docs': len(forced_dev) + len(picked_ids) + len(legacy_rows),
        },
        'fr_repair_doc_ids': sorted(set(forced_dev + picked_ids)),
        'forced_dev_doc_ids': forced_dev,
        'stratified_doc_ids': picked_ids,
        'legacy_carrier_doc_ids': sorted(legacy_rows),
        'fr_sha256': {r['document_id']: r['sha256'] for r in audit if r['document_id'] in set(forced_dev + picked_ids)},
        'legacy_sha256': {d: r[3] for d, r in legacy_rows.items()},
        'baseline_identity': {
            'production_catalog': 'D:/AI-Knowledge-Engine/data/catalog_full.db',
            'production_chunks_collection': 'kb_chunks_full_v1',
            'parser_version': '0.1.0', 'chunker_version': '0.3.0',
        },
    }
    with open(OUT, 'w', encoding='utf-8', newline='\n') as f:
        json.dump(subset, f, ensure_ascii=False, indent=2)
    print(json.dumps(subset['counts'], ensure_ascii=False, indent=1))
    print('manifest sha256:', sha(OUT)[:16])

if __name__ == '__main__':
    main()
