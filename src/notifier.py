"""Telegram + Resend 邮件通知。"""
import html
import os
import sys

import requests

TG_MAX = 4000


def _escape(s: str) -> str:
    return html.escape(str(s or ""))


def _telegram(text: str) -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id or not text:
        return
    proxy = os.environ.get("TELEGRAM_PROXY")
    proxies = {"http": proxy, "https": proxy} if proxy else None
    try:
        requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
            proxies=proxies, timeout=20,
        ).raise_for_status()
    except Exception as exc:
        print(f"[notifier] Telegram 发送失败: {exc}", file=sys.stderr)


def _email(high_items: list) -> None:
    api_key = os.environ.get("EMAIL_API_KEY")
    to = os.environ.get("EMAIL_TO")
    if not api_key or not to or not high_items:
        return
    lines = []
    for i in high_items:
        lines.append(f"- {i['title']} [{i['priority']}] 截止 {i.get('deadline') or '未知'}")
        lines.append(f"  {i['url']}")
    try:
        requests.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "from": os.environ.get("EMAIL_FROM", "onboarding@resend.dev"),
                "to": [to],
                "subject": f"🎯 艺术机会雷达:{len(high_items)} 个高优机会",
                "text": "\n".join(lines),
            },
            timeout=20,
        ).raise_for_status()
    except Exception as exc:
        print(f"[notifier] 邮件发送失败: {exc}", file=sys.stderr)


def notify(new_items: list) -> None:
    interesting = [i for i in new_items if i["priority"] in ("HIGH", "MAYBE")]
    if interesting:
        lines = ["🎯 <b>雷达更新</b>", ""]
        for i in interesting[:10]:
            dl = f" | 截止 {_escape(i.get('deadline'))}" if i.get("deadline") else ""
            lines.append(f"● <b>{_escape(i['title'])}</b>{dl} [{i['priority']}]")
            lines.append(_escape(i["url"]))
            lines.append("")
        if len(interesting) > 10:
            lines.append(f"…及其他 {len(interesting) - 10} 条,详见雷达页")
        _telegram("\n".join(lines)[:TG_MAX])
    _email([i for i in new_items if i["priority"] == "HIGH"])
