"""고도몰(godomall / NHN커머스) 기반 생두 쇼핑몰 공통 어댑터.

카탈로그: /goods/goods_list.php?cateCd=<코드>&page=N
상품:     /goods/goods_view.php?goodsNo=<번호>

상품 카드(`.item_cont`) 안의 찜하기 버튼이 `data-goods-no` / `data-goods-nm` /
`data-goods-price`를 그대로 들고 있어서, DOM 텍스트를 긁는 것보다 훨씬 안정적이다.
스킨이 바뀌어도 이 data 속성은 고도몰 공통 스크립트가 쓰기 때문에 잘 안 변한다.
"""
from __future__ import annotations
import re
from typing import Iterator

from curl_cffi import requests as cc_requests
from selectolax.parser import HTMLParser

from core.models import Product
from scrapers.base import (
    Scraper, parse_price_krw, parse_unit_g,
    guess_origin, guess_process, polite_sleep, cc_get_with_retry,
)

_GOODS_NO_RE = re.compile(r"goodsNo=(\d+)")


class GodomallScraper(Scraper):
    # --- subclass config ---
    name: str
    supplier_name: str
    base: str
    cate_cds: tuple[str, ...] = ()      # 생두 카테고리 코드들
    # ------------------------
    max_pages: int = 10
    timeout: int = 20
    sold_out_markers: tuple[str, ...] = ("품절", "SOLD OUT", "SOLDOUT", "일시품절")

    def _catalog_url(self, cate: str, page: int) -> str:
        return f"{self.base}/goods/goods_list.php?cateCd={cate}&page={page}"

    def fetch(self) -> list[Product]:
        out: list[Product] = []
        seen: set[str] = set()
        # 고도몰(로얄커피 등)은 데이터센터 IP + 봇 UA 조합에 403을 준다 —
        # 자택에서는 httpx 로도 되지만 Actions runner 에서 막힌다.
        with cc_requests.Session() as c:
            c.headers.update({"Accept-Language": "ko-KR,ko;q=0.9,en;q=0.5"})
            for cate in self.cate_cds:
                cat_seen: set[str] = set()
                for page in range(1, self.max_pages + 1):
                    if out:
                        polite_sleep()
                    r = cc_get_with_retry(c, self._catalog_url(cate, page),
                                          timeout=self.timeout)
                    if r.status_code >= 400:
                        raise RuntimeError(
                            f"{self.name}: HTTP {r.status_code} from "
                            f"{self._catalog_url(cate, page)}"
                        )
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
        for node in tree.css(".item_cont"):
            link = node.css_first("a[href*='goods_view.php']")
            if not link:
                continue
            m = _GOODS_NO_RE.search(link.attributes.get("href") or "")
            if not m:
                continue
            goods_no = m.group(1)

            name, price = self._from_data_attrs(node)
            if not name:
                el = node.css_first(".item_name, .item_tit_box a")
                name = el.text(strip=True) if el else ""
            if not name:
                continue
            if price is None:
                money = node.css_first(".item_money_box .item_price, .item_money_box")
                price = parse_price_krw(money.text()) if money else None

            text = node.text()
            in_stock = not any(mk in text for mk in self.sold_out_markers)

            yield Product(
                sku=f"{self.name}:{goods_no}",
                supplier=self.supplier_name,
                name=name,
                origin=guess_origin(name),
                process=guess_process(name),
                price_krw=price,
                unit_g=parse_unit_g(name, default=1000),
                url=f"{self.base}/goods/goods_view.php?goodsNo={goods_no}",
                in_stock=in_stock,
            )

    @staticmethod
    def _from_data_attrs(node) -> tuple[str, int | None]:
        btn = node.css_first("[data-goods-nm]")
        if not btn:
            return "", None
        name = (btn.attributes.get("data-goods-nm") or "").strip()
        raw = (btn.attributes.get("data-goods-price") or "").replace(",", "")
        try:
            price = int(float(raw)) if raw else None
        except ValueError:
            price = None
        return name, price


# --- concrete stores -------------------------------------------------------

class GscScraper(GodomallScraper):
    name = "gsc"
    supplier_name = "지에스씨(GSC)"
    base = "https://www.gsc.coffee"
    cate_cds = ("014",)                 # 생두


class MiCoffeeScraper(GodomallScraper):
    name = "micoffee"
    supplier_name = "엠아이커피"
    base = "https://www.micoffee.co.kr"
    # 001 남미 / 002 중미 / 003 아프리카 / 004 아시아&기타 / 024 MI 단독 생두
    cate_cds = ("001", "002", "003", "004", "024")


class WbeansScraper(GodomallScraper):
    name = "wbeans"
    supplier_name = "더블유빈즈"
    base = "https://www.wbeans.com"
    # 024 남아메리카 / 003 중앙아메리카 / 004 아프리카 / 005 아시아·그외 / 027 디카페인
    cate_cds = ("024", "003", "004", "005", "027")


class RoyalCoffeeScraper(GodomallScraper):
    name = "royal"
    supplier_name = "로얄커피코리아"
    base = "https://www.royalcoffeekorea.co.kr"
    cate_cds = ("039",)                 # 생두주문
