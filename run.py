from __future__ import annotations
import os
import sys
import traceback
from pathlib import Path

# Allow running from project root
sys.path.insert(0, str(Path(__file__).parent))

from core.state import connect, diff_and_record
from core.notify import send, DRY_RUN
from tools.build_feed import write_feed
from scrapers.momos import MomosScraper
from scrapers.coffeemeup import CoffeeMeUpScraper
from scrapers.coffeelibre import CoffeeLibreScraper
from scrapers.cobeans import CobeansScraper, AlmacieloScraper
from scrapers.blackroad import BlackRoadScraper
from scrapers.naver_smartstore import (
    VerdeTradeScraper, RyubeansScraper, ChBeanScraper, DoanSelectShopScraper,
    AyantuScraper, GimisaScraper,
)
from scrapers.sixshop import (
    CafeNogalesScraper, CompassCoffeeScraper, KoffeeRouteScraper,
    HankookCoffeeTradingScraper, UnicoCoffeeScraper, EthicoCoffeeScraper,
)
from scrapers.cafe24_shops import (
    SopexScraper, RnCScraper, NamusairoScraper, CoffeeSpellScraper,
)
from scrapers.godomall import (
    GscScraper, MiCoffeeScraper, WbeansScraper,
)
from scrapers.makeshop import AsianBeanScraper
from scrapers.youngcart import SewoongScraper, BlessBeanScraper
from scrapers.shopify import FalconMicroScraper

SCRAPERS = [
    MomosScraper(),
    CoffeeMeUpScraper(),
    CoffeeLibreScraper(),
    CobeansScraper(),
    BlackRoadScraper(),
    VerdeTradeScraper(),
    RyubeansScraper(),
    ChBeanScraper(),
    DoanSelectShopScraper(),
    CafeNogalesScraper(),
    CompassCoffeeScraper(),
    # --- 2026-08 추가 ---
    SopexScraper(),
    RnCScraper(),
    NamusairoScraper(),
    CoffeeSpellScraper(),
    GscScraper(),
    MiCoffeeScraper(),
    WbeansScraper(),
    # RoyalCoffeeScraper() — 2026-08-02부터 Actions 러너에서 호스트 전체가 403.
    # 매 실행 errors 에 쌓여서 진짜 고장 신호를 묻어버리므로 목록에서 뺐다.
    # 클래스는 그대로 두니 자택에서 `python tools/check_scrapers.py royal` 로
    # 차단이 풀렸는지 확인 가능. 자세한 건 README "클라우드에서만 막히는 곳".
    AsianBeanScraper(),
    AlmacieloScraper(),
    SewoongScraper(),
    BlessBeanScraper(),
    KoffeeRouteScraper(),
    HankookCoffeeTradingScraper(),
    UnicoCoffeeScraper(),
    EthicoCoffeeScraper(),
    FalconMicroScraper(),
    AyantuScraper(),
    GimisaScraper(),
]

DB_PATH = os.environ.get("RADAR_DB", "seen.sqlite")


def main() -> int:
    print(f"Mode: {'DRY-RUN (no Telegram)' if DRY_RUN else 'LIVE'}")
    print(f"DB:   {DB_PATH}")

    conn = connect(DB_PATH)
    total_new = 0
    all_products = []
    errors: list[str] = []

    for scraper in SCRAPERS:
        try:
            products = scraper.fetch()
        except Exception:
            print(f"\n!! {scraper.name} fetch failed:")
            traceback.print_exc()
            errors.append(scraper.name)
            continue

        if not products:
            # 예외 없이 0개 = 사이트 개편으로 셀렉터가 헛도는 경우. 조용히
            # 피드에서 사라지는 게 제일 나쁘므로 에러로 표시한다.
            print(f"{scraper.name}: 0 products — layout changed?")
            errors.append(scraper.name)
            continue

        new = diff_and_record(conn, products)
        print(f"{scraper.name}: {len(products):3d} total, {len(new):3d} new")
        total_new += len(new)
        all_products.extend(products)

        for p in new:
            send(p)

    # Snapshot the full catalog for the PWA. Done after diff_and_record so
    # first_seen timestamps for brand-new SKUs are already in the DB.
    feed_path = write_feed(all_products, errors)
    print(f"\nDone. {total_new} new product(s) announced. "
          f"Feed: {len(all_products)} products -> {feed_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
