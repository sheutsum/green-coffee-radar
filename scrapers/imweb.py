"""아임웹(imweb) 기반 쇼핑몰 어댑터.

카탈로그: /<MENU>/?page=N&sort=recent
상품:     /<MENU>/?idx=<id>
상품 카드 `div._shop_item` 의 `data-product-properties` 속성에 idx, name, price 가
JSON 으로 박혀 있어 텍스트 파싱이 필요 없다. 품절은 카드 안의 `img.sold_out` 배지.
"""
from __future__ import annotations
import json
from typing import Iterator

import httpx
from selectolax.lexbor import LexborHTMLParser as HTMLParser

from core.models import Product
from scrapers.base import (
    Scraper, _HEADERS, parse_unit_g, guess_origin, guess_process,
    polite_sleep, get_with_retry,
)


class ImwebScraper(Scraper):
    # --- subclass config ---
    name: str
    supplier_name: str
    base: str
    menu: str
    # ------------------------
    max_pages: int = 10
    timeout: int = 20

    def fetch(self) -> list[Product]:
        out: list[Product] = []
        seen: set[str] = set()
        with httpx.Client(headers=_HEADERS, timeout=self.timeout,
                          follow_redirects=True) as c:
            for page in range(1, self.max_pages + 1):
                if out:
                    polite_sleep()
                r = get_with_retry(
                    c, f"{self.base}/{self.menu}/?page={page}&sort=recent")
                r.raise_for_status()
                # 마지막 페이지를 넘기면 아임웹은 마지막 페이지를 다시 준다 → 새 SKU 없으면 끝
                new = [p for p in self._parse(r.text) if p.sku not in seen]
                if not new:
                    break
                for p in new:
                    seen.add(p.sku)
                    out.append(p)
        return out

    def _parse(self, html: str) -> Iterator[Product]:
        for node in HTMLParser(html).css("div._shop_item[data-product-properties]"):
            try:
                d = json.loads(node.attributes["data-product-properties"])
            except (ValueError, TypeError):
                continue
            idx, name = d.get("idx"), (d.get("name") or "").strip()
            if not idx or not name:
                continue
            price = d.get("price")
            yield Product(
                sku=f"{self.name}:{idx}",
                supplier=self.supplier_name,
                name=name,
                origin=guess_origin(name),
                process=guess_process(name),
                price_krw=int(price) if price else None,
                unit_g=parse_unit_g(name, default=1000),
                url=f"{self.base}/{self.menu}/?idx={idx}",
                in_stock=node.css_first("img.sold_out") is None,
            )


class DoanScraper(ImwebScraper):
    # 2026-11 네이버 스마트스토어(doanselectshop, 현재 STOP)에서 자사몰로 이전.
    # SKU 접두사 "doan" 은 그대로 쓰되 id 는 아임웹 idx 라 옛 네이버 SKU 와 겹치지 않는다.
    name = "doan"
    supplier_name = "도안 셀렉트 샵"
    base = "https://www.doancompany.kr"
    menu = "GREEN"
