#!/usr/bin/env python3
"""讯飞 PDF 包摄取器：PDF → processed 格式语料（零网络依赖）。

背景：讯飞交付包 environment.tar.gz 内为 5,568 篇 PDF（biorxiv/medrxiv/
arxiv/openalex 四源），文件名即 ID。OpenAlex/bioRxiv 官方 API 在部署网内
不可达，因此元数据全部来自 PDF 内嵌元数据 + 首页文本启发式解析。

输出 data/processed/xunfei_papers.json（JSON 数组，processed 格式），
source 统一为 "iflytek"（paper_uid = stable_uid("paper","iflytek",id)，
与既有 6 源零冲突、幂等 upsert 不覆盖），original_source 记录真实源。

用法：
  python3 scripts/ingest_xunfei_pdfs.py \
      --pdf-dir data/raw/iflytek/environment \
      --out data/processed/xunfei_papers.json \
      [--limit N] [--log data/processed/xunfei_ingest.log]
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import fitz  # PyMuPDF
except ImportError:  # pragma: no cover
    fitz = None
    print("缺少 PyMuPDF：pip install pymupdf", file=sys.stderr)
    sys.exit(2)

FILENAME_RE = re.compile(r"^(?P<source>biorxiv|medrxiv|arxiv|openalex)_(?P<id>.+)\.pdf$")
DOI_RE = re.compile(r"10\.\d{4,9}/[-._;()/:A-Za-z0-9]+")
YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")
ABSTRACT_RE = re.compile(
    r"(?is)abstracts?\s*[:.\-—]?\s*(.{200,4000}?)(?=\n\s*(?:keywords?|introduction|author summary|"
    r"highlights|1\.?\s+|\d+\.?\s+introduction)|$)"
)
REF_START_RE = re.compile(r"(?im)^\s*(?:references|bibliography|literature cited|致谢|acknowledg?ments?)\s*$")
PAGE_NUM_RE = re.compile(r"^\s*\d{1,4}\s*$")
HEADER_JUNK_RE = re.compile(r"(?i)(bioRxiv preprint|medRxiv preprint|doi:|https?://doi\.org/\S+)")

FIELD_BY_SOURCE = {
    "biorxiv": "biomedicine",
    "medrxiv": "medicine",
    "arxiv": "unknown",
    "openalex": "unknown",
}


def parse_filename(name: str) -> dict[str, str] | None:
    m = FILENAME_RE.match(name)
    if not m:
        return None
    source, sid = m.group("source"), m.group("id")
    # openalex_W1989668498 → W1989668498；biorxiv_10.1101_028274 → DOI 10.1101/028274
    source_id = sid
    doi = ""
    if source in ("biorxiv", "medrxiv"):
        doi = sid.replace("_", "/", 1).replace("_", "")
        source_id = doi
    elif source == "openalex":
        source_id = sid
    return {"source": source, "source_id": source_id, "doi": doi, "file_id": sid}


def extract_pdf(path: Path) -> dict[str, Any]:
    """返回 PDF 元数据、首页文本与清洗后全文。"""
    doc = fitz.open(str(path))
    try:
        meta = doc.metadata or {}
        pages = [doc.load_page(i) for i in range(min(len(doc), 4))]
        first_text = "\n".join(p.get_text() for p in pages[:1])
        # 标题/作者：取首页字号最大的文本块（bioRxiv/arXiv 标题均为最大字号）
        title, authors = _title_authors(pages[0])
        full_raw = "\n".join(p.get_text() for p in pages)
    finally:
        doc.close()
    full_text = clean_fulltext(full_raw)
    year = _guess_year(meta, first_text, path.stem)
    abstract = _guess_abstract(first_text)
    return {
        "meta_title": (meta.get("title") or "").strip(),
        "title": title,
        "authors": authors,
        "year": year,
        "abstract": abstract,
        "full_text": full_text,
        "first_text": first_text,
        "creation_date": meta.get("creationDate", ""),
    }


def _title_authors(page: Any) -> tuple[str, list[str]]:
    """首页：标题 = 开头的 1-4 行（遇到 Authors/Affiliations/ABSTRACT 停止）；
    作者 = Authors: 行或标题后紧跟的行，清洗序号与符号。"""
    text = page.get_text().strip()
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    if not lines:
        return "", []
    # 标题块：从首行起连续行，直到遇到结构标记
    title_lines: list[str] = []
    author_candidates: list[str] = []
    stop_re = re.compile(
        r"(?i)^(affiliations?|abstract|doi:|https?://|©|1|received|published|posted|correspond)"
    )
    for l in lines:
        if stop_re.match(l) and title_lines:
            break
        title_lines.append(l)
        if len(title_lines) >= 4:
            break
    # 标题行里若夹着作者行（含序号），切掉作者行
    cut = len(title_lines)
    for i, l in enumerate(title_lines):
        if re.search(r"(?i)^authors?\s*[:：]", l) or re.search(r"^\S+ \S+[,\d*#&]", l) or (
            len(title_lines) > 2 and i > 0 and len(l) < 40 and not re.search(r"[a-z]{4,}", l)
        ):
            cut = i
            break
    title = " ".join(title_lines[:cut])[:300]
    # 作者行：标题行之后的第一行
    start = cut
    for l in lines[start:]:
        if stop_re.match(l):
            break
        if re.search(r"[A-Za-z]", l) and len(l) < 260:
            author_candidates.append(l)
            break
    author_list = _clean_authors(author_candidates)
    return title, author_list


def _clean_authors(candidates: list[str]) -> list[str]:
    """把 'Authors: A1,*,#, B2 and C3' 拆成 ['A', 'B', 'C']。"""
    out: list[str] = []
    for c in candidates:
        c = re.sub(r"^authors?\s*[:：]\s*", "", c, flags=re.I)
        for part in re.split(r"(?:,|\band\b)+", c):
            name = re.sub(r"[\d*#¶]+", "", part).strip()
            name = re.sub(r"^(Dr|Prof|Mr|Ms)\.?\s+", "", name, flags=re.I)
            if re.fullmatch(r"[A-Z][a-zA-Z.'\-]+(?:\s+[A-Z][a-zA-Z.'\-]+){0,3}", name):
                out.append(name)
            elif 3 < len(name) < 60 and re.search(r"[a-z]", name) and not re.search(
                r"(university|institute|department|hospital|school|college|lab|center|centre|inc\.|ltd)", name, re.I
            ):
                out.append(name)
    # 去重保序
    seen: set[str] = set()
    return [n for n in out if not (n.lower() in seen or seen.add(n.lower()))][:30]


def _guess_year(meta: dict[str, str], first_text: str, stem: str) -> int | None:
    for candidate in (
        meta.get("creationDate", ""),
        meta.get("modDate", ""),
        first_text[:1200],
        stem,
    ):
        m = YEAR_RE.search(str(candidate))
        if m:
            y = int(m.group(0))
            if 1990 <= y <= 2030:
                return y
    # arXiv ID 前两位（2404.11939 → 2024）
    if stem.startswith("arxiv_"):
        mm = re.match(r"(\d{2})\d{2}", stem.split("_", 1)[1])
        if mm:
            return 2000 + int(mm.group(1))
    return None


def _guess_abstract(first_text: str) -> str:
    m = ABSTRACT_RE.search(first_text)
    if not m:
        return ""
    ab = re.sub(r"\s+", " ", m.group(1)).strip()
    # bioRxiv 摘要内分段标签（Background/Methods/Results/Conclusions）保留为空格分隔
    ab = re.sub(r"(?i)\b(background|methods|results|conclusions?)\b", lambda x: x.group(0).lower() + ":", ab)
    return ab[:3000]


def clean_fulltext(raw: str) -> str:
    """全文清洗：截参考文献、去页码/页眉、合并断词、剔除控制字符。"""
    # 截断到 References 起
    m = REF_START_RE.search(raw)
    if m:
        raw = raw[: m.start()]
    lines: list[str] = []
    for line in raw.split("\n"):
        line = line.strip()
        if not line:
            continue
        if PAGE_NUM_RE.match(line):
            continue
        if HEADER_JUNK_RE.search(line) and len(line) < 90:
            continue
        lines.append(line)
    text = "\n".join(lines)
    text = text.replace("-\n", "")  # 断词连字符
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def to_processed(meta: dict[str, Any], parsed: dict[str, str]) -> dict[str, Any]:
    title = (meta["title"] or meta["meta_title"]).strip()[:400] or f"untitled-{parsed['file_id']}"
    year = meta["year"]
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")
    authors = meta["authors"]
    source_id = parsed["source_id"]
    doi = parsed["doi"]
    return {
        "paper_id": f"iflytek-{parsed['file_id']}",
        "title": title,
        "abstract": meta["abstract"][:3000],
        "authors": authors,
        "year": year,
        "keywords": [],
        "field": FIELD_BY_SOURCE.get(parsed["source"], "unknown"),
        "full_text": meta["full_text"],
        "authorships": [
            {
                "author_id": "",
                "display_name": a,
                "raw_author_name": a,
                "orcid": "",
                "author_position": "first" if i == 0 else "middle",
                "author_position_index": i + 1,
                "is_corresponding": False,
                "institution_ids": [],
                "institutions": [],
                "country_codes": [],
                "raw_affiliation_strings": [],
            }
            for i, a in enumerate(authors)
        ],
        "source": "iflytek",
        "original_source": parsed["source"],
        "source_id": source_id,
        "query": "xunfei delivery",
        "field_seed": FIELD_BY_SOURCE.get(parsed["source"], "unknown"),
        "crawled_at": now,
        "text_for_analysis": (title + " " + meta["abstract"])[:2000],
        "doi": f"https://doi.org/{doi}" if doi else "",
        "url": "",
        "full_text_source": "xunfei-pdf",
        "full_text_url": "",
        "is_recent_window": False,
        "_sciscope_raw_file": f"data/raw/iflytek/environment/{parsed['source']}_{parsed['file_id']}.pdf",
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="讯飞 PDF 包 → processed 语料")
    ap.add_argument("--pdf-dir", required=True)
    ap.add_argument("--out", default="data/processed/xunfei_papers.json")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--log", default="")
    args = ap.parse_args()

    logging.basicConfig(
        filename=args.log or None,
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    pdf_dir = Path(args.pdf_dir)
    pdfs = sorted(pdf_dir.glob("*.pdf"))
    if args.limit:
        pdfs = pdfs[: args.limit]
    print(f"待处理 PDF: {len(pdfs)}", flush=True)

    papers: list[dict[str, Any]] = []
    failures: list[str] = []
    for i, p in enumerate(pdfs, 1):
        parsed = parse_filename(p.name)
        if not parsed:
            failures.append(f"{p.name}: 文件名无法解析")
            continue
        try:
            meta = extract_pdf(p)
        except Exception as exc:  # noqa: BLE001
            failures.append(f"{p.name}: {exc}")
            logging.warning("%s 解析失败: %s", p.name, exc)
            continue
        papers.append(to_processed(meta, parsed))
        if i % 200 == 0:
            print(f"  {i}/{len(pdfs)}", flush=True)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(papers, f, ensure_ascii=False, indent=1)

    with_ft = sum(1 for p in papers if len(p["full_text"]) >= 500)
    with_abs = sum(1 for p in papers if p["abstract"])
    with_title = sum(1 for p in papers if not p["title"].startswith("untitled"))
    print(f"完成: {len(papers)} 篇（标题解析 {with_title}、摘要 {with_abs}、全文≥500字 {with_ft}）")
    print(f"失败: {len(failures)}")
    for f in failures[:10]:
        print("  ", f)
    return 0 if not failures else 3


if __name__ == "__main__":
    sys.exit(main())
