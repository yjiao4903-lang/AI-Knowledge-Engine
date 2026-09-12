# -*- coding: utf-8 -*-
"""P8-CORPUS-01 · F 阶段准备：把 Dev human gold 转成 content_anchors 文本锚定金标。

每个 grade>=2 的 gold chunk：从生产 catalog 取 plain_text，取特征子串作 anchor_contains，
document_id 按目标索引（baseline/shadow）的 documents 表（report_code+title 匹配）重映射。
输出 questions 文件（两份，一份 per 索引），query 文本与 grade 原样保留。
仅 in-subset 的题保留；排除清单与原因写入 report。
"""
from __future__ import annotations
import json, sqlite3, re

PROD = r'D:/AI-Knowledge-Engine/data/catalog_full.db'
GOLD = r'D:/AI-Knowledge-Engine/docs/p8_review/benchmark/adjudication/development_calibration_v2/gold_development_v2_human.jsonl'
BASE_DB = r'D:/AIKE-local-a-corpus01/shadow/catalog_a43_base.db'
SHA_DB = r'D:/AIKE-local-a-corpus01/shadow/catalog_a43_sha.db'
OUT_DIR = r'D:/AIKE-local-a-corpus01/shadow'

def conn_ro(p):
    c = sqlite3.connect(f'file:{p}?mode=ro', uri=True)
    c.row_factory = sqlite3.Row
    return c

def distinctive(plain: str) -> str | None:
    # 保留原始空白（LIKE 按原文字节匹配）；取中段 120 字符避开开头 boilerplate
    t = plain.strip()
    if len(t) < 60:
        return t or None
    start = max(0, (len(t) - 120) // 2)
    return t[start:start + 120]

def main():
    prod = conn_ro(PROD)
    questions = [json.loads(l) for l in open(GOLD, encoding='utf-8')]
    # 目标索引 doc 映射：(report_code, title) -> document_id
    def doc_map(db):
        c = conn_ro(db)
        return {(r['report_code'], r['title']): r['id'] for r in c.execute('SELECT id, report_code, title FROM documents')}
    maps = {'base': doc_map(BASE_DB), 'sha': doc_map(SHA_DB)}

    out = {k: [] for k in maps}
    excluded = []
    for q in questions:
        gold = q.get('gold', {})
        anchors = []
        missing_docs = set()
        for it in gold.get('chunks', []):
            if it.get('grade', 0) < 2:
                continue
            row = prod.execute('SELECT document_id, plain_text FROM chunks WHERE id=?', (it['chunk_id'],)).fetchone()
            if not row:
                missing_docs.add(('chunk_missing', it['chunk_id']))
                continue
            a = distinctive(row['plain_text'])
            if not a or len(a) < 20:
                missing_docs.add(('anchor_weak', it['chunk_id']))
                continue
            prow = prod.execute('SELECT report_code, title FROM documents WHERE id=?', (row['document_id'],)).fetchone()
            key = (prow['report_code'], prow['title'])
            placed = False
            for k, m in maps.items():
                did = m.get(key)
                if did:
                    anchors.append({'document_id': did, 'anchor_contains': a, 'grade': it['grade']})
                    placed = True
            if not placed:
                missing_docs.add(('doc_not_in_subset', row['document_id']))
        if not anchors:
            excluded.append({'qid': q['id'], 'reason': sorted({m[0] for m in missing_docs})})
            continue
        out['base'].append({'id': q['id'], 'query': q['query'], 'type': q.get('query_type'), 'split': 'development', 'gold': {'content_anchors': anchors}})
        out['sha'].append({'id': q['id'], 'query': q['query'], 'type': q.get('query_type'), 'split': 'development', 'gold': {'content_anchors': anchors}})
        if missing_docs:
            out.setdefault('partial', []).append({'qid': q['id'], 'notes': sorted({m[0] for m in missing_docs})})
    for k in ('base', 'sha'):
        p = rf'{OUT_DIR}/dev_anchor_gold_{k}.jsonl'
        with open(p, 'w', encoding='utf-8', newline='\n') as f:
            for r in out[k]:
                f.write(json.dumps(r, ensure_ascii=False) + '\n')
        print(k, 'questions:', len(out[k]))
    with open(rf'{OUT_DIR}/dev_anchor_gold_excluded.json', 'w', encoding='utf-8', newline='\n') as f:
        json.dump({'excluded': excluded, 'partial': out.get('partial', [])}, f, ensure_ascii=False, indent=2)
    print('excluded:', len(excluded), 'partial:', len(out.get('partial', [])))

if __name__ == '__main__':
    main()
