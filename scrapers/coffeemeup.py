"""커피미업 — Cafe24 new skin, very similar structure to Momos.
Catalog: /category/green/182/?page=N
Product:  /product/<slug>/<id>/category/182/display/1/
Notable: prices use ￦ prefix, unit (50g/500g) is in product name.
"""
from scrapers.base import Cafe24Scraper


class CoffeeMeUpScraper(Cafe24Scraper):
    name = "coffeemeup"
    supplier_name = "커피미업"
    base = "https://coffeemeup.store"
    catalog_url_template = "{base}/category/green/182/?page={page}"
    # 슬러그가 "생두" 또는 "파나마"/"코스타리카"처럼 산지명만 시작하기도 함.
    # 안전하게 '/product/' 포함 + 카테고리 182 URL로 충분.
    url_must_contain = ("/category/182/",)
    # 단위가 명확하지 않은 상품(예: "커피벨트 - 로스터리 목록") 가격이 비정상일 수 있음
    # default_unit_g=None 으로 두면 unit이 명시된 상품(50g/500g)만 /kg 환산됨
    default_unit_g = None
