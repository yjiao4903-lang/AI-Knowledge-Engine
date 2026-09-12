# -*- coding: utf-8 -*-
"""P8-CORPUS-01 · A 阶段：外资研报 tier 全量诊断表（只读）。

对生产 catalog（只读）+ 源 markdown front matter 逐文档统计：
id/hash/来源/OCR/大小/section/chunk/元信息占比/有效标题/标题深度/元数据完整度/重复碰撞/家族/时间。
输出 JSON+CSV，供 shadow 抽样与 before/after 对比。
"""
from __future__ import annotations
import json, re, sqlite3, sys, hashlib
from collections import Counter, defaultdict

DB = r'D:/AI-Knowledge-Engine/data/catalog_full.db'
OUT = r'D:/AIKE-local-a-corpus01/shadow/audit'
PLACEHOLDER = re.compile(r'^(元信息|配图\d*|图表（p\d+ OCR）|图表\d*|（未 OCR）|目录|封面|附录|参考资料)$')

def front_matter(path):
    try:
        with open(path, encoding='utf-8') as f:
            text = f.read(4000)
    except OSError:
        return {}
    m = re.match(r'^---\r?\n(.*?)\r?\n---', text, re.S)
    if not m:
        return {}
    fm = {}
    for line in m.group(1).splitlines():
        if ':' in line:
            k, _, v = line.partition(':')
            fm[k.strip()] = v.strip().strip('"')
    return fm

def main():
    con = sqlite3.connect(f'file:{DB}?mode=ro', uri=True)
    cur = con.cursor()
    docs = cur.execute("""
        SELECT d.id, d.report_code, d.title, d.author, d.completed_at, d.source_path,
               d.file_size, d.sha256, d.parser_version, d.chunker_version
        FROM documents d WHERE d.domain='外资研报'""").fetchall()
    sec_counts = dict(cur.execute(
        "SELECT document_id, COUNT(*) FROM sections WHERE document_id LIKE ? GROUP BY document_id",
        ('%',)).fetchall()) if False else {}
    # batch section stats
    sec_rows = cur.execute("""
        SELECT document_id, COUNT(*), MAX(level),
               SUM(CASE WHEN heading IN ('元信息','目录') OR heading LIKE '配图%' OR heading LIKE '图表%' THEN 1 ELSE 0 END)
        FROM sections WHERE document_id IN (SELECT id FROM documents WHERE domain='外资研报')
        GROUP BY document_id""").fetchall()
    sec = {r[0]: (r[1], r[2], r[3]) for r in sec_rows}
    chunk_rows = cur.execute("""
        SELECT document_id, COUNT(*),
               SUM(CASE WHEN heading_path LIKE '%元信息%' THEN 1 ELSE 0 END),
               SUM(CASE WHEN heading_path LIKE '%配图%' OR heading_path LIKE '%图表（%' THEN 1 ELSE 0 END)
        FROM chunks WHERE document_id IN (SELECT id FROM documents WHERE domain='外资研报')
        GROUP BY document_id""").fetchall()
    chk = {r[0]: (r[1], r[2], r[3]) for r in chunk_rows}
    heading_rows = cur.execute("""
        SELECT document_id, heading FROM sections
        WHERE document_id IN (SELECT id FROM documents WHERE domain='外资研报')""").fetchall()
    headings = defaultdict(list)
    for did, h in heading_rows:
        headings[did].append(h)

    rc_base = Counter()
    for did, rc, *_ in docs:
        rc_base[str(rc).split('__')[0]] += 1

    records = []
    for did, rc, title, author, completed, spath, fsize, sha, pv, cv in docs:
        fm = front_matter(spath)
        n_sec, max_lvl, n_placeholder = sec.get(did, (0, 0, 0))
        n_chk, n_meta, n_chart = chk.get(did, (0, 0, 0))
        hs = headings.get(did, [])
        n_meaningful = sum(1 for h in hs if not PLACEHOLDER.match(h or ''))
        src_type = fm.get('source_type', '')
        ocr = 'ocr' in src_type.lower() or fm.get('ocr', '') not in ('', None)
        base_rc = str(rc).split('__')[0]
        rec = {
            'document_id': did,
            'report_code': rc,
            'report_code_base': base_rc,
            'title': (title or '')[:120],
            'source_path': spath,
            'sha256': sha,
            'file_size': fsize,
            'parser_version': pv,
            'chunker_version': cv,
            'source_type': src_type,
            'ocr_flag': bool(ocr),
            'author': fm.get('author', ''),
            'source_topic_id': fm.get('source_topic_id', ''),
            'quality_tier': fm.get('quality_tier', ''),
            'evidence': fm.get('evidence', ''),
            'completed_at': completed,
            'sections': n_sec,
            'max_heading_level': max_lvl,
            'placeholder_sections': n_placeholder,
            'meaningful_headings': n_meaningful,
            'chunks': n_chk,
            'meta_chunks': n_meta,
            'meta_chunk_ratio': round(n_meta / n_chk, 4) if n_chk else None,
            'chart_chunks': n_chart,
            'meta_keys_present': sum(1 for k in ('title','report_code','domain','author','completed_at','source_type','source_topic_id','evidence','quality_tier') if fm.get(k)),
            'report_code_collision': rc_base[base_rc] > 1,
            'title_sample': (title or '')[:40],
        }
        records.append(rec)
    with open(f'{OUT}/foreign_research_audit.json', 'w', encoding='utf-8', newline='\n') as f:
        json.dump(records, f, ensure_ascii=False)
    # summary
    tot = len(records)
    agg = {
        'docs': tot,
        'chunks': sum(r['chunks'] for r in records),
        'meta_chunks': sum(r['meta_chunks'] for r in records),
        'docs_with_meaningful_headings': sum(1 for r in records if r['meaningful_headings'] > 0),
        'meaningful_headings_total': sum(r['meaningful_headings'] for r in records),
        'meta_ratio_gt_99': sum(1 for r in records if (r['meta_chunk_ratio'] or 0) > 0.99),
        'ocr_docs': sum(1 for r in records if r['ocr_flag']),
        'source_types': Counter(r['source_type'] for r in records).most_common(),
        'authors_top': Counter(r['author'] for r in records).most_common(15),
        'collision_docs': sum(1 for r in records if r['report_code_collision']),
        'completed_range': [min(r['completed_at'] or '' for r in records), max(r['completed_at'] or '' for r in records)],
        'chunks_p50_p95': None,
    }
    cs = sorted(r['chunks'] for r in records)
    agg['chunks_p50_p95'] = [cs[len(cs)//2], cs[int(len(cs)*0.95)]]
    sizes = sorted(r['file_size'] for r in records)
    agg['size_p50_p95'] = [sizes[len(sizes)//2], sizes[int(len(sizes)*0.95)]]
    with open(f'{OUT}/foreign_research_audit_summary.json', 'w', encoding='utf-8', newline='\n') as f:
        json.dump(agg, f, ensure_ascii=False, indent=2)
    # csv
    import csv
    keys = list(records[0].keys())
    with open(f'{OUT}/foreign_research_audit.csv', 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows(records)
    print(json.dumps(agg, ensure_ascii=False, indent=2, default=str))

if __name__ == '__main__':
    main()
