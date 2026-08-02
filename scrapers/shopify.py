"""Shopify 기반 쇼핑몰 어댑터.

Shopify는 컬렉션 JSON을 그대로 열어준다:
    /collections/<handle>/products.json?limit=250&page=N
가격은 variants[0].price(문자열, 예: "35000.00"), 재고는 variants[*].available.
"""
from __future__ import annotations
from typing import Iterator

from curl_cffi import requests as cc_requests

from core.models import Product
from scrapers.base import (
    Scraper, parse_unit_g, guess_origin, guess_process, polite_sleep,
    cc_get_with_retry,
)


class ShopifyScraper(Scraper):
    # --- subclass config ---
    name: str
    supplier_name: str
    base: str
    collection: str = "all"     # /collections/<collection>/products.json
    # ------------------------
    page_size: int = 250
    max_pages: int = 5
    timeout: int = 20

    def fetch(self) -> list[Product]:
        out: list[Product] = []
        seen: set[str] = set()
        url = f"{self.base}/collections/{self.collection}/products.json"
        with cc_requests.Session() as c:
            for page in range(1, self.max_pages + 1):
                if page > 1:
                    polite_sleep()
                # Shopify는 UA만 바꿔서는 안 되고 TLS 지문까지 본다. 그래도
                # 공용 IP(Actions runner)에서는 429 local_rate_limited가 나서
                # 백오프 재시도가 필요하다.
                r = cc_get_with_retry(c, url, timeout=self.timeout,
                                      params={"limit": self.page_size,
                                              "page": page})
                if r.status_code >= 400:
                    raise RuntimeError(
                        f"{self.name}: HTTP {r.status_code} from {url}"
                    )
                items = list(self._parse(r.json()))
                new = [p for p in items if p.sku not in seen]
                if not new:
                    break
                for p in new:
                    seen.add(p.sku)
                    out.append(p)
        return out

    def _parse(self, data) -> Iterator[Product]:
        for d in (data or {}).get("products", []):
            pid = str(d.get("id") or "")
            name = (d.get("title") or "").strip()
            if not pid or not name:
                continue
            variants = d.get("variants") or []
            price = None
            for v in variants:
                raw = str(v.get("price") or "").replace(",", "")
                if raw:
                    try:
                        price = int(float(raw))
                    except ValueError:
                        price = None
                    break
            in_stock = any(v.get("available") for v in variants) if variants else True
            # 무게는 variant 이름(예: "5kg")이 상품명보다 정확한 경우가 많다
            unit = parse_unit_g(
                (variants[0].get("title") if variants else "") or "", default=None
            ) or parse_unit_g(name, default=1000)

            yield Product(
                sku=f"{self.name}:{pid}",
                supplier=self.supplier_name,
                name=name,
                origin=guess_origin(name),
                process=guess_process(name),
                price_krw=price,
                unit_g=unit,
                url=f"{self.base}/products/{d.get('handle')}",
                in_stock=in_stock,
            )


class FalconMicroScraper(ShopifyScraper):
    name = "falcon"
    supplier_name = "팔콘 마이크로 코리아"
    base = "https://korea.falcon-micro.com"
    collection = "korea-store-all-coffee"
