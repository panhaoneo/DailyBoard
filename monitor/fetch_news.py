#!/usr/bin/env python3
"""抓取 imarine.cn 站内搜索「关键词」的新闻列表（标题/分类/日期/链接），供订单信息提取使用。

用途：新闻不在页面展示；它是"原料"——从中提取逐笔订单的价格/交付期等信息，
回填跟踪卡「订单逐笔」表（提取由 Agent/人工完成，见 monitor/每日维护手册.md）。

用法:
  python3 fetch_news.py --code 603268 --keyword 恒力重工              # 仅列表
  python3 fetch_news.py --code 603268 --keyword 恒力重工 --with-text  # 同时抓正文（增量）

输出: monitor/data/{code}_news.json（含 fetched_at 与全部条目；--with-text 时每条附 text）。
失败保护: 首页失败或新结果少于旧数据一半时不覆盖旧文件（沿用仓库"保留上一版"惯例）。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import time
from datetime import datetime
from html import unescape
from urllib.parse import quote
from zoneinfo import ZoneInfo

import requests

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(ROOT, "data")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
}
ENTRY_PAT = re.compile(
    r'<h2 class="entry-title"><a href="(?P<link>[^"]+)"[^>]*>(?P<title>.*?)</a></h2>'
    r'(?P<meta>.{0,1200}?)<!-- \.entry-summary -->',
    re.S,
)
CAT_PAT = re.compile(r'entry-category">\s*<a[^>]*>([^<]+)</a>')
DATE_PAT = re.compile(r'entry-date">\s*([\d-]+)')
TEXT_LIMIT = 2500


def fetch_article_text(session, url) -> str:
    """抓取文章正文（纯文本，限长）。失败返回空串。"""
    try:
        r = session.get(url, timeout=30)
        if r.status_code != 200:
            return ""
        html = r.text
        m = re.search(r'<div class="entry-content"[^>]*>(.*?)</div>\s*</div>', html, re.S)
        body = m.group(1) if m else html
        body = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", body, flags=re.S)
        body = re.sub(r"<[^>]+>", " ", body)
        body = unescape(body)
        body = re.sub(r"\s+", " ", body).strip()
        return body[:TEXT_LIMIT]
    except Exception:
        return ""


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="抓取 imarine 站内搜索新闻列表")
    p.add_argument("--code", required=True, help="股票代码，决定输出文件名 data/{code}_news.json")
    p.add_argument("--keyword", required=True, help="站内搜索关键词，如 恒力重工")
    p.add_argument("--max-pages", type=int, default=60)
    p.add_argument("--stop-date", default="2026-01-01", help="翻页至结果早于该日期即停止")
    p.add_argument("--delay", type=float, default=0.8, help="翻页间隔秒数")
    p.add_argument("--with-text", action="store_true", help="同时抓取每条新闻的正文（增量，已有 text 的跳过）")
    args = p.parse_args(argv)

    out_path = os.path.join(DATA_DIR, f"{args.code}_news.json")
    prev, prev_text = [], {}
    if os.path.exists(out_path):
        try:
            with open(out_path, encoding="utf-8") as f:
                prev = (json.load(f).get("items") or [])
            prev_text = {x["link"]: x.get("text", "") for x in prev if x.get("link")}
        except Exception:
            prev = []

    kw = quote(args.keyword)
    session = requests.Session()
    session.headers.update(HEADERS)
    items, seen = [], set()
    try:
        for page in range(1, args.max_pages + 1):
            url = ("https://www.imarine.cn/?s=" + kw) if page == 1 else (
                f"https://www.imarine.cn/page/{page}/?s=" + kw
            )
            r = session.get(url, timeout=30)
            if r.status_code != 200:
                print(f"[!] 第 {page} 页状态 {r.status_code}，停止翻页")
                break
            found, oldest = 0, "9999"
            for m in ENTRY_PAT.finditer(r.text):
                link = m.group("link")
                if link in seen:
                    continue
                seen.add(link)
                found += 1
                meta = m.group("meta")
                cm, dm = CAT_PAT.search(meta), DATE_PAT.search(meta)
                d = dm.group(1) if dm else ""
                if d and d < oldest:
                    oldest = d
                items.append({
                    "date": d,
                    "cat": cm.group(1) if cm else "",
                    "title": m.group("title").strip(),
                    "link": link,
                    "text": prev_text.get(link, ""),
                })
            print(f"  第 {page} 页: +{found} 条（最早 {oldest}）")
            if found == 0 or (oldest != "9999" and oldest < args.stop_date):
                break
            time.sleep(args.delay)
    except Exception as e:
        print(f"[!] 抓取中断: {e}")

    if len(items) < 10 or (prev and len(items) < len(prev) * 0.5):
        print(f"[!] 结果异常（新 {len(items)} 条 / 旧 {len(prev)} 条），保留旧文件不覆盖")
        return 1

    if args.with_text:
        todo = [x for x in items if not x.get("text")]
        print(f"  抓取正文: {len(todo)} 条待抓（已有 {len(items) - len(todo)} 条）")
        ok = 0
        for i, x in enumerate(todo, 1):
            x["text"] = fetch_article_text(session, x["link"])
            if x["text"]:
                ok += 1
            if i % 20 == 0 or i == len(todo):
                print(f"    进度 {i}/{len(todo)}（成功 {ok}）")
            time.sleep(0.4)

    items.sort(key=lambda x: x.get("date") or "", reverse=True)
    data = {
        "code": args.code,
        "keyword": args.keyword,
        "fetched_at": datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y-%m-%d %H:%M"),
        "count": len(items),
        "items": items,
    }
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    print(f"已保存 {len(items)} 条 → {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
