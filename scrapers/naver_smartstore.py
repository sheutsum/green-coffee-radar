"""네이버 스마트스토어 — 4개 사이트 공통 어댑터.

스마트스토어 페이지는 Next.js 기반으로, 일반적으로 다음 패턴 중 하나로
SSR 데이터가 박혀 있다:
  1) <script id="__NEXT_DATA__" type="application/json">{...}</script>
  2) window.__PRELOADED_STATE__ = {...};
  3) window.__APOLLO_STATE__ = {...};

이 어댑터는 위 셋을 순서대로 시도하고, JSON 트리에서 상품처럼 보이는
객체들을 찾아 평탄화한다.

⚠️ 봇 차단: 2026-07 기준 네이버는 **모든 데스크톱 TLS 지문**(chrome131~146,
safari, edge 전부 확인)의 smartstore 요청을 nid.naver.com 로그인으로 리다이렉트
시킨다. IP는 무관 — 자택 IP와 GitHub Actions 양쪽에서 동일하게 막힌다.
모바일 프로파일(chrome131_android)만 통과하며, 이 경우 m.smartstore.naver.com
모바일 SSR 페이지로 붙는다. 그래서 _IMPERSONATE는 android 고정이다.
"""
from __future__ import annotations
import re
import json
import time
import random
from curl_cffi import requests as cc_requests
from selectolax.parser import HTMLParser
from typing import Iterator

from core.models import Product
from scrapers.base import (
    Scraper, parse_unit_g, guess_origin, guess_process,
)

# curl_cffi의 impersonate="chrome131"이 진짜 Chrome의 TLS 지문, sec-ch-ua,
# Accept, User-Agent 등 거의 모든 헤더를 자동으로 채워준다. 우리는 한국어
# 콘텐츠를 받기 위한 Accept-Language만 명시적으로 추가.
_NAVER_EXTRA_HEADERS = {
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
}

# 반드시 android 프로파일. 데스크톱 지문은 전부 로그인 월로 튕긴다(모듈 docstring
# 참고). 최신 chrome146도 막히므로 "버전을 올리는" 방향으로는 해결되지 않는다.
_IMPERSONATE = "chrome131_android"

_PRELOAD_RE = re.compile(
    r"window\.__PRELOADED_STATE__\s*=\s*({.+?})\s*;", re.DOTALL
)
_APOLLO_RE = re.compile(
    r"window\.__APOLLO_STATE__\s*=\s*({.+?})\s*;", re.DOTALL
)


_JS_NULL_KEYWORDS = ("undefined", "NaN", "Infinity")


def _js_literal_to_json(src: str) -> str:
    """JS 객체 리터럴 → 유효 JSON. 문자열 안쪽은 절대 건드리지 않는다.
    문자열 밖에 단어 경계로 나타나는 undefined/NaN/Infinity만 null로 치환."""
    out: list[str] = []
    i = 0
    n = len(src)
    in_str = False
    escape = False
    while i < n:
        ch = src[i]
        if in_str:
            out.append(ch)
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_str = False
            i += 1
            continue
        if ch == '"':
            in_str = True
            out.append(ch)
            i += 1
            continue
        replaced = False
        for kw in _JS_NULL_KEYWORDS:
            klen = len(kw)
            if src.startswith(kw, i):
                left = src[i - 1] if i > 0 else ""
                right = src[i + klen] if i + klen < n else ""
                left_boundary = not (left.isalnum() or left in "_$")
                right_boundary = not (right.isalnum() or right in "_$")
                if left_boundary and right_boundary:
                    out.append("null")
                    i += klen
                    replaced = True
                    break
        if not replaced:
            out.append(ch)
            i += 1
    return "".join(out)


def _looks_like_product(d) -> bool:
    if not isinstance(d, dict):
        return False
    has_id = any(k in d for k in ("id", "productNo", "no", "channelProductNo"))
    has_name = isinstance(d.get("name"), str) and len(d["name"]) > 2
    has_price = any(
        isinstance(d.get(k), (int, str))
        for k in ("salePrice", "price", "discountedSalePrice", "mobileDiscountedSalePrice")
    )
    return has_id and has_name and has_price


def _walk(node):
    if isinstance(node, dict):
        if _looks_like_product(node):
            yield node
        for v in node.values():
            yield from _walk(v)
    elif isinstance(node, list):
        for v in node:
            yield from _walk(v)


