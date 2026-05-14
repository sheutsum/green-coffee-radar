"""식스샵(Sixshop) 사이트 공통 어댑터.

식스샵 사이트는 자체 도메인의 다음 endpoint를 호출하여 상품을 동적 로딩한다:
    GET /apis/mall/shop/products-catalog

인증: Authorization: Basic <base64(site_id)>
site_id는 사이트의 contents.sixshop.com/uploadedFiles/<site_id>/... CDN 경로에서
또는 페이지 소스에서 확인 가능.

쿼리 파라미터:
    page=N (0-indexed)
    npp=20~40 (number per page)
    categories=ID1,ID2,...  (선택 — 빼면 전체 카탈로그)
    customerGradeNo=-2
    orderType=PRODUCT_ORDER_NO
    useSortedBySoldOutAllPage=notUse
    customerNo=0

응답 구조는 사이트마다 약간 다를 수 있어, NaverSmartStoreScraper에서 쓰는
"product처럼 생긴 dict 찾기" 휴리스틱을 재활용한다.
"""
from __future__ import annotations
import base64
import httpx
from typing import Iterator

from core.models import Product
from scrapers.base import (
    Scraper, guess_origin, guess_process,
)
class SixshopScraper(Scraper):
    # --- subclass config ---
    site_id: str = ""           # e.g. "10202"
    supplier_name: str = ""
    base: str = ""              # e.g. "https://www.cafenogales.co.kr"
    # 카테고리 ID 목록 (생두만 필터). 비워두면 전체.
    categories: tuple[str, ...] = ()
    # ------------------------
    page_size = 40
    max_pages = 25

    @property
    def _auth(self) -> str:
        return "Basic " + base64.b64encode(self.site_id.encode()).decode()

    def _headers(self) -> dict:
        return {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept": "*/*",
            "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.5",
            "Authorization": self._auth,
            "Referer": f"{self.base}/shop",
            "X-Requested-With": "XMLHttpRequest",
        }

    def _params(self, page: int) -> dict:
        params = {
            "page": page,
            "npp": self.page_size,
            "customerGradeNo": -2,
            "orderType": "PRODUCT_ORDER_NO",
            "useSortedBySoldOutAllPage": "notUse",
            "customerNo": 0,
        }
        if self.categories:
            params["categories"] = ",".join(self.categories)
        return params

    def fetch(self) -> list[Product]:
        out: list[Product] = []
        seen: set[str] = set()
        url = f"{self.base}/apis/mall/shop/products-catalog"

        with httpx.Client(headers=self._headers(), timeout=20,
                          follow_redirects=True) as c:
            page = 0
            total_pages = self.max_pages  # 첫 응답으로 갱신
            while page < total_pages and page < self.max_pages:
                r = c.get(url, params=self._params(page))
                r.raise_for_status()
                try:
                    data = r.json()
                except Exception:
                    break

                # 첫 페이지에서 totalPages 받아 루프 한계 설정
                if isinstance(data, dict) and "totalPages" in data:
                    total_pages = data.get("totalPages") or 1

                items = list(self._extract_products(data))
                new = [p for p in items if p.sku not in seen]
                if not new and items:  # 같은 page 다시 받음 = 끝
                    break
                if not items:
                    break
                for p in new:
                    seen.add(p.sku)
                    out.append(p)
                page += 1
        return out

    def _extract_products(self, data) -> Iterator[Product]:
        if not isinstance(data, dict):
            return
        content = data.get("content")
        if not isinstance(content, list):
            return
        for d in content:
            if not isinstance(d, dict):
                continue
            pid = d.get("id")
            if pid is None:
                continue
            pid = str(pid)
            name = (d.get("name") or "").strip()
            if not name:
                continue

            # 가격: price.regularPrice (1kg 단가, KRW)
            price = None
            price_obj = d.get("price")
            if isinstance(price_obj, dict):
                price = self._coerce_price(price_obj.get("regularPrice"))

            in_stock = not bool(d.get("soldOut"))

            # 가공법: 이름이 보통 "코드 / 품종 / 가공법" 패턴 → 마지막 / 뒤
            process = None
            if " / " in name:
                process = name.rsplit(" / ", 1)[-1].strip()
            if not process:
                process = guess_process(name)

            # 식스샵 상품 detail URL — 응답에 명시된 게 없으면 site_id+id 기반 추측
            detail_url = f"{self.base}/product/{pid}"

            yield Product(
                sku=f"{self.name}:{pid}",
                supplier=self.supplier_name,
                name=name,
                origin=guess_origin(name),
                process=process,
                price_krw=price,
                unit_g=1000,  # 식스샵 응답의 regularPrice는 1kg 단가
                url=detail_url,
                in_stock=in_stock,
            )

    @staticmethod
    def _coerce_price(v):
        if isinstance(v, (int, float)):
            return int(v)
        if isinstance(v, str):
            try:
                return int(float(v.replace(",", "")))
            except ValueError:
                return None
        return None


# --- concrete stores -------------------------------------------------------

class CafeNogalesScraper(SixshopScraper):
    name = "cafenogales"
    supplier_name = "카페노갈레스"
    site_id = "10202"
    base = "https://www.cafenogales.co.kr"
    # 사용자가 cURL inspection으로 확인한 14개 카테고리 ID (생두 전체)
    categories = (
        "132953", "132952", "132955", "150819", "132954", "232925",
        "143505", "227824", "273097", "195437", "129489", "129490",
        "723967", "727098",
    )


class CompassCoffeeScraper(SixshopScraper):
    name = "compass"
    supplier_name = "콤파스 커피"
    site_id = "224244"
    base = "https://compasscoffee.kr"
    # 사용자 inspection으로 확인한 13개 생두 카테고리 ID
    categories = (
        "1113765", "1112855", "1112854", "770813", "770814", "770389",
        "1077451", "1034797", "975931", "1112426", "1118973", "881304",
        "880244",
    )
