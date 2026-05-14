"""모모스커피 — Cafe24 new skin, /product/<slug>/<id>/ URLs."""
from scrapers.base import Cafe24Scraper


class MomosScraper(Cafe24Scraper):
    name = "momos"
    supplier_name = "모모스커피"
    base = "https://momos.co.kr"
    # cate_no 162 = 생두 ALL, sort_method=5 = 신상품
    catalog_url_template = (
        "{base}/category/ALL/162/?cate_no=162&sort_method=5&page={page}"
    )
    # only keep links whose slug starts with 생두- (raw or URL-encoded)
    url_must_contain = ("/product/생두-", "/product/%EC%83%9D%EB%91%90-")
    default_unit_g = 1000   # 모모스 생두는 1kg 기본
