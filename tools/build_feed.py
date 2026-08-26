"""Snapshot the current catalog into web/feed.json — the data source for the
iPhone PWA (web/).

Read-only with respect to seen.sqlite: it only reads first_seen so the app can
flag recent arrivals; the live notifier (run.py) remains the only writer.

Two entry points:
  * standalone   `python tools/build_feed.py`  → fetches every scraper, writes feed
  * from run.py  `write_feed(products, errors)` → reuses run.py's single fetch
"""
from __future__ import annotations

import json
import sqlite3
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.models import Product  # noqa: E402

DB_PATH = ROOT / "seen.sqlite"
OUT_PATH = ROOT / "web" / "feed.json"


def load_first_seen(db_path: Path = DB_PATH) -> dict[str, str]:
    if not db_path.exists():
        return {}
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute("SELECT sku, first_seen FROM seen").fetchall()
    except sqlite3.OperationalError:
        return {}
    finally:
        conn.close()
    return {sku: first_seen for sku, first_seen in rows}


def build_payload(products: list[Product], errors: list[str]) -> dict:
    first_seen = load_first_seen()
    out: list[dict] = []
    for p in products:
        d = p.to_dict()
        d["price_per_kg"] = p.price_per_kg
        d["first_seen"] = first_seen.get(p.sku)
        out.append(d)

    out.sort(
        key=lambda d: (d.get("first_seen") or "0000", d.get("name") or ""),
        reverse=True,
    )

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "count": len(out),
        "suppliers": sorted({d["supplier"] for d in out}),
        "errors": errors,
        "products": out,
    }


def carry_forward(payload: dict, errors: list[str], out_path: Path) -> dict:
    """실패한 스크레이퍼의 상품을 직전 feed 에서 그대로 물려온다.

    403 한 번에 그 공급사 상품 100여 개(카탈로그의 6%)가 피드에서 통째로
    사라졌다가 다음 실행에 돌아오는 걸 막는다. 어떤 곳이 갱신 안 된 상태인지는
    payload["errors"] 가 그대로 들고 있다.

    ponytail: 영구 폐업/개편이면 옛 상품이 계속 남는다 — errors 가 매번 울리니
    사람이 보고 지우면 된다. 자동 만료가 필요해지면 first_seen 대신 last_seen
    기준으로 N일 지난 건 버리는 식으로 올리면 된다.
    """
    if not errors or not out_path.exists():
        return payload
    try:
        prev = json.loads(out_path.read_text(encoding="utf-8"))["products"]
    except (ValueError, KeyError, OSError):
        return payload

    failed = set(errors)
    fresh = {d["sku"] for d in payload["products"]}
    carried = [d for d in prev
               if d.get("sku", "").split(":", 1)[0] in failed and d["sku"] not in fresh]
    if not carried:
        return payload

    payload["products"].extend(carried)
    payload["products"].sort(
        key=lambda d: (d.get("first_seen") or "0000", d.get("name") or ""),
        reverse=True,
    )
    payload["count"] = len(payload["products"])
    payload["suppliers"] = sorted({d["supplier"] for d in payload["products"]})
    return payload


def write_feed(products: list[Product], errors: list[str] | None = None,
               out_path: Path = OUT_PATH) -> Path:
    errors = errors or []
    payload = carry_forward(build_payload(products, errors), errors, out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        # 상품 1600여 개 × 30분마다 커밋 + 앱이 매번 내려받는 파일이라 압축해서 쓴다
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    return out_path


def fetch_all() -> tuple[list[Product], list[str]]:
    from run import SCRAPERS  # imported lazily to avoid cycle when run.py imports us

    products: list[Product] = []
    errors: list[str] = []
    for scraper in SCRAPERS:
        try:
            fetched = scraper.fetch()
        except Exception:
            errors.append(scraper.name)
            print(f"!! {scraper.name} failed:", file=sys.stderr)
            traceback.print_exc()
            continue
        print(f"{scraper.name}: {len(fetched)} products")
        products.extend(fetched)
    return products, errors


def main() -> int:
    products, errors = fetch_all()
    path = write_feed(products, errors)
    print(f"\nWrote {len(products)} products -> {path}")
    if errors:
        print(f"(scrapers that failed: {', '.join(errors)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
