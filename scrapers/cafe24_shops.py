"""Cafe24 기반 생두 쇼핑몰 4곳 — 설정만 다르고 파싱은 Cafe24Scraper 공통.

카테고리 번호는 각 사이트 홈페이지의 네비게이션에서 확인했다(2026-08).
전 카테고리가 생두인 수입사(소펙스·레햄)는 산지별 카테고리를 전부 돈다.
"""
from scrapers.base import Cafe24Scraper


class SopexScraper(Cafe24Scraper):
    name = "sopex"
    supplier_name = "소펙스코리아"
    base = "https://sopexkorea.com"
    # 24 중남미 / 26 아프리카 / 27 아시아 / 66 디카페인 / 74 스페셜티
    cate_nos = (24, 26, 27, 66, 74)
    max_pages = 6


class RnCScraper(Cafe24Scraper):
    name = "rnc"
    supplier_name = "레햄코리아(RNC)"
    base = "https://rnccoffee.kr"
    # 43 Africa / 44 South America / 45 Central America / 46 Asia / 47 Other
    cate_nos = (43, 44, 45, 46, 47)
    max_pages = 6


class NamusairoScraper(Cafe24Scraper):
    name = "namusairo"
    supplier_name = "나무사이로"
    base = "https://namusairo.green"
    cate_nos = (24,)          # GREEN
    max_pages = 5


class CoffeeSpellScraper(Cafe24Scraper):
    name = "coffeespell"
    supplier_name = "커피스펠"
    base = "https://coffeespell.co.kr"
    cate_nos = (25,)          # 생두
    max_pages = 5
