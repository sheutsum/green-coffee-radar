from __future__ import annotations
import os
import time
import httpx

from core.models import Product

TG_TOKEN = os.environ.get("TG_TOKEN", "")
TG_CHAT = os.environ.get("TG_CHAT", "")
DRY_RUN = not (TG_TOKEN and TG_CHAT)


def _escape_md(s: str) -> str:
    """Telegram MarkdownV2 escaping (kept minimal — we use plain Markdown)."""
    return s.replace("[", "(").replace("]", ")")


def format_message(p: Product) -> str:
    parts = [f"🆕 *{_escape_md(p.supplier)}*", _escape_md(p.name)]
    meta = " · ".join(filter(None, [p.origin, p.process]))
    if meta:
        parts.append(meta)
    if p.price_krw is not None:
        per_kg = f" (₩{p.price_per_kg:,}/kg)" if p.price_per_kg else ""
        parts.append(f"₩{p.price_krw:,}{per_kg}")
    if not p.in_stock:
        parts.append("⚠️ 품절")
    parts.append(f"[상품 보기]({p.url})")
    return "\n".join(parts)


def send(p: Product) -> None:
    msg = format_message(p)
    if DRY_RUN:
        print("[DRY-RUN]\n" + msg + "\n")
        return
    try:
        httpx.post(
            f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
            json={
                "chat_id": TG_CHAT,
                "text": msg,
                "parse_mode": "Markdown",
                "disable_web_page_preview": False,
            },
            timeout=15,
        ).raise_for_status()
    except Exception as e:
        print(f"telegram failed for {p.sku}: {e}")
    # gentle pacing to stay well under Telegram's 30 msg/sec global limit
    time.sleep(0.4)
