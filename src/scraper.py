"""RSS 并发抓取与 URL 去重。"""
import concurrent.futures as cf
import hashlib
import html
import json
import re
import sys
from pathlib import Path

import feedparser
import requests

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
UA = "art-opportunity-radar/1.0"
MAX_ENTRIES_PER_SOURCE = 30
_TAG = re.compile(r"<[^>]+>")


def url_hash(url: str) -> str:
    return hashlib.sha256(url.encode()).hexdigest()


def clean_title(title: str) -> str:
    """部分 feed(如 On the Move)的 title 内嵌 HTML 标签,剥掉并还原实体。"""
    return html.unescape(_TAG.sub("", title)).strip()


def load_seen() -> set:
    p = DATA / "seen_urls.json"
    if not p.exists():
        return set()
    return set(json.loads(p.read_text(encoding="utf-8")).get("urls", []))


def save_seen(seen: set) -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    tmp = DATA / "seen_urls.json.tmp"
    tmp.write_text(json.dumps({"urls": sorted(seen)}, ensure_ascii=False), encoding="utf-8")
    tmp.replace(DATA / "seen_urls.json")


def _parse_feed(source: dict) -> list:
    r = requests.get(source["url"], timeout=15, headers={"User-Agent": UA})
    r.raise_for_status()
    feed = feedparser.parse(r.text)
    if feed.bozo and not feed.entries:
        raise ValueError(f"feed 解析失败: {feed.bozo_exception}")
    items = []
    for e in feed.entries[:MAX_ENTRIES_PER_SOURCE]:
        url = e.get("link", "")
        if not url:
            continue
        title = clean_title(e.get("title", ""))
        summary = e.get("summary", "")
        items.append({
            "title": title,
            "url": url,
            "text": f"{title}\n{summary}",
            "source": source["name"],
            "region": source.get("region", "overseas"),
        })
    return items


def _fetch_one(source: dict) -> list:
    for attempt in (1, 2):
        try:
            return _parse_feed(source)
        except Exception as exc:
            if attempt == 2:
                print(f"[scraper] {source['name']} 抓取失败: {exc}", file=sys.stderr)
    return []


def fetch_all(sources: list, seen: set) -> list:
    """并发抓取全部源;返回 seen 中不存在的新条目,并把新 URL 计入 seen(内存)。"""
    fresh = []
    with cf.ThreadPoolExecutor(max_workers=8) as pool:
        for items in pool.map(_fetch_one, sources):
            for it in items:
                h = url_hash(it["url"])
                if h not in seen:
                    seen.add(h)
                    fresh.append(it)
    return fresh
