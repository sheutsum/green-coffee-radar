"""모모스커피 — 2026-07 사이트 개편으로 Cafe24 → imweb 이전.

구 스크레이퍼는 Cafe24 카탈로그(`/category/ALL/162/?cate_no=162`)를 긁었는데,
개편 후 이 URL은 홈으로 301 리다이렉트되고 상품이 0개가 됐다(마지막 수집
2026-07-28).

새 스토어프론트(imweb)는 상품 목록을 HTML에 렌더하지 않고, 백오피스가 제공하는
공개 읽기전용 JSON API를 브라우저에서 호출해 그린다. 페이지 소스의
`window.MOMOS_API_BASE = "https://office.momos.co.kr"` + `MOMOS_STORE_API`
클라이언트 참고. 그래서 HTML 파싱 대신 그 API를 그대로 쓴다 — 산지/가공/SCA
점수까지 구조화돼 나오므로 base.py의 이름 휴리스틱보다 정확하다.

응답: {"greenBeans": [{prodNo, prodCode, name, price, thumbnail, origin,
continent, flag, process, sca, variety, grade, availableKg, status}, ...]}

주의:
- SKU가 Cafe24 product_no(2398~2838) → imweb prodNo(4656~7359)로 바뀌었다.
  겹치는 번호가 없어서 잘못된 dedup은 안 나지만, 전환 후 첫 실행에서 현재
  카탈로그 전체가 "신상"으로 잡힌다.
- availableKg는 공개 API에서 전부 0으로 내려온다(재고 비공개). 재고 판정은
  status만 사용.
- price는 상세 페이지의 "판매가"(표시가)와 같은 값이다. 옵션(중량 등)에 추가금이
  붙는 상품은 실제 결제가가 조금 더 높을 수 있다 — 목록 표시가를 쓰는 건 다른
  스크레이퍼와 동일한 기준이라 그대로 둔다.
"""
from __future__ import annotations
import httpx

from core.models import Product
from scrapers.base import (
    Scraper, get_with_retry, guess_origin, guess_process, parse_unit_g,
)

_API = "https://office.momos.co.kr/api/public/green-beans"
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; GreenCoffeeRadar/0.1; personal alert bot)",
    "Accept": "application/json",
    "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.5",
    # 백오피스는 스토어프론트에서만 불리는 API라 CORS 오리진을 맞춰준다
    "Origin": "https://momos.co.kr",
    "Referer": "https://momos.co.kr/greenbean",
}


class MomosScraper(Scraper):
    name = "momos"
    supplier_name = "모모스커피"
    timeout = 20

    def fetch(self) -> list[Product]:
        with httpx.Client(headers=_HEADERS, timeout=self.timeout,
                          follow_redirects=True) as c:
            r = get_with_retry(c, _API)
            r.raise_for_status()
            beans = r.json().get("greenBeans") or []

        out: list[Product] = []
        for b in beans:
            prod_no = b.get("prodNo")
            name = (b.get("name") or "").strip()
            if not prod_no or not name:
                continue
            out.append(Product(
                sku=f"{self.name}:{prod_no}",
                supplier=self.supplier_name,
                name=name,
                # API의 origin은 한글("볼리비아") — 다른 공급사와 패싯을 맞추려면
                # 영문 라벨로 정규화해야 한다. guess_origin이 한/영 둘 다 받는다.
                origin=guess_origin(b.get("origin") or "") or guess_origin(name),
                process=b.get("process") or guess_process(name),
                price_krw=b.get("price"),
                # 지금은 이름에 중량 표기가 없어 전부 기본값 1kg로 떨어지지만,
                # 500g 샘플팩 같은 게 생기면 원/kg가 2배로 어긋난다
                unit_g=parse_unit_g(name, default=1000),
                url=f"https://momos.co.kr/shop_view/?idx={prod_no}",
                in_stock=b.get("status") == "sale",
            ))
        return out


if __name__ == "__main__":
    ps = MomosScraper().fetch()
    assert ps, "0 products — API 응답 스키마가 바뀌었는지 확인"
    assert all(p.price_per_kg for p in ps), "가격/단위 파싱 실패"
    assert all(p.url.startswith("https://momos.co.kr/shop_view/?idx=") for p in ps)
    print(f"{len(ps)} products")
    for p in ps[:5]:
        print(f"  {p.origin or '?':<12} {p.price_per_kg:>7,}원/kg  {p.name}")
