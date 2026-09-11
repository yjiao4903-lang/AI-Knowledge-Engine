# -*- coding: utf-8 -*-
"""P8-BENCH-01 混合语料 Development / sealed Holdout 题集生成器（确定性）。

目标（Issue #36）：覆盖真实语料分层与真实题型的 150 + 150 题集；
Legacy 50 字节级冻结，仅作 canary。

设计
----
- **确定性**：固定 seed；排序/抽样基于 sha256(seed + 稳定键)，与文件系统顺序无关。
- **分层配额**：按语料目录分层分配题量，不让外资研报（74% chunk）压倒其它层；
  每层 ≥10%、单层 ≤35%（配图资料无可用正文，改以 ocr_derived 跨层标注覆盖 OCR 层）。
- **金标取自源内容**：每题锚定 catalog 真实 chunk_id（grade 3/2）；生成时校验锚点词
  确实出现在该 chunk 正文中，不从检索输出反推金标。
- **Holdout 密封**：Holdout 题面/金标只写本地密封路径；仓库仅落 freeze manifest
  （sha256 + 组成统计 + 分层容量）。
- **反泄漏**：Dev/Holdout 目标文档集不相交；cross_doc 的 gold 文档同属一个 split；
  Legacy 九个 target 文档不参与新题金标。

用法:
  python docs/p8_review/scripts/p8_bench_build.py --report
  python docs/p8_review/scripts/p8_bench_build.py --split development --out <repo path>
  python docs/p8_review/scripts/p8_bench_build.py --split holdout --out <sealed local path>
  python docs/p8_review/scripts/p8_bench_build.py --split both --outdir <dir> --manifest <json>
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
CATALOG = REPO / "data" / "catalog_full.db"
SEED = "p8-bench-01-20260911"

LEGACY_TARGETS = {"M04", "M05", "M06", "M07", "M09", "M10", "M16", "M18", "M22"}

TIER_OF_DIR = [
    ("外资研报", "broker_report"),
    ("科技日报", "daily_report"),
    ("中港交易台", "trading_desk"),
    ("北美交易台", "trading_desk"),
    ("SemiAnalysis", "research_media"),
    ("公众号", "research_media"),
    ("即时讨论", "discussion"),
    ("配图资料", "image_material"),
]
TIER_QUOTA = {"flagship": 30, "broker_report": 30, "daily_report": 25,
              "trading_desk": 15, "research_media": 25, "discussion": 25}
QTYPE_ORDER = ["exact_entity", "exact_number", "semantic_thesis", "causal",
               "temporal", "long_tail", "cross_doc"]
QTYPE_QUOTA = {"exact_entity": 25, "exact_number": 25, "semantic_thesis": 30, "causal": 20,
               "temporal": 15, "long_tail": 15, "cross_doc": 20}
SOURCE_TYPE = {"flagship": "flagship", "broker_report": "formal_report", "daily_report": "daily",
               "trading_desk": "daily", "research_media": "other", "discussion": "discussion",
               "image_material": "image_material"}
ID_PREFIX = {"flagship": "FB", "broker_report": "DB", "daily_report": "DY", "trading_desk": "TD",
             "research_media": "RM", "discussion": "DS"}

OCR_DOCS: set[str] = set()

LATIN = re.compile(r"[A-Za-z][A-Za-z0-9\-\.]{2,}")
NUM = re.compile(r"(?<![\w.])(\d{1,3}(?:,\d{3})*(?:\.\d+)?|\d+(?:\.\d+)?)\s*"
                 r"(%|％|个百分点|pct|bp|bps|倍|万亿元|亿元|亿美元|万美元|万|亿|"
                 r"nm|um|mm|GW|GWh|MW|kW|TWh|GB|TB|PB|TFLOPS|TOPS|FLOPS|美元|元|"
                 r"ms|ns|GB/s|TB/s)")
DATE = re.compile(r"(?<![\d/年])(20\d{2}\s*(?:[-/年\.]\s*\d{1,2}(?:\s*[-/月\.]\s*\d{1,2})?)?|"
                  r"Q[1-4]\s*[-/]?\s*20\d{2}|20\d{2}\s*Q[1-4]|"
                  r"(?:0?[1-9]|1[0-2])\s*月\s*(?:[12]\d|3[01]|0?[1-9])\s*日)(?![\d/])")
TICKER_RE = re.compile(r"^[A-Z]{1,5}(?:\.[A-Z]{1,3})?$")
# 严格实体：词典实体，或经验证的产品/型号代码（含数字且形态干净）
STRICT_CODE_RE = re.compile(
    r"^(?:(?:[A-Za-z]{1,4}\d{1,5}[A-Za-z]{0,3})|(?:\d[A-Z]{2,4})|(?:\dQFY\d{2}[A-Z]?))$")
DOT_CODE_RE = re.compile(r"^[A-Za-z]{2,8}\.\d{1,2}$")
# 日期/币种/期间/文件等伪实体前缀
ARTIFACT_RE = re.compile(
    r"^(?:19|20)\d{2}$|^(?:Rmb|RMB|Rmb|USD|EUR|JPY|CNY|HKD|FY|CY|Q[1-4]|Mar|Apr|May|Jun|Jul|Aug|"
    r"Sep|Oct|Nov|Dec|Jan|Feb|p\d+|img|image|page|fig|chart|exhibit|table|part|top|sec|appendix|note)",
    re.I)
PERSON_RE = re.compile(r"^[A-Z][a-z]+\.[A-Z]|^[A-Z][a-z]+[0-9]+$|^[a-z]+\.[a-z]")
CAUSAL = re.compile(r"(因为|由于|导致|因此|使得|驱动|原因是|之所以|"
                    r"because|due to|driven by|as a result|led to|results from)")
STOP = set("""
the and for with that this from have has had are was were will would can could not but its their our your they
them there here what which who whom when where why how all any both each few more most other some such only
own same so than too very just don now summary known risks page pages figures source note notes disclaimer
important global research americas asia europe equity securities morning futures update daily report reports
company market markets price target results data growth risk investment china us inc ltd corp llc london york
limited group holdings international capital partners fund management analytics intelligence technology
technologies system systems business financial services new news week month year today yesterday tomorrow
great good chart thanks via estimated estimate expect expects expected guidance consensus revenue earnings
margin margins quarter quarterly annual yoy qoq mom saar ebitda eps fcf roe roic
assessing pressures buyouts encouragingly engagements bookmark bearish bullish dollar between management
called early video models zero shot discuss discussing comment comments agree disagree thinking view views
thread post poster note point points question answer replies replay update updates today tonight yesterday
worth watch watching looking look looks likely unlikely maybe probably perhaps actually really basically
still already almost nearly around about above below over under again further however therefore moreover
also plus minus total overall average level levels number numbers rate rates value values case cases
""".split())
# 明显非实体的评级/职能/通用缩写（避免把 AAA / CEO 之类当查询焦点）
ACRONYM_BLOCK = set("""
AAA AA BBB BB CCC CC DDD DD BUY SELL HOLD OVERWEIGHT UNDERWEIGHT NEUTRAL OW UW EW ESG CEO CFO CTO COO
IPO CFO M A YOY QOQ MOM EPS PE PB ROE ROIC EBITDA FCF ARR MRR TP SL US UK EU UN IT PC PDF OCR OCRD
L1 L2 L3 NA NB AS IS TO BE OF IN ON AT BY OR IF SO NO YES ALL ANY NONE
""".split())
# AI / 半导体 / 科技 / 金融领域实体词典（大小写不敏感匹配）
LEX = set(w.lower() for w in """
Nvidia NVIDIA AMD Intel TSMC Samsung Hynix SKHynix Micron ASML AppliedMaterials Lam LamResearch KLA ARM
Qualcomm Broadcom Marvell MediaTek Google Microsoft Amazon Meta Apple OpenAI Anthropic xAI Tesla BYD
Alibaba Tencent Baidu Huawei SMIC CXMT YMTC NIO XPeng LiAuto Xiaomi Foxconn ASE Amkor UMC GlobalFoundries
CoWoS HBM HBM3 HBM3E HBM4 EUV DUV GAA FinFET RISC-V Transformer Gemini Claude GPT GPT4 GPT5 Llama
DeepSeek Qwen Kimi Moonshot Mistral Grok Copilot Blackwell Hopper Rubin Grace Thor GB200 GB300 H100 H200
B100 B200 A100 MI300 MI325 MI355 TPU TPUv4 TPUv5 TPUv7 Trainium Inferentia Groq Cerebras SambaNova
Graphcore ARM Neoverse GraceHopper NVL72 NVL36 DGX HGX InfiniBand NVLink PCIe CXL DDR5 HBM2E LPDDR
Ethernet Wi-Fi WiFi 5G 6G IoT AIoT SoC CPU GPU FPGA ASIC IP EDA Cadence Synopsys Siemens Mentor
Ansys Keysight Advantest Teradyne TokyoElectron Screen Dainippon ShinEtsu Sumco JSR TOK Ibiden
Nitto Shinko Ibiden Unimicron Nan Ya Kinsus AT&S Zhen Ding
Fed FOMC CPI PCE GDP PMI ECB BOJ PBOC OPEC NFP ISM ECI PPI YCC QE QT TGA RRP SOFR LIBOR HIBOR
Bitcoin Ethereum Binance Coinbase ETF REIT MLP SPX NDX HSI CSI KOSPI NIKKEI VIX
Anthropic Claude Codex ChatGPT Sora Veo Grok Midjourney StableDiffusion
Semiconductor DRAM NAND SSD SoC CPU GPU FPGA ASIC IP EDA Cadence Synopsys Siemens Mentor
Ansys Keysight Advantest Teradyne TokyoElectron Screen Dainippon ShinEtsu Sumco JSR TOK Ibiden
Nitto Shinko Ibiden Unimicron Nan Ya Kinsus AT&S Zhen Ding
Fed FOMC CPI PCE GDP PMI ECB BOJ PBOC OPEC NFP ISM ECI PPI YCC QE QT TGA RRP SOFR LIBOR HIBOR
Bitcoin Ethereum Binance Coinbase ETF REIT MLP SPX NDX HSI CSI KOSPI NIKKEI VIX
Anthropic Claude Codex ChatGPT Sora Veo Grok Midjourney StableDiffusion
RAG
NVDATSM MU WDC STX AVGO MRVL QCOM INTC GFS ONTO CAMT NVMI ACLS AEIS MKSI ENTG COHR LITE FN JBL CLS
SANM FLEX VICR MPWR SLAB SWKS QRVO CRUS SYNA LSCC ALGM POWI DIOD VSH TTMI PLXS KEYS TDY GRMN TRMB ZBRA
DELL HPE SMCI VRT ETN SIE ABBN PH EMR ROK CEG VST NRG TLN OKLO SMR PLTR SNOW DDOG MDB NET CRWD PANW ZS
FTNT NOW WDAY INTU PYPL SQ SHOP UBER LYFT ABNB DASH NFLX DIS SPOT RBLX TTWO EA MSFT GOOGL GOOG AMZN META
AAPL TSLA ORCL CRM ADBE IBM CSCO AMD ASML LRCX KLAC AMAT TER ADI TXN NXPI STM IFX INFY
H100 H200 H800 A100 A800 B100 B200 B300 GB10 GB200 GB300 NVL36 NVL72 NVL576 NVL1152 DGX HGX MGX
MI300 MI300X MI325 MI325X MI350 MI355 MI400 MI450 TPUv2 TPUv3 TPUv4 TPUv5 TPUv5e TPUv5p TPUv6 TPUv7
Trainium Trainium2 Trainium3 Inferentia Gaudi2 Gaudi3 MTIA Dojo
HBM2E HBM3 HBM3E HBM4 HBM4E DDR4 DDR5 LPDDR5 LPDDR5X GDDR6 GDDR7 GDDR6X
N3 N3E N3P N3B N2 N2P N5 N5P N4 N4P N7 N16 A16 A14 SF2 SF3 18A 14A Intel4 Intel3 Intel18A Intel20A
Snapdragon Exynos Dimensity TensorG3 TensorG4
Blackwell Hopper Ada Lovelace Ampere Volta Turing Pascal CDNA3 CDNA4 RDNA3 RDNA4 Zen4 Zen5
Gemini GPT4 GPT4o GPT5 GPT5o Claude3 Claude35 Claude4 Llama2 Llama3 Llama4 Mistral DeepSeekV3 DeepSeekR1
Qwen2 Qwen25 Qwen3 Kimi Grok2 Grok3 Grok4 Sora Veo Flux StableDiffusion Midjourney
EUV DUV HighNA CoWoS SoIC InFO Foveros EMIB HybridBonding
RISC-V ARMv9 Neoverse Chiplet UCIe PCIe5 PCIe6 NVLink NVSwitch InfiniBand UltraEthernet
VR200 VR300 Rubin Vera Thor Orin Xavier Drive
OSFP QSFP CPO LPO SiliconPhotonics
""".split())


# 产品/型号代码：GB200、H100、TPUv7、N3E、AST2700、MI300X、4QFY25 等
CODE_RE = re.compile(r"\b(?:\d?[A-Z]{1,4}\d{2,5}[A-Za-z]{0,3}|\d[A-Z]{2,4}|\dQFY\d{2}[A-Z]?)\b")

UNIT_NAME = {"%": "占比或同比增速", "％": "占比或同比增速", "bp": "基点变动", "bps": "基点变动",
             "个百分点": "百分点变化", "pct": "百分比", "倍": "倍数", "万亿元": "金额",
             "亿元": "金额", "亿美元": "金额", "万美元": "金额", "美元": "金额", "元": "金额",
             "万": "数量", "亿": "数量", "nm": "制程节点", "um": "尺寸", "mm": "尺寸",
             "GW": "装机或产能", "GWh": "产能", "MW": "装机或产能", "kW": "功率", "TWh": "电量",
             "GB": "容量", "TB": "容量", "PB": "容量", "TFLOPS": "算力", "TOPS": "算力",
             "FLOPS": "算力", "ms": "时延", "ns": "时延", "GB/s": "带宽", "TB/s": "带宽"}

CN_GENERIC = {"元信息", "正文", "配图", "研究报告", "深度研究报告", "报告", "摘要", "结论", "观点",
              "分析", "市场", "行业", "公司", "数据", "投资", "风险", "执行摘要", "核心",
              "本章结论", "参考文献", "引用文献", "主要参考文献", "参考锚定文献", "附录", "目录",
              "引言", "论据", "方法论", "数据来源", "研究框架", "核心结论", "研究结论", "总结",
              "资料来源", "参考资料", "注释", "附注", "表格", "图表", "术语表", "免责声明"}
HEAD_BAD = re.compile(r"^[一二三四五六七八九十]+[、.]|^\d+(?:\.\d+)*[\s、.]|^\(?\d+\)")


def ro() -> sqlite3.Connection:
    c = sqlite3.connect(f"file:{CATALOG}?mode=ro", uri=True)
    c.row_factory = sqlite3.Row
    return c


def h(*parts: str) -> str:
    return hashlib.sha256(("|".join([SEED, *parts])).encode("utf-8")).hexdigest()


def tier_of(sp: str) -> str | None:
    sp = sp.replace("\\", "/")
    if sp.startswith("D:/AI深度报告归档"):
        return "flagship"
    for d, t in TIER_OF_DIR:
        if f"/markdown/{d}/" in sp:
            return t
    return None


def is_meta(text: str) -> bool:
    t = text.strip()
    return t.startswith("- 发布：") or ("源文件：" in t and len(t) < 700)


CANON = {"google": "Google", "meta": "Meta", "uber": "Uber", "amazon": "Amazon", "cadence": "Cadence",
         "grok": "Grok", "sora": "Sora", "circle": "Circle", "vector": "Vector", "flash": "Flash",
         "dash": "Dash", "copilot": "Copilot", "anthropic": "Anthropic", "claude": "Claude",
         "openai": "OpenAI", "nvidia": "NVIDIA", "microsoft": "Microsoft", "apple": "Apple",
         "tesla": "Tesla", "alibaba": "Alibaba", "tencent": "Tencent", "baidu": "Baidu",
         "huawei": "Huawei", "samsung": "Samsung", "hynix": "Hynix", "micron": "Micron",
         "intel": "Intel", "qualcomm": "Qualcomm", "broadcom": "Broadcom", "marvell": "Marvell",
         "mediatek": "MediaTek", "xai": "xAI", "kimi": "Kimi", "qwen": "Qwen", "deepseek": "DeepSeek",
         "mistral": "Mistral", "llama": "Llama", "gemini": "Gemini", "netflix": "Netflix",
         "disney": "Disney", "spotify": "Spotify", "binance": "Binance", "coinbase": "Coinbase",
         "amkor": "Amkor", "umc": "UMC", "smic": "SMIC", "cxmt": "CXMT", "ymtc": "YMTC",
         "su7": "SU7", "wifi": "Wi-Fi", "coinbase": "Coinbase"}


# 大小写敏感：这些缩写同时也是常见英文词，必须按原样匹配，避免 shop/keys/net 误命中
CASE_SENSITIVE = set("NET NOW SHOP KEYS DIS SQ FLEX LITE DASH SPOT EA U FN ON ALL ANY IT InFO".split())
LEX -= {t.lower() for t in CASE_SENSITIVE}
CANON.update({"gpt": "GPT", "gpu": "GPU", "cpu": "CPU", "nvlink": "NVLink", "cowos": "CoWoS",
              "hbm": "HBM", "dram": "DRAM", "nand": "NAND", "ssd": "SSD", "ddr4": "DDR4",
              "hbm4e": "HBM4E", "mi450": "MI450", "nvl1152": "NVL1152", "spx": "SPX", "ndx": "NDX",
              "vix": "VIX", "fomc": "FOMC", "cpi": "CPI", "gdp": "GDP", "fed": "Fed", "ism": "ISM",
              "pboc": "PBOC", "nfp": "NFP", "ycc": "YCC", "dojo": "Dojo", "thor": "Thor",
              "orin": "Orin", "drive": "Drive", "agent": "Agent", "cloud": "Cloud",
              "memory": "Memory", "datacenter": "Datacenter", "hyperscaler": "Hyperscaler",
              "kospi": "KOSPI", "nikkei": "Nikkei", "nio": "NIO", "byd": "BYD", "txn": "TXN",
              "mdb": "MDB", "screen": "Screen", "flex": "Flex", "keys": "Keys",
              "nflx": "NFLX", "flux": "FLUX", "mi325x": "MI325X", "gaudi2": "Gaudi2",
              "lpddr5x": "LPDDR5X", "hbm2e": "HBM2E", "rubin": "Rubin", "qrvo": "QRVO",
              "lyft": "Lyft", "chatgpt": "ChatGPT", "asic": "ASIC", "tpu": "TPU", "msft": "MSFT",
              "etf": "ETF", "tok": "TOK", "nand": "NAND", "nvl72": "NVL72", "nvl36": "NVL36"})


def clean_term(w: str) -> str | None:
    """严格实体门：仅接受词典实体（公司/机构/技术/产品），并规范大小写。

    不接受句词、人名、日期、币种、图表/文件标记及未登记型号代码，避免把 OCR 噪音当查询焦点。
    """
    w = w.strip(".-_")
    if len(w) < 2 or len(w) > 24 or w.isdigit():
        return None
    if not any(c.isalpha() for c in w):
        return None
    if w in CASE_SENSITIVE:
        return w
    lw = w.lower()
    if lw in STOP or lw in ACRONYM_BLOCK:
        return None
    if lw in LEX:
        return CANON.get(lw, w)
    return None


def entity_terms(text: str) -> list[str]:
    out = []
    for m in CODE_RE.finditer(text):
        w = clean_term(m.group(0))
        if w:
            out.append(w)
    for m in LATIN.finditer(text):
        w = clean_term(m.group(0))
        if w:
            out.append(w)
    return out



def load_corpus(conn) -> dict:
    corpus = defaultdict(list)
    for r in conn.execute("SELECT id, title, source_path, sha256 FROM documents ORDER BY id"):
        t = tier_of(r["source_path"])
        if t is None or t == "image_material":
            continue
        if t == "flagship" and r["id"] in LEGACY_TARGETS:
            continue
        chunks = []
        for c in conn.execute(
            "SELECT id, section_id, heading_path, plain_text, content_type, ordinal "
            "FROM chunks WHERE document_id=? ORDER BY ordinal", (r["id"],)):
            text = c["plain_text"] or ""
            if not (120 <= len(text) <= 1500) or is_meta(text):
                continue
            chunks.append({"id": c["id"], "heading_path": c["heading_path"] or "",
                           "text": text, "ct": c["content_type"]})
        if not chunks:
            continue
        toks = set()
        for c in chunks:
            for w in entity_terms(c["text"]):
                toks.add(w)
        corpus[t].append({"id": r["id"], "title": (r["title"] or "").strip(),
                          "sha256": r["sha256"] or "", "chunks": chunks, "tokens": sorted(toks),
                          "blob": "\n".join(c["text"] for c in chunks)})
    return corpus


def make_splits(corpus):
    dev, hold = defaultdict(list), defaultdict(list)
    for t, docs in corpus.items():
        for i, d in enumerate(sorted(docs, key=lambda d: h("split", d["id"]))):
            (dev if i % 2 == 0 else hold)[t].append(d)
    return dev, hold


def token_df(docs):
    df = defaultdict(int)
    for d in docs:
        for tok in d["tokens"]:
            df[tok] += 1
    return df


TPL = {
    "exact_entity": ["报告中 {t} 的现状与定位有哪些说明？", "{t} 在报告里是如何描述的？",
                     "关于 {t}，报告给出了哪些关键信息？"],
    "exact_number": ["报告中 {t} 对应的 {u} 指标是多少？", "按报告，{t} 的 {u} 数值是多少？",
                     "{t} 在报告中的数据（{u}）是多少？"],
    "semantic_thesis": ["报告关于「{t}」的核心判断是什么？", "针对「{t}」，报告的主要结论是什么？",
                        "报告如何概括「{t}」这一主题？"],
    "causal": ["报告中，{t} 的驱动因素 / 原因是什么？", "报告如何解释 {t} 的出现？",
               "按报告，是什么导致或推动了 {t}？"],
    "temporal": ["报告在 {d} 前后提到了哪些与 {t} 相关的进展？", "{d} 期间，报告记录的 {t} 有哪些变化？"],
    "long_tail": ["报告中提到的 {t} 指什么？", "{t} 在报告中的含义或背景是什么？"],
    "cross_doc": ["综合多份材料，{t} 的情况是怎样的？", "这几份报告如何看待 {t}？"],
}
DIFF = {"exact_entity": "medium", "exact_number": "medium", "temporal": "medium",
        "semantic_thesis": "hard", "causal": "hard", "long_tail": "hard", "cross_doc": "hard"}


def phrase(qtype, term, extra=None):
    tpls = TPL[qtype]
    t = tpls[int(h("tpl", qtype, term)[:8], 16) % len(tpls)]
    u = (extra or {}).get("unit_name") or (extra or {}).get("unit", "数值")
    return t.format(t=term, u=u, d=(extra or {}).get("date", ""))


def good_heading(hp, df=None):
    """仅接受干净的中文实义标题（4-16 字、无句读/编号/数字），或含严格实体的标题。"""
    for p in reversed(hp.split(">")):
        p = p.strip().replace("_", " ").strip()
        if not p or p in CN_GENERIC or p.startswith("配图"):
            continue
        if "OCR" in p or "图表" in p or "（p" in p or "锚点" in p or HEAD_BAD.match(p):
            continue
        if any(k in p for k in ("总表", "汇总表", "统计表", "对照表", "清单", "明细表")):
            continue
        if any("\u4e00" <= ch <= "\u9fff" for ch in p):
            if 4 <= len(p) <= 16 and not any(ch in p for ch in "：:。；;！!？?，,、（）()") \
                    and not any(ch.isdigit() for ch in p):
                return p
            continue
        terms = entity_terms(p)
        if terms:
            terms.sort(key=lambda w: (-len(w), w))
            return terms[0]
    return ""


def title_term(doc, df):
    terms = entity_terms(doc["title"] or "")
    if terms:
        terms.sort(key=lambda w: (df.get(w, 999), -len(w), w))
        return terms[0]
    return ""


def pick_term(chunk, df, lo, hi):
    cands = []
    for w in entity_terms(chunk["text"]):
        if w and lo <= df.get(w, 1) <= hi:
            cands.append(w)
    cands.sort(key=lambda w: (df.get(w, 1), -len(w), w))
    return cands[0] if cands else None


def base_item(qtype, tier, docs, gold, term, query, extra=None):
    src = [{"document_id": d["id"], "sha256": d["sha256"]} for d in docs]
    return {"query": query, "query_type": qtype, "source_type": SOURCE_TYPE[tier],
            "corpus_tier": tier, "difficulty": DIFF[qtype],
            "temporal": qtype == "temporal" or bool(extra and extra.get("date")),
            "gold": {"mode": "chunk_ids", "chunks": gold}, "source_hashes": src,
            "notes": f"auto-authored qtype={qtype} tier={tier} anchor_term={term!r}"
                     + (f" extra={extra}" if extra else ""), "version": "1.0"}


def author(qtype, tier, doc, df):
    chunks = doc["chunks"]
    if qtype == "exact_entity":
        for c in chunks:
            term = pick_term(c, df, 2, 200)
            if term:
                return base_item(qtype, tier, [doc], [{"chunk_id": c["id"], "grade": 3}], term,
                                 phrase(qtype, term))
    elif qtype == "exact_number":
        for c in chunks:
            term = pick_term(c, df, 2, 200)
            m = NUM.search(c["text"])
            if term and m:
                unit = m.group(2)
                extra = {"unit": unit, "value": m.group(1),
                         "unit_name": UNIT_NAME.get(unit, "数值")}
                return base_item(qtype, tier, [doc], [{"chunk_id": c["id"], "grade": 3}], term,
                                 phrase(qtype, term, extra), extra)
    elif qtype == "semantic_thesis":
        for c in chunks:
            hp = c["heading_path"]
            if any(k in hp for k in ("摘要", "结论", "观点", "判断", "核心", "Summary", "Takeaway")) \
                    or c["ct"] == "summary":
                term = good_heading(hp, df) or pick_term(c, df, 2, 200)
                if term:
                    return base_item(qtype, tier, [doc], [{"chunk_id": c["id"], "grade": 3}], term,
                                     phrase(qtype, term))
        c = chunks[0]
        term = good_heading(c["heading_path"], df) or pick_term(c, df, 2, 200)
        if term:
            return base_item(qtype, tier, [doc], [{"chunk_id": c["id"], "grade": 3}], term,
                             phrase(qtype, term))
    elif qtype == "causal":
        for c in chunks:
            if not CAUSAL.search(c["text"]):
                continue
            term = pick_term(c, df, 2, 200) or good_heading(c["heading_path"], df)
            if term:
                return base_item(qtype, tier, [doc], [{"chunk_id": c["id"], "grade": 3}], term,
                                 phrase(qtype, term))
    elif qtype == "temporal":
        for c in chunks:
            m = DATE.search(c["text"])
            if not m:
                continue
            ym = re.search(r"(20\d{2})", m.group(1))
            if ym and not (2015 <= int(ym.group(1)) <= 2028):
                continue  # 过滤引文中的历史年份，避免常识性错配
            term = pick_term(c, df, 2, 300) or good_heading(c["heading_path"], df)
            if term:
                extra = {"date": m.group(1).strip()}
                return base_item(qtype, tier, [doc], [{"chunk_id": c["id"], "grade": 3}], term,
                                 phrase(qtype, term, extra), extra)
    elif qtype == "long_tail":
        for c in chunks:
            term = pick_term(c, df, 1, 3)
            if term:
                return base_item(qtype, tier, [doc], [{"chunk_id": c["id"], "grade": 3}], term,
                                 phrase(qtype, term))
    return None


def author_cross(tier, doc, docs, df, used_terms):
    for c in doc["chunks"]:
        for w in entity_terms(c["text"]):
            if not w or w in used_terms or not (3 <= df.get(w, 0) <= 15):
                continue
            others = [d for d in docs if d["id"] != doc["id"] and w in d["blob"]]
            if not others:
                continue
            d2 = sorted(others, key=lambda d: h("xd", d["id"]))[0]
            c2 = next(ch for ch in d2["chunks"] if w in ch["text"])
            return base_item("cross_doc", tier, [doc, d2],
                             [{"chunk_id": c["id"], "grade": 3}, {"chunk_id": c2["id"], "grade": 2}],
                             w, phrase("cross_doc", w)), w
    return None, None


def allocate_slots():
    free = dict(TIER_QUOTA)
    slots = defaultdict(list)
    tiers = sorted(TIER_QUOTA)
    ti = 0
    for qt in QTYPE_ORDER:
        need = QTYPE_QUOTA[qt]
        while need > 0:
            t = tiers[ti % len(tiers)]
            ti += 1
            if free[t] <= 0:
                avail = [x for x in tiers if free[x] > 0]
                if not avail:
                    break
                t = avail[0]
            slots[t].append(qt)
            free[t] -= 1
            need -= 1
    for t in tiers:
        while free[t] > 0:
            slots[t].append("semantic_thesis")
            free[t] -= 1
    return slots


def author_split(name, split_docs, df, target=150):
    slots = allocate_slots()
    items, drops = [], []
    used_q, used_notes, used_terms = set(), set(), set()
    per_doc = Counter()
    for tier in sorted(slots):
        docs = split_docs.get(tier, [])
        for qt in slots[tier]:
            if len(items) >= target:
                break
            ordered = sorted(docs, key=lambda d: (per_doc[d["id"]], h("doc", d["id"])))
            made = None
            for d in ordered:
                if per_doc[d["id"]] >= 2:
                    continue
                if qt == "cross_doc":
                    cand, term = author_cross(tier, d, docs, df, used_terms)
                    if cand:
                        made, used = cand, term
                else:
                    cand = author(qt, tier, d, df)
                    if cand:
                        made, used = cand, cand["notes"]
                if made and made["query"] not in used_q and made["notes"] not in used_notes:
                    break
                made = None
            if not made:
                drops.append({"tier": tier, "qtype": qt, "reason": "no_candidate"})
                continue
            made["split"] = name
            items.append(made)
            used_q.add(made["query"]); used_notes.add(made["notes"])
            if used:
                used_terms.add(used)
            per_doc[made["source_hashes"][0]["document_id"]] += 1

    # backfill 到 target：semantic_thesis / exact_entity，允许每文档至多 3 题
    if len(items) < target:
        for tier in sorted(slots):
            docs = sorted(split_docs.get(tier, []), key=lambda d: h("bf", d["id"]))
            for qt in ("semantic_thesis", "exact_entity", "causal", "temporal"):
                for d in docs:
                    if len(items) >= target:
                        break
                    if per_doc[d["id"]] >= 3:
                        continue
                    cand = author(qt, tier, d, df)
                    if not cand or cand["query"] in used_q or cand["notes"] in used_notes:
                        continue
                    cand["split"] = name
                    items.append(cand)
                    used_q.add(cand["query"]); used_notes.add(cand["notes"])
                    per_doc[cand["source_hashes"][0]["document_id"]] += 1
    if len(items) > target:
        items.sort(key=lambda x: (x["corpus_tier"], x["query_type"], x["notes"]))
        items = items[:target]
    return items, drops


def assign_ids(items):
    counters = defaultdict(int)
    ordered = sorted(items, key=lambda x: (x["corpus_tier"], x["query_type"], x["notes"]))
    for it in ordered:
        pfx = "XD" if it["query_type"] == "cross_doc" else ID_PREFIX[it["corpus_tier"]]
        counters[pfx] += 1
        it["id"] = f"{pfx}-{counters[pfx]:03d}"
    return ordered


def composition(items):
    tier, qt, st = Counter(), Counter(), Counter()
    docs, ocr = set(), 0
    for it in items:
        tier[it["corpus_tier"]] += 1; qt[it["query_type"]] += 1; st[it["source_type"]] += 1
        ocr += 1 if it.get("ocr_derived") else 0
        for s in it["source_hashes"]:
            docs.add(s["document_id"])
    n = len(items)
    return {"n": n, "by_tier": dict(sorted(tier.items())), "by_query_type": dict(sorted(qt.items())),
            "by_source_type": dict(sorted(st.items())), "distinct_gold_docs": len(docs),
            "ocr_derived": ocr, "ocr_derived_share": round(ocr / n, 4) if n else 0.0,
            "max_tier_share": round(max(tier.values()) / n, 4) if n else 0.0,
            "min_tier_share": round(min(tier.values()) / n, 4) if n else 0.0}


def write_jsonl(path: Path, items):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for it in items:
            f.write(json.dumps(it, ensure_ascii=False) + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", choices=["development", "holdout", "both"], default="development")
    ap.add_argument("--out")
    ap.add_argument("--outdir")
    ap.add_argument("--manifest")
    ap.add_argument("--report", action="store_true")
    a = ap.parse_args()

    conn = ro()
    global OCR_DOCS
    OCR_DOCS = {r["id"] for r in conn.execute(
        "SELECT DISTINCT d.id FROM documents d JOIN chunks c ON c.document_id=d.id "
        "WHERE c.plain_text LIKE '%- 发布：%OCR%'")}
    corpus = load_corpus(conn)
    dev, hold = make_splits(corpus)
    df_dev = token_df([d for ds in dev.values() for d in ds])
    df_hold = token_df([d for ds in hold.values() for d in ds])

    if a.report:
        print("tier caps:", TIER_QUOTA, "sum", sum(TIER_QUOTA.values()))
        print("qtype caps:", QTYPE_QUOTA, "sum", sum(QTYPE_QUOTA.values()))
        for t in sorted(corpus):
            print(f"  {t:16s} docs={len(corpus[t]):5d} dev={len(dev[t]):5d} hold={len(hold[t]):5d}")
        print("OCR-derived docs:", len(OCR_DOCS))
        return 0

    results = {}
    for name, sd, df in (("development", dev, df_dev), ("holdout", hold, df_hold)):
        if a.split not in (name, "both"):
            continue
        items, drops = author_split(name, sd, df)
        items = assign_ids(items)
        for it in items:
            it["ocr_derived"] = any(s["document_id"] in OCR_DOCS for s in it["source_hashes"])
        items.sort(key=lambda x: x["id"])
        comp = composition(items)
        results[name] = {"items": items, "drops": drops, "composition": comp}
        print(f"[{name}] n={comp['n']} ocr={comp['ocr_derived']} drops={len(drops)} "
              f"max_tier={comp['max_tier_share']} min_tier={comp['min_tier_share']}")
        print("  tier:", json.dumps(comp["by_tier"], ensure_ascii=False))
        print("  qtype:", json.dumps(comp["by_query_type"], ensure_ascii=False))

    if a.outdir:
        base = Path(a.outdir)
        for name, r in results.items():
            p = base / f"{name}_v1.jsonl"
            write_jsonl(p, r["items"]); print("wrote", p)
    elif a.out and a.split != "both":
        write_jsonl(Path(a.out), results[a.split]["items"]); print("wrote", a.out)

    if a.manifest:
        man = {"benchmark": "p8-mixed-benchmark", "version": "1.0", "seed": SEED,
               "generator": "docs/p8_review/scripts/p8_bench_build.py",
               "schema": "docs/p8_review/benchmark/schema.json",
               "catalog": str(CATALOG), "legacy_targets_excluded": sorted(LEGACY_TARGETS),
               "tier_quota": TIER_QUOTA, "query_type_quota": QTYPE_QUOTA, "splits": {}}
        for name, r in results.items():
            raw = json.dumps(r["items"], ensure_ascii=False, sort_keys=True).encode("utf-8")
            man["splits"][name] = {"n": len(r["items"]),
                                   "sha256_jsonl": _sha_jsonl(r["items"]),
                                   "sha256_canonical": hashlib.sha256(raw).hexdigest(),
                                   "composition": r["composition"], "drops": r["drops"]}
        Path(a.manifest).write_text(json.dumps(man, ensure_ascii=False, indent=2), encoding="utf-8")
        print("wrote manifest", a.manifest)
    return 0


def _sha_jsonl(items) -> str:
    hh = hashlib.sha256()
    for it in items:
        hh.update((json.dumps(it, ensure_ascii=False) + "\n").encode("utf-8"))
    return hh.hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
