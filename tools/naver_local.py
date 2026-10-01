"""네이버 스마트스토어 6곳 — 이 PC에서 로그인한 브라우저로 수집 → 텔레그램.

2026-09-23부터 스마트스토어 카테고리 목록이 비로그인 요청을 전부 로그인 월로
보낸다(README "네이버 스마트스토어 6곳 제외" 참고). 클라우드에선 방법이 없어서
로그인 세션이 남는 Playwright 영구 프로필로 이 PC에서만 돈다.

    python tools/naver_local.py --login   # 처음 한 번 / 로그인 풀렸을 때. 로그인 후 창 닫기
    python tools/naver_local.py           # 작업 스케줄러가 2시간마다 실행

알림 중복은 seen.sqlite 가 아니라 따로 둔 naver_seen.json 으로 막는다 — 이 6곳은
CI 의 SCRAPERS 에서 빠졌으므로 seen.sqlite 와 경쟁할 일이 없다.
"""
from __future__ import annotations
import json
import random
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from playwright.sync_api import sync_playwright  # noqa: E402

from core.notify import send, TG_TOKEN, TG_CHAT  # noqa: E402
from scrapers.naver_smartstore import (  # noqa: E402
    VerdeTradeScraper, RyubeansScraper, ChBeanScraper, DoanSelectShopScraper,
    AyantuScraper, GimisaScraper,
)

HOME = Path.home() / ".green-coffee-radar"
PROFILE = HOME / "naver-profile"
STATE = HOME / "naver_seen.json"
STORES = [VerdeTradeScraper(), RyubeansScraper(), ChBeanScraper(),
          DoanSelectShopScraper(), AyantuScraper(), GimisaScraper()]


def _log(msg: str) -> None:
    print(f"{datetime.now():%Y-%m-%d %H:%M:%S} {msg}", flush=True)


def _alert(text: str) -> None:
    import httpx
    if not (TG_TOKEN and TG_CHAT):
        _log(f"[DRY-RUN] {text}")
        return
    httpx.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
               json={"chat_id": TG_CHAT, "text": text}, timeout=15)


def login() -> None:
    with sync_playwright() as p:
        # check() 가 화면 밖(-32000)에 띄운 위치를 프로필이 기억하므로 명시적으로 되돌린다
        ctx = p.chromium.launch_persistent_context(
            PROFILE, headless=False, locale="ko-KR",
            args=["--window-position=100,100", "--window-size=1000,800"])
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto("https://nid.naver.com/nidlogin.login?url=https%3A%2F%2Fsmartstore.naver.com%2Fverde_trade")
        print("브라우저에서 네이버 로그인 후 창을 닫으세요.")
        page.wait_for_event("close", timeout=0)
        ctx.close()


def check() -> int:
    state = json.loads(STATE.read_text()) if STATE.exists() else {"seen": [], "login_alerted": False}
    seen = set(state["seen"])
    first_run = not STATE.exists()
    with sync_playwright() as p:
        # 헤드리스는 로그인해도 429 로 막힌다. 일반 창을 화면 밖에 띄운다.
        ctx = p.chromium.launch_persistent_context(
            PROFILE, headless=False, locale="ko-KR",
            args=["--window-position=-32000,-32000"])
        page = ctx.new_page()
        for s in STORES:
            time.sleep(random.uniform(2, 5))
            try:
                # 하이드레이션 뒤 DOM 이 아니라 서버가 준 원본 HTML 을 파싱한다
                resp = page.goto(s._catalog_url(1).replace("size=20", "size=40"),
                                 wait_until="domcontentloaded", timeout=45000)
                if "nidlogin" in page.url:
                    _log("로그인 풀림")
                    if not state["login_alerted"]:
                        _alert("🔑 네이버 로그인이 풀렸습니다. PC에서 실행:\n"
                               "python tools/naver_local.py --login")
                        state["login_alerted"] = True
                    break
                state["login_alerted"] = False
                if resp.status >= 400:
                    _log(f"{s.name}: HTTP {resp.status}")
                    continue
                products = list(s._extract_products(resp.text()))
            except Exception:
                _log(f"{s.name} 실패:\n{traceback.format_exc()}")
                continue
            new = [x for x in products if x.sku not in seen]
            _log(f"{s.name}: {len(products)} total, {len(new)} new")
            for x in new:
                seen.add(x.sku)
                if not first_run:  # 첫 실행은 기준점만 잡고 조용히
                    send(x)
        ctx.close()
    HOME.mkdir(exist_ok=True)
    STATE.write_text(json.dumps({**state, "seen": sorted(seen)}))
    return 0


if __name__ == "__main__":
    sys.exit(login() if "--login" in sys.argv else check())
