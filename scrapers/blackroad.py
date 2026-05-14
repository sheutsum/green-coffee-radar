"""블랙로드커피 — imweb 플랫폼.
Catalog: /37  (37 = 생두 카테고리)
Product: /37/?idx=<product_id>
페이지네이션: ?page=N (imweb 표준).
상품명 텍스트에 가격·재고 마커가 함께 들어 있어서 후처리 필요:
  예) "[생두] 파나마 블랙문 게이샤 워시드 #26 412,000원 BESTSOLDOUT"
"""
from __future__ import annotations
import re
import httpx
from selectolax.parser import HTMLParser

from core.models import Product
from scrapers.base import (
    Scraper, _HEADERS, parse_price_krw, parse_unit_g,
    guess_origin, guess_process,
)

_IDX_RE = re.compile(r"[?&]idx=(\d+)")
_PRICE_TAIL_RE = re.compile(r"\s*[\d,]+원.*$")
_TRAILING_MARKERS_RE = re.compile(r"\s*(BESTSOLDOUT|SOLDOUT|BEST|NEW)\s*$", re.IGNORECASE)


def _clean_name(raw: str) -> str:
    """Strip trailing price + BEST/SOLDOUT markers from imweb product text."""
    name = _PRICE_TAIL_RE.sub("", raw).strip()
    name = _TRAILING_MARKERS_RE.sub("", name).strip()
    return name


class BlackRoadScraper(Scraper):
    name = "blackroad"
    supplier_name = "블랙로드커피"
    base = "https://blackroad.kr"
    catalog_path = "/37"
    max_pages = 5

    def fetch(self) -> list[Product]:
        out: list[Product] = []
        seen: set[str] = set()
        with httpx.Client(headers=_HEADERS, timeout=20, follow_redirects=True) as c:
            for page in range(1, self.max_pages + 1):
                url = self.base + self.catalog_path
                if page > 1:
                    url += f"?page={page}"
                r = c.get(url)
                r.raise_for_status()
                items = list(self._parse(r.text))
                new = [p for p in items if p.sku not in seen]
                if not new:
                    break
                for p in new:
                    seen.add(p.sku)
                    out.append(p)
        return out

    def _parse(self, html: str):
        tree = HTMLParser(html)
        seen_idx: set[str] = set()

        for a in tree.css("a[href*='?idx=']"):
            href = a.attributes.get("href", "") or ""
            m = _IDX_RE.search(href)
            if not m:
                continue
            raw_text = a.text(strip=True)
            if not raw_text or len(raw_text) < 5:
                continue
            idx = m.group(1)
            if idx in seen_idx:
                continue
            seen_idx.add(idx)

            # blackroad는 a 텍스트 안에 가격·재고가 다 박혀 있음
            price = parse_price_krw(raw_text)
            in_stock = "SOLDOUT" not in raw_text.upper()
            name = _clean_name(raw_text)

            # URL 정규화
            if href.startswith("http"):
                full_url = href
            elif href.startswith("/"):
                full_url = self.base + href
            elif href.startswith("?"):
                full_url = f"{self.base}{self.catalog_path}{href}"
            else:
                full_url = f"{self.base}/{href}"

            yield Product(
                sku=f"{self.name}:{idx}",
                supplier=self.supplier_name,
                name=name,
                origin=guess_origin(name),
                process=guess_process(name),
                price_krw=price,
                unit_g=parse_unit_g(name, default=1000),
                url=full_url,
                in_stock=in_stock,
            )
