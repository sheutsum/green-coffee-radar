"""영카트/그누보드(youngcart) 기반 쇼핑몰 어댑터.

카탈로그: /shop/list.php?ca_id=<카테고리>&page=N
상품 링크는 스킨마다 다르다 —
  세웅지씨:  /shop/item.php?it_id=<숫자>
  블레스빈:  /shop/<상품코드>?ca_id=...   (rewrite 사용)
그래서 상품 id를 뽑는 정규식만 사이트별로 갈아끼운다.

가격은 스킨에 따라 "48,000"처럼 '원' 없이 찍히기도 해서, 원/₩ 매칭이 실패하면
콤마 구분 숫자를 그대로 집어온다.
"""
from __future__ import annotations
import re
from typing import Iterator, Optional

import httpx
from selectolax.parser import HTMLParser

from core.models import Product
from scrapers.base import (
    Scraper, _HEADERS, parse_price_krw, parse_unit_g,
    guess_origin, guess_process, polite_sleep, get_with_retry,
)

_BARE_PRICE_RE = re.compile(r"\d{1,3}(?:,\d{3})+")


def _price_from(text: str) -> Optional[int]:
    price = parse_price_krw(text)
    if price is not None:
        return price
    m = _BARE_PRICE_RE.search(text)
    return int(m.group(0).replace(",", "")) if m else None


class YoungcartScraper(Scraper):
    # --- subclass config ---
    name: str
    supplier_name: str
    base: str
    ca_ids: tuple[str, ...] = ()
    item_href_re: str = r"item\.php\?it_id=([\w\-]+)"
    item_selector: str = "li"
    name_selector: str = ".item_tit, .sct_txt a, strong"
    # ------------------------
    max_pages: int = 10
    timeout: int = 20
    sold_out_markers: tuple[str, ...] = ("품절", "SOLD OUT", "SOLDOUT")

    def _catalog_url(self, ca_id: str, page: int) -> str:
        return f"{self.base}/shop/list.php?ca_id={ca_id}&page={page}"

    def fetch(self) -> list[Product]:
        out: list[Product] = []
        seen: set[str] = set()
        rx = re.compile(self.item_href_re)
        with httpx.Client(headers=_HEADERS, timeout=self.timeout,
                          follow_redirects=True) as c:
            for ca_id in self.ca_ids:
                cat_seen: set[str] = set()
                for page in range(1, self.max_pages + 1):
                    if out:
                        polite_sleep()
                    r = get_with_retry(c, self._catalog_url(ca_id, page))
                    r.raise_for_status()
                    items = list(self._parse(r.text, rx))
                    new = [p for p in items if p.sku not in cat_seen]
                    if not new:
                        break
                    for p in new:
                        cat_seen.add(p.sku)
                        if p.sku not in seen:
                            seen.add(p.sku)
                            out.append(p)
        return out

    def _parse(self, html: str, rx: re.Pattern) -> Iterator[Product]:
        tree = HTMLParser(html)
        for node in tree.css(self.item_selector):
            item_id = url = None
            for a in node.css("a[href]"):
                m = rx.search(a.attributes.get("href") or "")
                if m:
                    item_id = m.group(1)
                    href = a.attributes.get("href") or ""
                    url = href if href.startswith("http") else self.base + href
                    break
            if not item_id:
                continue

            name = ""
            for sel in self.name_selector.split(", "):
                el = node.css_first(sel)
                if el and el.text(strip=True):
                    name = el.text(strip=True)
                    break
            if not name or len(name) < 4:
                continue

            text = node.text()
            yield Product(
                sku=f"{self.name}:{item_id}",
                supplier=self.supplier_name,
                name=name,
                origin=guess_origin(name),
                process=guess_process(name),
                price_krw=_price_from(text),
                unit_g=parse_unit_g(name, default=1000),
                url=url,
                in_stock=not any(mk in text for mk in self.sold_out_markers),
            )


# --- concrete stores -------------------------------------------------------

class SewoongScraper(YoungcartScraper):
    name = "sewoong"
    supplier_name = "세웅지씨"
    base = "https://www.sewoonggc.com"
    # 10 아프리카 / 20 아메리카 / 30 아시아 / 40 마이크로랏 / 50 게이샤
    # 60 디카페인 / b0 대회 후원 생두
    ca_ids = ("10", "20", "30", "40", "50", "60", "b0")
    item_selector = "ul.itemlist_01 > li, li"
    name_selector = ".item_tit, .sct_txt a"


class BlessBeanScraper(YoungcartScraper):
    name = "blessbean"
    supplier_name = "블레스빈"
    base = "https://blessbean.co.kr"
    # 2010 Africa / 2020 Latin America / 2030 Asia & Etc / 2040 Decaffeinated
    ca_ids = ("2010", "2020", "2030", "2040")
    # rewrite 링크: /shop/<상품코드>?ca_id=...  (list.php 같은 .php 경로는 제외)
    item_href_re = r"/shop/([A-Za-z0-9][\w\-]*)\?ca_id="
    item_selector = ".item-list"
    name_selector = ".item-content strong, strong"
