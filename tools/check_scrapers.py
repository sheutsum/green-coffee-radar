"""등록된 스크레이퍼가 실제로 상품을 뽑는지 확인한다.

    python tools/check_scrapers.py            # 전체
    python tools/check_scrapers.py gsc sopex  # 이름으로 골라서

상품 0개거나 name/url이 빈 스크레이퍼가 있으면 exit code 1.
네트워크를 타므로 CI 필수 게이트가 아니라 손으로 돌리는 점검용이다.
"""
from __future__ import annotations
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from run import SCRAPERS  # noqa: E402


def main(argv: list[str]) -> int:
    wanted = set(argv[1:])
    targets = [s for s in SCRAPERS if not wanted or s.name in wanted]
    if not targets:
        print(f"no scraper matched {sorted(wanted)}")
        return 1

    bad: list[str] = []
    for s in targets:
        try:
            products = s.fetch()
        except Exception as e:  # noqa: BLE001
            print(f"{s.name:12} FETCH FAILED: {type(e).__name__}: {e}")
            bad.append(s.name)
            continue

        broken = [p for p in products if not p.name or not p.url]
        priced = sum(1 for p in products if p.price_krw)
        sample = products[0].name[:44] if products else ""
        print(f"{s.name:12} {len(products):4d} products, "
              f"{priced:3d} priced, {len(broken)} broken   {sample}")
        if not products or broken:
            bad.append(s.name)

    if bad:
        print(f"\nFAIL: {', '.join(bad)}")
        return 1
    print(f"\nOK: {len(targets)} scrapers")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
