"""关键词矩阵初筛 + LLM 结构化打分。"""
import json
import os
import re
import sys

import requests

CATEGORIES = ["residency", "grant", "open_call", "publishing",
              "digital_media", "research", "spatial"]
TH = "thresholds"

# 月份映射供 deadline 解析使用(英文全称 + 常见缩写)
MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7,
    "aug": 8, "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12,
}

_ISO = re.compile(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b")
_SLASH = re.compile(r"\b(\d{4})/(\d{1,2})/(\d{1,2})\b")
_MDY = re.compile(r"\b([A-Za-z]+)\.?\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})\b")
_DMY = re.compile(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]+)\.?,?\s+(\d{4})\b")


def _iso(y: int, m: int, d: int) -> str | None:
    if not (1 <= m <= 12 and 1 <= d <= 31):
        return None
    return f"{y:04d}-{m:02d}-{d:02d}"


def parse_deadline(text: str) -> str | None:
    t = text[:3000]
    for pat in (_ISO, _SLASH):
        m = pat.search(t)
        if m:
            out = _iso(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            if out:
                return out
    for pat in (_MDY, _DMY):
        m = pat.search(t)
        if m:
            groups = [g.lower() for g in m.groups()]
            if pat is _MDY:
                mon, day, year = groups
            else:
                day, mon, year = groups
            if mon in MONTHS:
                out = _iso(int(year), MONTHS[mon], int(day))
                if out:
                    return out
    return None


def is_blocked(text: str, kw: dict) -> bool:
    return any(w.lower() in text.lower() for w in kw["block_words"])


def has_trigger(text: str, kw: dict) -> bool:
    return any(w.lower() in text.lower() for w in kw["trigger_words"])


def keyword_stage(text: str, kw: dict):
    """返回加权重(funding+media);命中 block 或未命中 trigger 返回 None。"""
    if is_blocked(text, kw) or not has_trigger(text, kw):
        return None
    t = text.lower()
    score = 0
    for word, weight in kw["funding_words"].items():
        if word in t:
            score += weight
    for word, weight in kw["media_words"].items():
        if word in t:
            score += weight
    return score


def keyword_categories(text: str) -> list:
    t = text.lower()
    cats = []
    if "residenc" in t:
        cats.append("residency")
    if "grant" in t or "funding" in t or "fellowship" in t:
        cats.append("grant")
    if "open call" in t or "call for" in t:
        cats.append("open_call")
    if any(w in t for w in ("zine", "publishing", "artist book", "版画", "独立出版")):
        cats.append("publishing")
    if any(w in t for w in ("media", "digital", "媒体", "数字")):
        cats.append("digital_media")
    if "research" in t or "研究" in t:
        cats.append("research")
    if any(w in t for w in ("public space", "site-specific", "spatial", "空间", "田野")):
        cats.append("spatial")
    return cats[:4] or ["open_call"]


LLM_PROMPT = """分析以下艺术机会信息,只返回一个 JSON 对象,不要任何其他文字。
格式:
{"organization": "主办机构或 null", "country": "国家或 null", "deadline": "YYYY-MM-DD 或 null",
 "summary": "不超过200字的中文摘要",
 "relevance": 0到100的整数,
 "funding": {"fully_funded": true/false/null, "stipend": true/false/null, "accommodation": true/false/null, "travel": true/false/null},
 "categories": ["从以下选0到4个: residency, grant, open_call, publishing, digital_media, research, spatial"]}

relevance 评分标准:是真实的驻留/基金/征集机会 40 分基础;全额资助 +20;匹配独立出版/媒体考古/数字人文/开源硬件/空间实践/策展/研究方向 每个 +15;接受国际艺术家 +10;截止日期明确 +5。

机会信息:
"""


def llm_stage(text: str) -> dict | None:
    """OpenAI 兼容 API 结构化打分;失败或未配置返回 None(由调用方降级)。"""
    api_key = os.environ.get("AI_API_KEY")
    if not api_key:
        return None
    base = os.environ.get("AI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    model = os.environ.get("AI_MODEL", "gpt-4o-mini")
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": LLM_PROMPT + text[:6000]}],
        "response_format": {"type": "json_object"},
        "temperature": 0.1,
    }
    headers = {"Authorization": f"Bearer {api_key}"}
    for attempt in (1, 2):
        try:
            r = requests.post(f"{base}/chat/completions", json=payload,
                             headers=headers, timeout=60)
            r.raise_for_status()
            content = r.json()["choices"][0]["message"]["content"].strip()
            if content.startswith("```"):
                content = re.sub(r"^```(json)?|```$", "", content, flags=re.M).strip()
            data = json.loads(content)
            if not isinstance(data, dict):
                raise ValueError("LLM 返回的不是 JSON 对象")
            funding = data.get("funding") or {}
            return {
                "organization": data.get("organization"),
                "country": data.get("country"),
                "deadline": data.get("deadline"),
                "summary": str(data.get("summary") or "")[:200],
                "relevance": max(0, min(100, int(data.get("relevance") or 0))),
                "funding": {k: funding.get(k) for k in
                            ("fully_funded", "stipend", "accommodation", "travel")},
                "categories": [c for c in data.get("categories", []) if c in CATEGORIES][:4],
            }
        except Exception as exc:
            if attempt == 2:
                print(f"[analyzer] LLM 打分失败,降级为关键词结果: {exc}", file=sys.stderr)
    return None
