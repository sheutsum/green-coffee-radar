"""
네이버 스마트스토어 페이지 응답에서 상품 데이터가 어디 박혀있는지 진단.
사용법: python debug_naver.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from curl_cffi import requests as cc_requests
from scrapers.naver_smartstore import NaverSmartStoreScraper, _walk

STORE_ID = "verde_trade"
CAT_ID = "117e91878227475083b34fdfbd553db2"

home = f"https://smartstore.naver.com/{STORE_ID}"
url = f"{home}/category/{CAT_ID}?st=RECENT&dt=IMAGE&page=1&size=40"

print(f"Fetching: {url}\n")

with cc_requests.Session() as s:
    s.headers.update({"Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7"})
    try:
        s.get(home, impersonate="chrome131", timeout=15, allow_redirects=True)
    except Exception as e:
        print(f"home prefetch failed: {e}")
    r = s.get(url, headers={"Referer": home}, impersonate="chrome131",
              timeout=30, allow_redirects=True)

print(f"Status: {r.status_code}")
print(f"Content length: {len(r.text):,} chars\n")
html = r.text

print("=" * 60)
print("Trying to extract SSR JSON with brace counting...")
print("=" * 60)
data = NaverSmartStoreScraper._find_ssr_json(html)
if data is None:
    print("Still no SSR JSON found. More analysis needed.")
    for marker in ("window.__PRELOADED_STATE__", "__PRELOADED_STATE__",
                   "__NEXT_DATA__", "__APOLLO_STATE__"):
        idx = html.find(marker)
        if idx >= 0:
            print(f"\n  Found '{marker}' at offset {idx}")
            print(f"  Context: ...{html[max(0,idx-30):idx+80]}...")
else:
    print(f"SSR JSON parsed!")
    print(f"   Top-level type: {type(data).__name__}")
    if isinstance(data, dict):
        print(f"   Top-level keys: {list(data.keys())[:10]}")

    print("\n" + "=" * 60)
    print("Walking JSON tree for product-shaped dicts...")
    print("=" * 60)
    seen_ids = set()
    count = 0
    for d in _walk(data):
        pid = str(d.get("id") or d.get("productNo") or d.get("channelProductNo") or "")
        if not pid or pid in seen_ids:
            continue
        seen_ids.add(pid)
        name = d.get("name", "<no name>")
        price = (d.get("discountedSalePrice") or d.get("salePrice")
                 or d.get("price"))
        soldOut = d.get("soldOut")
        count += 1
        if count <= 8:
            print(f"  [{count}] pid={pid}  name={name[:50]}")
            print(f"       price={price}  soldOut={soldOut}")
    print(f"\nTotal product-shaped dicts found: {count}")

with open("naver_debug.html", "w", encoding="utf-8") as f:
    f.write(html)
print(f"\nFull HTML saved to: naver_debug.html ({len(html):,} chars)")
