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
from scrapers.cobeans import CobeansScraper
from scrapers.blackroad import BlackRoadScraper
from scrapers.naver_smartstore import (
    VerdeTradeScraper, RyubeansScraper, ChBeanScraper, DoanSelectShopScraper,
)
from scrapers.sixshop import CafeNogalesScraper, CompassCoffeeScraper

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
