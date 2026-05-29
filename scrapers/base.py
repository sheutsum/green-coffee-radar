from __future__ import annotations
import re
import random
import time
from abc import ABC, abstractmethod
from typing import Optional

from core.models import Product


# Heuristics shared by most Korean coffee importers
_ORIGIN_KEYWORDS = [
    ("Ethiopia", "Ethiopia"), ("에티오피아", "Ethiopia"),
    ("Colombia", "Colombia"), ("콜롬비아", "Colombia"),
    ("Bolivia", "Bolivia"), ("볼리비아", "Bolivia"),
    ("Brazil", "Brazil"), ("브라질", "Brazil"),
    ("Ecuador", "Ecuador"), ("에콰도르", "Ecuador"),
    ("Peru", "Peru"), ("페루", "Peru"),
    ("Guatemala", "Guatemala"), ("과테말라", "Guatemala"),
    ("El Salvador", "El Salvador"), ("엘살바도르", "El Salvador"),
    ("Honduras", "Honduras"), ("온두라스", "Honduras"),
    ("Costa Rica", "Costa Rica"), ("코스타리카", "Costa Rica"),
    ("Panama", "Panama"), ("파나마", "Panama"),
    ("Kenya", "Kenya"), ("케냐", "Kenya"),
    ("Rwanda", "Rwanda"), ("르완다", "Rwanda"),
    ("Burundi", "Burundi"), ("부룬디", "Burundi"),
    ("Tanzania", "Tanzania"), ("탄자니아", "Tanzania"),
    ("Yemen", "Yemen"), ("예멘", "Yemen"),
    ("India", "India"), ("인도네시아", "Indonesia"),
    ("Indonesia", "Indonesia"), ("인도", "India"),
    ("Papua New Guinea", "Papua New Guinea"), ("파푸아뉴기니", "Papua New Guinea"),
    ("Mexico", "Mexico"), ("멕시코", "Mexico"),
    ("Nicaragua", "Nicaragua"), ("니카라과", "Nicaragua"),
]

# Order matters — match longer / more specific labels first
_PROCESS_KEYWORDS = [
    # English
    "Anaerobic Natural", "Coco Natural", "Mosto Anaerobic",
    "White Honey", "Red Honey", "Yellow Honey", "Black Honey",
    "Anaerobic Washed", "Anaerobic",
    "Carbonic Maceration", "Thermal Shock",
    "Washed", "Natural", "Honey", "Pulped Natural",
    "Decaf",
    # Korean (Korean importers freely mix both)
    "무산소 내추럴", "무산소 워시드", "코코 내추럴",
    "화이트 허니", "레드 허니", "옐로우 허니", "블랙 허니",
    "무산소", "워시드", "내추럴", "허니", "디카페인",
]


def guess_origin(name: str) -> Optional[str]:
    low = name.lower()
    for needle, label in _ORIGIN_KEYWORDS:
        if needle.lower() in low:
            return label
    return None


def guess_process(name: str) -> Optional[str]:
    low = name.lower()
    for kw in _PROCESS_KEYWORDS:
        if kw.lower() in low:
            return kw
    return None


# Match either "12,345원" or "￦12,345" / "₩12,345"
PRICE_RE = re.compile(
    r"(?:[￦₩]\s*(\d{1,3}(?:,\d{3})+|\d+)|(\d{1,3}(?:,\d{3})+|\d+)\s*원)"
)
# 50g / 500g / 1kg / 1.5kg from product names
UNIT_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(kg|g)\b", re.IGNORECASE)


def parse_price_krw(text: str) -> Optional[int]:
    m = PRICE_RE.search(text)
    if not m:
        return None
    raw = m.group(1) or m.group(2)
    return int(raw.replace(",", ""))


def parse_unit_g(name: str, default: Optional[int] = None) -> Optional[int]:
    m = UNIT_RE.search(name)
    if not m:
        return default
    value, unit = float(m.group(1)), m.group(2).lower()
    return int(value * 1000) if unit == "kg" else int(value)


class Scraper(ABC):
    name: str   # short id used in SKU prefix

    @abstractmethod
    def fetch(self) -> list[Product]:
        """Return current catalog as a list of Product."""
        ...


# ---------------------------------------------------------------------------
# Cafe24Scraper — covers most Korean coffee importers' Cafe24-based shops.
# Two URL patterns coexist:
#   1) /product/<slug>/<product_no>/category/<cate_no>/display/1/   (newer)
#   2) /product/detail.html?product_no=<id>&cate_no=<n>...           (older)
# ---------------------------------------------------------------------------
import httpx
from selectolax.parser import HTMLParser

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; GreenCoffeeRadar/0.1; personal alert bot)",
    "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.5",
}


def polite_sleep(min_s: float = 0.8, max_s: float = 1.8) -> None:
    """Random short pause between requests — spreads burst, less robotic."""
    time.sleep(random.uniform(min_s, max_s))