class NaverSmartStoreScraper(Scraper):
    # subclass-set
    store_id: str = ""        # e.g. "verde_trade"
    category_id: str = ""     # GUID-like category id
    supplier_name: str = ""

    base = "https://smartstore.naver.com"
    page_size = 20
    # ponytail: 모바일 SSR은 page/size 파라미터를 무시하고 st=RECENT 최신 20개만
    # 준다(page=1,2,3 모두 동일한 20개 반환 확인). 즉 카탈로그 전체(verde 기준
    # categoryProducts.totalCount=341)가 아니라 최신 20개만 본다.
    # 15분 주기 신상 감시가 목적이라 한 스토어가 15분 안에 21개 이상을 올리지
    # 않는 한 놓치지 않는다. 다만 PWA feed의 네이버 스토어 상품 수도 20으로 잘린다.
    # 전체 카탈로그가 필요해지면 내부 API(/i/v1/stores/{channelNo}/categories/
    # {catId}/products)를 뚫어야 하는데 2026-07 기준 429로 막혀 있다.
    max_pages = 1

    def _catalog_url(self, page: int) -> str:
        return (
            f"{self.base}/{self.store_id}/category/{self.category_id}"
            f"?st=RECENT&dt=IMAGE&page={page}&size={self.page_size}"
        )

    def fetch(self) -> list[Product]:
        out: list[Product] = []
        seen: set[str] = set()
        # 4개 네이버 가게가 동시에 호출하지 않도록 호출 직전 무작위 대기
        time.sleep(random.uniform(2.5, 6.0))

        # curl_cffi.Session — TLS 지문까지 Chrome 흉내내서 봇 검출 우회
        with cc_requests.Session() as c:
            c.headers.update(_NAVER_EXTRA_HEADERS)

            # 메인 페이지 prefetch — 쿠키/세션 워밍업 (정상 브라우저 흐름 흉내)
            home_url = f"{self.base}/{self.store_id}"
            try:
                c.get(home_url, impersonate=_IMPERSONATE, timeout=15,
                      allow_redirects=True)
                time.sleep(random.uniform(1.2, 2.8))
            except Exception:
                pass  # 워밍업 실패해도 본 요청은 시도

            # 카테고리 페이지로 넘어갈 때는 home에서 온 것처럼 Referer 설정
            cat_headers = {"Referer": home_url}
            for page in range(1, self.max_pages + 1):
                url = self._catalog_url(page)
                r = c.get(url, headers=cat_headers,
                          impersonate=_IMPERSONATE, timeout=30,
                          allow_redirects=True)
                if r.status_code in (403, 429):
                    raise RuntimeError(
                        f"{self.name}: Naver returned {r.status_code} "
                        "(anti-bot). curl_cffi+impersonate도 막힘 — "
                        "Playwright 검토 필요."
                    )
                if r.status_code >= 400:
                    raise RuntimeError(
                        f"{self.name}: HTTP {r.status_code} from {url}"
                    )
                # 봇으로 찍히면 200 + 로그인 페이지가 온다. 이걸 잡아내지 않으면
                # 아래 파서가 "SSR JSON not found = layout 변경"이라는 엉뚱한
                # 진단을 내놓는다(실제로 그래서 한참 헤맴).
                if "nidlogin" in str(r.url):
                    raise RuntimeError(
                        f"{self.name}: 로그인 월로 리다이렉트됨({r.url}). "
                        f"impersonate={_IMPERSONATE} 가 봇으로 검출됨 — "
                        "다른 모바일 프로파일 검토 필요."
                    )
                items = list(self._extract_products(r.text))
                new = [p for p in items if p.sku not in seen]
                if not new:
                    break
                for p in new:
                    seen.add(p.sku)
                    out.append(p)
                # 페이지 사이도 짧게 쉬어 자연스럽게
                time.sleep(random.uniform(0.8, 1.8))
        return out

    def _extract_products(self, html: str) -> Iterator[Product]:
        data = self._find_ssr_json(html)
        if data is None:
            raise RuntimeError(
                f"{self.name}: SSR JSON not found. Site layout may have changed."
            )
        seen_ids: set[str] = set()
        for d in _walk(data):
            pid = str(
                d.get("id")
                or d.get("productNo")
                or d.get("channelProductNo")
                or d.get("no")
                or ""
            )
            if not pid or pid in seen_ids:
                continue
            seen_ids.add(pid)

            name = d["name"]
            price = self._coerce_price(
                d.get("discountedSalePrice")
                or d.get("mobileDiscountedSalePrice")
                or d.get("salePrice")
                or d.get("price")
            )
            in_stock = not (d.get("soldOut") or d.get("stockQuantity") == 0)

            url = f"{self.base}/{self.store_id}/products/{pid}"

            yield Product(
                sku=f"{self.name}:{pid}",
                supplier=self.supplier_name,
                name=name,
                origin=guess_origin(name),
                process=guess_process(name),
                price_krw=price,
                unit_g=parse_unit_g(name, default=1000),
                url=url,
                in_stock=in_stock,
            )

    @staticmethod
    def _coerce_price(v) -> int | None:
        if isinstance(v, int):
            return v
        if isinstance(v, str):
            try:
                return int(v.replace(",", ""))
            except ValueError:
                return None
        return None

    @staticmethod
    def _find_ssr_json(html: str):
        # 1) Next.js __NEXT_DATA__
        tree = HTMLParser(html)
        next_node = tree.css_first("script#__NEXT_DATA__")
        if next_node:
            try:
                return json.loads(next_node.text())
            except (json.JSONDecodeError, TypeError):
                pass
        # 2) __PRELOADED_STATE__  — brace counting (정규식보다 안정적)
        for marker in (
            "window.__PRELOADED_STATE__",
            "window[\"__PRELOADED_STATE__\"]",
            "__PRELOADED_STATE__",
        ):
            idx = html.find(marker)
            if idx == -1:
                continue
            # marker 이후 첫 '{' 찾기
            brace_start = html.find("{", idx)
            if brace_start == -1:
                continue
            end = NaverSmartStoreScraper._scan_balanced_json(html, brace_start)
            if end == -1:
                continue
            raw = html[brace_start:end]
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                # window.__PRELOADED_STATE__는 엄밀한 JSON이 아니라 JS 객체
                # 리터럴이다. 네이버는 undefined/NaN/Infinity 같은 JS 전용
                # 값을 그대로 박아두므로 json.loads가 실패한다.
                # 문자열 영역을 건드리지 않고 이들만 null로 치환 후 재시도.
                try:
                    return json.loads(_js_literal_to_json(raw))
                except json.JSONDecodeError:
                    continue
        # 3) __APOLLO_STATE__
        m = _APOLLO_RE.search(html)
        if m:
            try:
                return json.loads(m.group(1))
            except json.JSONDecodeError:
                pass
        return None

    @staticmethod
    def _scan_balanced_json(s: str, start: int) -> int:
        """s[start]가 '{' 일 때, 균형 잡힌 닫는 '}' 다음 인덱스 반환. 실패 시 -1.
        문자열 안의 '{}'와 escape 처리까지 고려."""
        if start >= len(s) or s[start] != "{":
            return -1
        depth = 0
        i = start
        in_str = False
        escape = False
        n = len(s)
        while i < n:
            ch = s[i]
            if escape:
                escape = False
            elif ch == "\\" and in_str:
                escape = True
            elif ch == '"':
                in_str = not in_str
            elif not in_str:
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        return i + 1
            i += 1
        return -1


# --- concrete stores ------------------------------------------------------

class VerdeTradeScraper(NaverSmartStoreScraper):
    name = "verde"
    supplier_name = "베르데 트레이드"
    store_id = "verde_trade"
    category_id = "117e91878227475083b34fdfbd553db2"


class RyubeansScraper(NaverSmartStoreScraper):
    name = "ryubeans"
    supplier_name = "류빈스커피"
    store_id = "ryubeans"
    category_id = "7f74a04ff9e3458e86fb68a305133d08"


class ChBeanScraper(NaverSmartStoreScraper):
    name = "chbean"
    supplier_name = "씨에이치빈"
    store_id = "chbean"
    category_id = "86715f19337349238c32fde6c5655a13"


class DoanSelectShopScraper(NaverSmartStoreScraper):
    name = "doan"
    supplier_name = "도안 셀렉트 샵"
    store_id = "doanselectshop"
    category_id = "7cf945cf3b334753baeed79a7f9a4b25"
