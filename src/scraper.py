"""并发抓取与条目提取(RSS / Next.js flight / 服务端渲染网页)、URL 去重。"""
import concurrent.futures as cf
import hashlib
import html
import json
import re
import sys
from pathlib import Path
from urllib.parse import urljoin

import feedparser
import requests

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")
MAX_ENTRIES_PER_SOURCE = 30
_TAG = re.compile(r"<[^>]+>")
_FLIGHT_PUSH = re.compile(r'self\.__next_f\.push\(\[1,\s*("(?:[^"\\]|\\.)*")\]\)')


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


def _item(title, url, text, source, id_key=None):
    return {
        "title": (title or "(无标题)")[:200],
        "url": url,
        "text": text,
        "source": source["name"],
        "region": source.get("region", "overseas"),
        "id_key": id_key,
    }


def _extract_feed(source, text):
    feed = feedparser.parse(text)
    if feed.bozo and not feed.entries:
        raise ValueError(f"feed 解析失败: {feed.bozo_exception}")
    items = []
    for e in feed.entries[:MAX_ENTRIES_PER_SOURCE]:
        url = e.get("link", "")
        if not url:
            continue
        title = clean_title(e.get("title", ""))
        items.append(_item(title, url, f"{title}\n{e.get('summary', '')}", source))
    return items


def _flight_text(page):
    """Next.js App Router 站点的数据在 RSC flight 流(self.__next_f.push)里,拼接还原。"""
    return "".join(json.loads(c) for c in _FLIGHT_PUSH.findall(page))


def _extract_eflux(source, page):
    text = _flight_text(page)
    base = "https://www.e-flux.com"
    items, seen = [], set()
    # href 与同对象内 children 文本直接配对(featured 区,质量最高)
    for href, title in re.findall(
            r'"href"\s*:\s*"(/announcements/\d+/[^"]+)"[^}]*"children"\s*:\s*"([^"]{8,220})"', text):
        url = base + href
        if url in seen:
            continue
        seen.add(url)
        items.append(_item(html.unescape(title), url, html.unescape(title), source))
    # 其余 announcement 链接用 slug 生成标题兜底
    for href in re.findall(r'"href"\s*:\s*"(/announcements/\d+/[^"]+)"', text):
        url = base + href
        if url in seen:
            continue
        seen.add(url)
        slug = href.rstrip("/").rsplit("/", 1)[-1]
        title = slug.replace("-", " ").title()
        items.append(_item(title, url, title, source))
    return items


def _extract_artconnect(source, page):
    text = _flight_text(page)
    items, seen = [], set()
    for m in re.finditer(r'"title"\s*:\s*"([^"]{10,200})"\s*,\s*"description"\s*:\s*'
                         r'\[\{"content"\s*:\s*"((?:[^"\\]|\\.){20,1500})', text):
        title = html.unescape(m.group(1))
        try:
            desc = json.loads('"' + m.group(2) + '"')
        except json.JSONDecodeError:
            desc = m.group(2)
        # 条目自身无站内详情页,用邻近的机构外链(常为申请入口)
        ctx = text[max(0, m.start() - 2500):m.start()]
        ext = re.findall(r'"url"\s*:\s*"(https?://[^"]+)"', ctx)
        url = ext[-1] if ext else source["url"]
        if url in seen:
            continue
        seen.add(url)
        # 同一机构可能有多个机会,id 用 外链+标题 保证唯一
        items.append(_item(title, url, f"{title}\n{desc}", source, id_key=url + "|" + title))
    return items


def _extract_webpage(source, page):
    """服务端渲染列表页:标题元素(h2/h3)内的链接优先;纯图片 anchor 用 slug 兜底。"""
    pat = re.escape(source.get("link_pattern", "/"))
    items, seen = [], set()
    for m in re.finditer(
            r'<h[1-4][^>]*>\s*<a[^>]*href="([^"]*' + pat + r'[^"]*)"[^>]*>\s*([^<]{6,220})\s*</a>', page):
        href, title = m.groups()
        url = urljoin(source["url"], href)
        if url in seen:
            continue
        seen.add(url)
        title = " ".join(html.unescape(title).split())
        items.append(_item(title, url, title, source))
    for m in re.finditer(
            r'<a[^>]*href="([^"]*' + pat + r'[^"]*)"[^>]*>([\s\S]{0,700}?)</a>', page):
        href, blob = m.groups()
        url = urljoin(source["url"], href)
        if url in seen:
            continue
        seen.add(url)
        blob = " ".join(_TAG.sub(" ", html.unescape(blob)).split())
        dl = re.search(r'Deadline[:\s]*[A-Za-z]+ \d{1,2},? \d{4}', blob)
        slug = href.rstrip("/").rsplit("/", 1)[-1]
        title = (blob.split("Deadline")[0].strip() or slug.replace("-", " ").title())[:200]
        full = blob if dl else title
        items.append(_item(title, url, full, source))
    return items


EXTRACTORS = {
    "rss": _extract_feed,
    "atom": _extract_feed,
    "eflux": _extract_eflux,
    "artconnect": _extract_artconnect,
    "webpage": _extract_webpage,
}


def _fetch_one(source):
    for attempt in (1, 2):
        try:
            r = requests.get(source["url"], timeout=20, headers={"User-Agent": UA})
            r.raise_for_status()
            return EXTRACTORS[source.get("type", "rss")](source, r.text)[:MAX_ENTRIES_PER_SOURCE]
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
                h = url_hash(it.get("id_key") or it["url"])
                if h not in seen:
                    seen.add(h)
                    fresh.append(it)
    return fresh
