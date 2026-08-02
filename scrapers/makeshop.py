"""메이크샵(MakeShop) 기반 쇼핑몰 어댑터.

카탈로그: /shop/shopbrand.html?xcode=<대분류>&type=X&page=N
상품:     /shop/shopdetail.html?branduid=<id>
상품 카드는 `li.item_list` + `.prdname` / `.prdprice .price` 구조.
"""
from __future__ import annotations
import re
from typing import Iterator

import httpx
from selectolax.parser import HTMLParser

from core.models import Product
from scrapers.base import (
    Scraper, _HEADERS, parse_price_krw, parse_unit_g,
    guess_origin, guess_process, polite_sleep, get_with_retry,
)

_BRANDUID_RE = re.compile(r"branduid=(\d+)")


class MakeshopScraper(Scraper):
    # --- subclass config ---
    name: str
    supplier_name: str
    base: str
    xcodes: tuple[str, ...] = ()
    # ------------------------
    max_pages: int = 10
    timeout: int = 20
    sold_out_markers: tuple[str, ...] = ("품절", "SOLD OUT", "SOLDOUT")

    def _catalog_url(self, xcode: str, page: int) -> str:
        return (f"{self.base}/shop/shopbrand.html?xcode={xcode}"
                f"&type=X&page={page}")

    def fetch(self) -> list[Product]:
        out: list[Product] = []
        seen: set[str] = set()
        with httpx.Client(headers=_HEADERS, timeout=self.timeout,
                          follow_redirects=True) as c:
            for xcode in self.xcodes:
                cat_seen: set[str] = set()
                for page in range(1, self.max_pages + 1):
                    if out:
                        polite_sleep()
                    r = get_with_retry(c, self._catalog_url(xcode, page))
                    r.raise_for_status()
                    items = list(self._parse(r.text))
                    new = [p for p in items if p.sku not in cat_seen]
                    if not new:
                        break
                    for p in new:
                        cat_seen.add(p.sku)
                        if p.sku not in seen:
                            seen.add(p.sku)
                            out.append(p)
        return out

    def _parse(self, html: str) -> Iterator[Product]:
        tree = HTMLParser(html)
        nodes = tree.css("li.item_list") or tree.css("li[class*='item_list']")
        for node in nodes:
            link = node.css_first("a[href*='shopdetail.html']")
            if not link:
                continue
            href = link.attributes.get("href") or ""
            m = _BRANDUID_RE.search(href)
            if not m:
                continue
            uid = m.group(1)

            el = node.css_first(".prdname")
            name = el.text(strip=True) if el else ""
            if not name:
                continue

            money = node.css_first(".prdprice")
            price = parse_price_krw(money.text() + "원") if money else None

            text = node.text()
            in_stock = not any(mk in text for mk in self.sold_out_markers)

            yield Product(
                sku=f"{self.name}:{uid}",
                supplier=self.supplier_name,
                name=name,
                origin=guess_origin(name),
                process=guess_process(name),
                price_krw=price,
                unit_g=parse_unit_g(name, default=1000),
                url=f"{self.base}/shop/shopdetail.html?branduid={uid}",
                in_stock=in_stock,
            )


class AsianBeanScraper(MakeshopScraper):
    name = "asianbean"
    supplier_name = "에이션빈"
    base = "https://www.asianbean.co.kr"
    # 007 아프리카 / 009 남미 / 010 중미 / 008 아시아 / 011 디카페인
    # 014 할인생두 / 015 대회 협찬 생두
    xcodes = ("007", "009", "010", "008", "011", "014", "015")
