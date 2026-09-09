"""403 재시도 + carry-forward + last_ok 회귀 테스트. `python test_feed_resilience.py`"""
from __future__ import annotations
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from scrapers.base import RETRY_STATUS, get_with_retry
from tools.build_feed import carry_forward


class _FakeResp:
    def __init__(self, status): self.status_code, self.headers = status, {"Retry-After": "0"}


class _FakeClient:
    def __init__(self, statuses): self.statuses, self.calls = list(statuses), 0
    def get(self, url, **kw):
        self.calls += 1
        return _FakeResp(self.statuses.pop(0) if self.statuses else 200)


def test_403_is_retried():
    assert 403 in RETRY_STATUS
    c = _FakeClient([403, 403])
    assert get_with_retry(c, "http://x").status_code == 200
    assert c.calls == 3


def test_hard_403_still_surfaces():
    c = _FakeClient([403] * 9)
    assert get_with_retry(c, "http://x").status_code == 403


def _payload(products, errors, generated_at="2026-09-09T00:00:00+00:00"):
    return {"generated_at": generated_at, "count": len(products),
            "suppliers": sorted({p["supplier"] for p in products}),
            "errors": errors, "products": list(products)}


def test_carry_forward():
    prev = [{"sku": "blessbean:a1", "supplier": "블레스빈", "name": "n", "first_seen": "2026-01-01"},
            {"sku": "momos:m1", "supplier": "모모스", "name": "n", "first_seen": "2026-01-02"}]
    with tempfile.TemporaryDirectory() as d:
        out = Path(d) / "feed.json"
        out.write_text(json.dumps(_payload(prev, [])), encoding="utf-8")

        # blessbean 이 죽은 실행: 옛 상품이 살아남고 momos 는 새 데이터만
        now = [{"sku": "momos:m2", "supplier": "모모스", "name": "n2", "first_seen": "2026-02-01"}]
        p = carry_forward(_payload(now, ["blessbean"]), ["blessbean"], out)
        assert {x["sku"] for x in p["products"]} == {"momos:m2", "blessbean:a1"}
        assert p["count"] == 2 and p["errors"] == ["blessbean"]

        # 정상 실행이면 옛 상품을 되살리지 않는다 (진짜 단종 반영)
        p = carry_forward(_payload(now, []), [], out)
        assert {x["sku"] for x in p["products"]} == {"momos:m2"}

        # 되살아난 공급사는 중복되지 않는다
        both = now + [{"sku": "blessbean:a1", "supplier": "블레스빈", "name": "n", "first_seen": "2026-01-01"}]
        p = carry_forward(_payload(both, ["blessbean"]), ["blessbean"], out)
        assert len(p["products"]) == 2


def test_last_ok_tracks_silent_permanent_death():
    """한 곳만 죽으면 carry_forward 가 count 도 errors 도 조용하게 만든다 —
    last_ok 만이 '커피미업이 하루째 못 긁고 있다'를 들고 있다."""
    momos = {"sku": "momos:m1", "supplier": "모모스", "name": "n", "first_seen": "2026-01-01"}
    cmu = {"sku": "coffeemeup:c1", "supplier": "커피미업", "name": "n", "first_seen": "2026-01-01"}
    with tempfile.TemporaryDirectory() as d:
        out = Path(d) / "feed.json"

        # 1회차: 둘 다 정상 → 둘 다 지금 시각
        p = carry_forward(_payload([momos, cmu], [], "2026-09-08T00:00:00+00:00"),
                          [], out)
        assert p["last_ok"] == {"momos": "2026-09-08T00:00:00+00:00",
                                "coffeemeup": "2026-09-08T00:00:00+00:00"}
        out.write_text(json.dumps(p), encoding="utf-8")

        # 2회차: coffeemeup 만 죽음 → 상품은 물려와서 count 는 그대로,
        # last_ok 만 1회차에 멈춰 있다 (워치독이 이걸 보고 운다)
        p = carry_forward(_payload([momos], ["coffeemeup"], "2026-09-09T00:00:00+00:00"),
                          ["coffeemeup"], out)
        assert p["count"] == 2 and p["errors"] == ["coffeemeup"]
        assert p["last_ok"]["momos"] == "2026-09-09T00:00:00+00:00"
        assert p["last_ok"]["coffeemeup"] == "2026-09-08T00:00:00+00:00"
        out.write_text(json.dumps(p), encoding="utf-8")

        # 3회차: 되살아나면 last_ok 도 따라 올라온다
        p = carry_forward(_payload([momos, cmu], [], "2026-09-09T12:00:00+00:00"),
                          [], out)
        assert p["last_ok"]["coffeemeup"] == "2026-09-09T12:00:00+00:00"


def test_last_ok_first_run_failure_starts_clock_now():
    """처음 추가한 스크레이퍼가 첫 실행부터 실패해도 즉시 울리지 않는다."""
    with tempfile.TemporaryDirectory() as d:
        out = Path(d) / "feed.json"
        p = carry_forward(_payload([], ["newshop"], "2026-09-09T00:00:00+00:00"),
                          ["newshop"], out)
        assert p["last_ok"] == {"newshop": "2026-09-09T00:00:00+00:00"}


if __name__ == "__main__":
    for fn in [v for k, v in sorted(vars().items()) if k.startswith("test_")]:
        fn(); print("ok", fn.__name__)