def get_with_retry(
    client: "httpx.Client",
    url: str,
    *,
    max_retries: int = 3,
    base_backoff: float = 2.0,
    **kwargs,
) -> "httpx.Response":
    """GET with exponential backoff on 429/5xx and transient transport errors.
    Honors Retry-After when present. Returns the final Response so the caller
    can still inspect / raise_for_status()."""
    for attempt in range(max_retries + 1):
        try:
            r = client.get(url, **kwargs)
        except (httpx.TimeoutException, httpx.TransportError):
            if attempt >= max_retries:
                raise
            time.sleep(base_backoff ** (attempt + 1) + random.uniform(0, 1))
            continue

        if r.status_code in (429, 502, 503, 504) and attempt < max_retries:
            ra = r.headers.get("Retry-After", "").strip()
            if ra.isdigit():
                delay = float(ra)
            else:
                delay = base_backoff ** (attempt + 1) + random.uniform(0, 1)
            time.sleep(delay)
            continue
        return r
    raise RuntimeError(f"get_with_retry: exhausted retries for {url}")


_PRODUCT_ID_RE = re.compile(
    r"/product/[^/]+/(\d+)/|[?&]product_no=(\d+)"
)


class Cafe24Scraper(Scraper):
    # --- config (subclass overrides) ---
    name: str
    supplier_name: str
    base: str
    catalog_url_template: str   # must include {page}
    # if set, only product URLs whose path contains this substring are kept
    # (defends against "추천 상품" sidebars leaking non-green-bean items)
    url_must_contain: tuple[str, ...] = ()
    default_unit_g: Optional[int] = 1000   # most importers price by the kg
    max_pages: int = 25                    # safety cap
    timeout: int = 20
    # extra phrases that mark sold-out (varies by skin)
    sold_out_markers: tuple[str, ...] = ("품절", "SOLD OUT", "SOLDOUT")

    def fetch(self) -> list[Product]:
        out: list[Product] = []
        seen_ids: set[str] = set()
        with httpx.Client(headers=_HEADERS, timeout=self.timeout,
                          follow_redirects=True) as c:
            for page in range(1, self.max_pages + 1):
                if page > 1:
                    polite_sleep()
                url = self.catalog_url_template.format(base=self.base, page=page)
                r = get_with_retry(c, url)
                r.raise_for_status()
                items = list(self._parse_list(r.text))
                # stop when a page yields nothing new (handles end-of-pagination
                # and Cafe24's tendency to loop back to page 1 past the end)
                new = [p for p in items if p.sku not in seen_ids]
                if not new:
                    break
                for p in new:
                    seen_ids.add(p.sku)
                    out.append(p)
        return out

    def _parse_list(self, html: str):
        tree = HTMLParser(html)
        nodes = []
        for sel in (
            "ul.prdList > li", "ul.prdList li",
            ".xans-product-listnormal ul li",
            "ul[class*='prdList'] li",
        ):
            nodes = tree.css(sel)
            if nodes:
                break

        for node in nodes:
            link = node.css_first("a[href*='/product/']")
            if not link:
                continue
            href = link.attributes.get("href") or ""
            m = _PRODUCT_ID_RE.search(href)
            if not m:
                continue
            product_id = m.group(1) or m.group(2)
            full_url = href if href.startswith("http") else self.base + href

            # filter (e.g. only 생두 slugs)
            if self.url_must_contain and not any(
                tok in full_url for tok in self.url_must_contain
            ):
                continue

            name = self._extract_name(node)
            if not name:
                continue

            text = node.text()
            price = parse_price_krw(text)
            in_stock = not any(m in text for m in self.sold_out_markers)
            unit = parse_unit_g(name, default=self.default_unit_g)

            yield Product(
                sku=f"{self.name}:{product_id}",
                supplier=self.supplier_name,
                name=name,
                origin=guess_origin(name),
                process=guess_process(name),
                price_krw=price,
                unit_g=unit,
                url=full_url,
                in_stock=in_stock,
            )

    def _extract_name(self, node) -> str:
        for sel in (
            ".description .name a", ".description strong a",
            "p.name a", "strong.name a", ".name a",
        ):
            el = node.css_first(sel)
            if el:
                name = el.text(strip=True)
                if name:
                    return re.sub(r"^\s*상품명\s*:\s*", "", name).strip()
        # fallback: img alt
        img = node.css_first("img[alt]")
        if img:
            alt = (img.attributes.get("alt") or "").strip()
            # skip generic alt text used by Cafe24 themes
            generic = ("스페셜티", "드립백커피", "원두커피", "Coffee Me Up", "커피 리브레", "MOMOS")
            if alt and not any(alt.startswith(g) for g in generic):
                return alt
        return ""
