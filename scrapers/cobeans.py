"""위사(Wisa) 솔루션 쇼핑몰 — 코빈즈커피 / 알마시엘로.
Catalog: /shop/big_section.php?cno1=<category>&sort=1&page=N
Product: /shop/detail.php?pno=<HEX>
코빈즈는 cno1=1037 (신규입고/New Arrival) — 알림 봇 목적에 가장 적합.
"""
from __future__ import annotations
import re
import httpx
from selectolax.parser import HTMLParser

from core.models import Product
from scrapers.base import (
    Scraper, _HEADERS, parse_price_krw, parse_unit_g,
    guess_origin, guess_process, polite_sleep, get_with_retry,
)

_PNO_RE = re.compile(r"[?&]pno=([A-F0-9]+)")


class WisaScraper(Scraper):
    # --- subclass config ---
    name: str
    supplier_name: str
    base: str
    catalog_url_template: str   # must include {base} and {page}
    # ------------------------
    max_pages = 5

    def fetch(self) -> list[Product]:
        out: list[Product] = []
        seen: set[str] = set()
        with httpx.Client(headers=_HEADERS, timeout=20, follow_redirects=True) as c:
            for page in range(1, self.max_pages + 1):
                if page > 1:
                    polite_sleep()
                url = self.catalog_url_template.format(base=self.base, page=page)
                r = get_with_retry(c, url)
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
        seen_pno: set[str] = set()

        # detail.php?pno=... 링크 중 텍스트(상품명)를 가진 것만 골라낸다.
        for a in tree.css("a[href*='/shop/detail.php']"):
            href = a.attributes.get("href", "") or ""
            m = _PNO_RE.search(href)
            if not m:
                continue
            name = a.text(strip=True)
            # 짧은 텍스트(이미지/장바구니 링크)는 스킵
            if not name or len(name) < 4:
                continue
            pno = m.group(1)
            if pno in seen_pno:
                continue
            seen_pno.add(pno)

            # 가장 가까운 li/div 컨테이너로 올라가서 가격·재고 텍스트를 얻는다
            container = a.parent
            for _ in range(6):
                if container is None or container.tag == "li":
                    break
                container = container.parent
            ctx_text = container.text() if container else name

            price = parse_price_krw(ctx_text)
            in_stock = "Sold out" not in ctx_text and "품절" not in ctx_text

            full_url = href if href.startswith("http") else self.base + href

            yield Product(
                sku=f"{self.name}:{pno}",
                supplier=self.supplier_name,
                name=name,
                origin=guess_origin(name),
                process=guess_process(name),
                price_krw=price,
                unit_g=parse_unit_g(name, default=1000),
                url=full_url,
                in_stock=in_stock,
            )


class CobeansScraper(WisaScraper):
    name = "cobeans"
    supplier_name = "코빈즈커피"
    base = "https://www.cobeans.com"
    # cno1=1037 = New Arrival. 일반 생두 카테고리 전체를 보고 싶으면
    # 여러 cno1을 돌리도록 확장 가능 (1015 에티오피아, 1022 아프리카, 1023 라틴, 1024 아시아 등)
    catalog_url_template = "{base}/shop/big_section.php?cno1=1037&sort=1&page={page}"


class AlmacieloScraper(WisaScraper):
    name = "almacielo"
    supplier_name = "알마시엘로"
    base = "https://www.almacielo.com"
    catalog_url_template = "{base}/shop/big_section.php?cno1=1070&page={page}"
    max_pages = 10
