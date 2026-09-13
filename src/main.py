"""入口:抓取 → 初筛 → AI 打分 → 归档 → 通知。用法见 README(--dry-run / --region)。"""
import argparse
import datetime as dt
import json
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from analyzer import keyword_categories, keyword_stage, llm_stage, parse_deadline
from notifier import notify
from scraper import DATA, fetch_all, load_seen, save_seen, url_hash

ROOT = Path(__file__).resolve().parent.parent


def load_yaml(path: str) -> dict:
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))


def load_db() -> dict:
    p = DATA / "opportunities.json"
    if not p.exists():
        return {"updated_at": "", "items": []}
    return json.loads(p.read_text(encoding="utf-8"))


def atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def priority_of(relevance: int, th: dict) -> str:
    if relevance >= th["ai_priority_high"]:
        return "HIGH"
    if relevance >= th["ai_relevance_notify"]:
        return "MAYBE"
    return "LOW"


def archive_expired(db: dict) -> dict:
    cutoff = (dt.date.today() - dt.timedelta(days=30)).isoformat()
    keep, moved = [], []
    for it in db["items"]:
        if it.get("deadline") and it["deadline"] < cutoff:
            moved.append(it)
        else:
            keep.append(it)
    if moved:
        month = dt.date.today().strftime("%Y-%m")
        arch = DATA / "archive" / f"{month}.json"
        existing = json.loads(arch.read_text(encoding="utf-8")) if arch.exists() else []
        existing_ids = {e["id"] for e in existing}
        existing += [m for m in moved if m["id"] not in existing_ids]
        atomic_write(arch, json.dumps(existing, ensure_ascii=False, indent=1))
    db["items"] = keep
    return db


def build_entry(raw: dict, score: int, th: dict) -> dict:
    relevance = min(100, score * 10)
    return {
        "id": url_hash(raw.get("id_key") or raw["url"])[:16],
        "title": raw["title"][:200] or "(无标题)",
        "organization": None,
        "country": None,
        "url": raw["url"],
        "source": raw["source"],
        "region": raw["region"],
        "deadline": parse_deadline(raw["text"]),
        "summary": "",
        "funding": {"fully_funded": None, "stipend": None,
                     "accommodation": None, "travel": None},
        "categories": keyword_categories(raw["text"]),
        "relevance": relevance,
        "priority": priority_of(relevance, th),
        "first_seen": dt.date.today().isoformat(),
        "ai_scored": False,
        "_text": raw["text"],
    }


def merge_items(db: dict, new_items: list) -> list:
    existing = {it["id"]: it for it in db["items"]}
    merged = []
    for item in new_items:
        if item["id"] in existing:
            for k in ("relevance", "priority", "deadline", "summary", "funding",
                      "categories", "organization", "country"):
                if item.get(k) not in (None, "", []):
                    existing[item["id"]][k] = item[k]
        else:
            merged.append(item)
            existing[item["id"]] = item
    return merged


def main() -> int:
    ap = argparse.ArgumentParser(description="艺术机会雷达")
    ap.add_argument("--dry-run", action="store_true",
                    help="只抓取和初筛,不调 AI、不通知、不写任何文件")
    ap.add_argument("--region", choices=["overseas", "cn"], default=None,
                    help="只处理指定 region 的源(默认全部)")
    args = ap.parse_args()

    kw = load_yaml(str(ROOT / "config" / "keywords.yml"))
    th = kw["thresholds"]
    sources_cfg = load_yaml(str(ROOT / "config" / "sources.yml"))
    sources = [s for s in sources_cfg["sources"]
               if args.region is None or s.get("region") == args.region]
    if not sources:
        print("sources.yml 中没有匹配的源", file=sys.stderr)
        return 1

    seen = load_seen()
    raw_items = fetch_all(sources, seen)
    print(f"本轮抓取:新条目 {len(raw_items)} 个")

    entries = []
    for raw in raw_items:
        score = keyword_stage(raw["text"], kw)
        if score is None or score < th["keyword_min_score"]:
            continue
        entries.append(build_entry(raw, score, th))
    print(f"关键词初筛通过: {len(entries)} 个")

    if args.dry_run:
        for e in entries:
            print(f"  [{e['priority']}] {e['title']} (score→{e['relevance']})")
        print("dry-run 结束,未写任何文件")
        return 0

    for e in entries:
        ai = llm_stage(e.pop("_text", e["url"]))
        if ai:
            e.update({k: ai[k] for k in ("organization", "country", "deadline",
                                           "summary", "relevance")})
            e["funding"] = ai["funding"]
            if ai["categories"]:
                e["categories"] = ai["categories"]
            e["relevance"] = int(e["relevance"])
            e["priority"] = priority_of(e["relevance"], th)
            e["ai_scored"] = True
        e.pop("_text", None)

    db = load_db()
    merged = merge_items(db, entries)
    db["items"].extend(merged)
    db = archive_expired(db)
    db["updated_at"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    atomic_write(DATA / "opportunities.json",
                 json.dumps(db, ensure_ascii=False, indent=1))
    save_seen(seen)

    print(f"新增 {len(merged)} 条,活跃 {len(db['items'])} 条,已入库")
    notify(merged)
    return 0


if __name__ == "__main__":
    sys.exit(main())
