"""커피 리브레 — Cafe24 older skin, /product/detail.html?product_no=NNNN URLs.
Catalog category 57 = 생두소분 (1kg vacuum-packed portions).
Most items often show SOLDOUT — the bot will alert when fresh stock comes in.
"""
from scrapers.base import Cafe24Scraper


class CoffeeLibreScraper(Cafe24Scraper):
    name = "libre"
    supplier_name = "커피 리브레"
    base = "https://coffeelibre.kr"
    # 생두소분 카테고리 (57). 정렬 옵션이 없으면 기본 신상품순으로 추정됨.
    catalog_url_template = "{base}/category/생두소분/57/?page={page}"
    # 리브레는 product/detail.html 패턴이므로 이 토큰으로 필터
    url_must_contain = ("/product/detail.html",)
    default_unit_g = 1000   # 모든 상품이 "1kg 소분 진공포장"
