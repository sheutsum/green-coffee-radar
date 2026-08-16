# green-coffee-radar

국내 스페셜티 생두 신상품 알림 봇 + **아이폰 앱(PWA)**.
정해진 생두회사들의 카탈로그를 주기적으로 긁어, 처음 보는 SKU가 등장하면
텔레그램으로 푸시한다. 같은 데이터로 `web/feed.json`을 만들어
아이폰 홈 화면에 설치하는 앱(`web/`)에서도 본다. 서버 없이 GitHub Actions에서 도는 구조.

## 아이폰 앱 (PWA)

`web/` 폴더가 설치형 웹앱이다. 아이폰 Safari에서 열고 **공유 → 홈 화면에 추가**하면
아이콘·전체화면·오프라인·새 상품 알림이 되는 앱처럼 동작한다. (별도 앱스토어/맥 불필요)

기능: 전체 카탈로그 목록 · 검색 · 공급사/산지/가공방식 필터 · 정렬 · 신상품(최근 7일) 탭 ·
즐겨찾기 · 상세 보기에서 원본 상품 페이지로 이동 · 새 상품 입고 시 알림.

### 로컬에서 보기 (PC 브라우저)

```bash
python tools/build_feed.py        # web/feed.json 생성 (스크레이퍼 1회 수집)
python -m http.server 8765 -d web # http://127.0.0.1:8765 접속
```

> 아이폰에 "홈 화면 앱"으로 설치하려면 **HTTPS**가 필요하다(서비스워커·오프라인).
> 로컬 `http://`는 PC 브라우저 테스트용. 실제 설치는 아래 GitHub Pages 배포를 쓴다.

### 아이폰에 설치 (GitHub Pages)

1. 이 레포를 GitHub에 푸시한다.
2. 레포 **Settings → Pages → Build and deployment → Source = "GitHub Actions"** 로 지정.
3. Actions 탭에서 워크플로를 한 번 실행(또는 30분 스케줄 대기) → `web/`가 Pages로 배포됨.
4. 배포 URL(예: `https://<계정>.github.io/green-coffee-radar/`)을 **아이폰 Safari**에서 연다.
5. 공유 버튼 → **홈 화면에 추가**. 끝.

피드는 워크플로가 30분마다 `web/feed.json`을 갱신하므로 앱이 자동으로 최신 카탈로그를 받는다.
(앱 → 설정 → "새 상품 알림"을 켜면 입고 시 알림. iOS 16.4+ 에서 설치된 PWA 기준.)

## 빠른 시작 (로컬 테스트)

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Telegram 환경변수 없이도 DRY-RUN 모드로 돌아감 (콘솔에 출력만)
python run.py
```

처음 실행하면 모모스 생두 90여 종이 전부 "new"로 출력됩니다.
이게 baseline이 되고, 두 번째 실행부터는 정말 새로 들어온 것만 출력됩니다.

## Telegram 봇 셋업

1. Telegram에서 `@BotFather` → `/newbot` → 토큰 받기
2. 봇에게 아무 메시지 1개 → `https://api.telegram.org/bot<TOKEN>/getUpdates`
   → `chat.id` 확인
3. 여러 명에게 보내려면 그룹 만들고 봇 초대 (chat_id가 음수로 나옴)
4. 환경변수 또는 GitHub Secrets에 등록:

```bash
export TG_TOKEN="123456:ABC..."
export TG_CHAT="123456789"
python run.py
```

## GitHub Actions 배포

1. 이 디렉토리를 새 GitHub 레포로 푸시
2. Settings → Secrets and variables → Actions → New repository secret:
   - `TG_TOKEN`
   - `TG_CHAT`
3. 처음에는 Actions 탭에서 "Run workflow" 수동 실행 → baseline 만들기
4. 그 뒤로는 2시간마다 자동 실행됨

> ⚠️ GitHub Actions의 scheduled workflow는 60일간 레포에 커밋이 없으면
> 비활성화됩니다. 봇이 매번 seen.sqlite를 커밋하므로 자연스럽게 유지됩니다.

## 현재 등록된 스크레이퍼 (30곳)

| name | supplier | 플랫폼 | 스코프 |
|---|---|---|---|
| `momos` | 모모스커피 | imweb (백오피스 공개 API) | ✅ |
| `coffeemeup` | 커피미업 | Cafe24 (new skin) | 생두 카테고리 |
| `libre` | 커피 리브레 | Cafe24 (old skin) | 생두 카테고리 |
| `sopex` | 소펙스코리아 | Cafe24 | cate_no 24·26·27·66·74 |
| `rnc` | 레햄코리아(RNC) | Cafe24 | cate_no 43~47 (대륙별) |
| `namusairo` | 나무사이로 | Cafe24 | cate_no 24 (GREEN) |
| `coffeespell` | 커피스펠 | Cafe24 | cate_no 25 (생두) |
| `cobeans` | 코빈즈커피 | Wisa | cno1 1037 (신규입고) |
| `almacielo` | 알마시엘로 | Wisa | cno1 1070 (생두찾기) |
| `blackroad` | 블랙로드커피 | imweb | `/<cat>/?idx=<id>` |
| `gsc` | 지에스씨(GSC) | 고도몰 | cateCd 014 |
| `micoffee` | 엠아이커피 | 고도몰 | cateCd 001~004·024 |
| `wbeans` | 더블유빈즈 | 고도몰 | cateCd 024·003·004·005·027 |
| ~~`royal`~~ | 로얄커피코리아 | 고도몰 | cateCd 039 — **IP 차단으로 제외**, 아래 참고 |
| `asianbean` | 에이션빈 | 메이크샵 | xcode 007~011·014·015 |
| `sewoong` | 세웅지씨 | 영카트 | ca_id 10~60·b0 |
| `blessbean` | 블레스빈 | 영카트 | ca_id 2010~2040 |
| `falcon` | 팔콘 마이크로 코리아 | Shopify | `korea-store-all-coffee` 컬렉션 |
| `verde` `ryubeans` `chbean` `doan` `ayantu` `gimisa` | (6곳) | 네이버 스마트스토어 | SSR JSON, 최신 20개 |
| `cafenogales` `compass` `koffeeroute` `hankook` `unico` `ethico` | (6곳) | 식스샵 | 내부 API |

플랫폼별 공통 베이스 클래스:
- `Cafe24Scraper` (base.py) → coffeemeup / libre / sopex / rnc / namusairo / coffeespell
- `GodomallScraper` (godomall.py) → gsc / micoffee / wbeans / royal
- `MakeshopScraper` (makeshop.py) → asianbean
- `YoungcartScraper` (youngcart.py) → sewoong / blessbean
- `WisaScraper` (cobeans.py) → cobeans / almacielo
- `ShopifyScraper` (shopify.py) → falcon
- `NaverSmartStoreScraper` (naver_smartstore.py) → 스마트스토어 6곳
- `SixshopScraper` (sixshop.py) → 식스샵 6곳
- 단일 사이트: blackroad (imweb)

### 점검

```bash
python tools/check_scrapers.py            # 전부 한 번 긁어서 개수/가격/링크 확인
python tools/check_scrapers.py gsc sopex  # 일부만
```

상품 0개는 예외가 아니라 조용한 실패라서, `run.py`가 이를 에러로 취급해
`feed.json`의 `errors`에 넣는다.

### ⚠️ 클라우드에서만 막히는 곳

`royal`(로얄커피코리아)은 **자택 IP에서는 200, GitHub Actions runner IP에서는
403**이다. 마지막 정상 수집은 2026-08-02.

2026-08-16 러너(Azure US, Des Moines)에서 직접 프로브를 돌려 원인을 확정했다:

| 프로브 | 결과 |
|---|---|
| plain curl / 풀 브라우저 헤더 / curl_cffi `chrome131`·`chrome124`·`safari17_0` | 전부 403, 응답 3750바이트로 **동일** |
| 사이트 루트 `/` | 403 — 카탈로그가 아니라 **호스트 전체** 차단 |
| `gsc` (같은 고도몰, 같은 러너) | 200 — 러너 평판/플랫폼 문제 아님 |

403 본문이 고도몰 관리자 기능인 차단 안내 페이지(`.blackout`,
`/admin/gd_share/img/icon_error.png`)다. 즉 봇 탐지가 아니라 **상점주가 관리자에서
켠 해외/특정 IP 차단**이다. UA·헤더·TLS 지문으로는 뚫리지 않는다 — 한국 IP만 된다.

프록시를 붙일 값어치는 없다고 판단해(30곳 중 1곳), `run.py`의 `SCRAPERS`에서
제외했다. 매 실행 `errors`에 쌓이면 진짜 고장 신호가 묻히기 때문이다.
클래스는 남아 있으니 자택에서 `python tools/check_scrapers.py royal` 로 차단이
풀렸는지 확인할 수 있고, 200이 나오면 `SCRAPERS`에 다시 넣으면 된다.

(`falcon`도 한때 429 `local_rate_limited` 로 같은 증상이었으나 지금은 정상.
과거 네이버 스마트스토어는 `chrome131_android` 지문으로 해결 — 지문 문제와 IP
문제는 구분해서 봐야 한다.)

### momos imweb 이전 (2026-08-10 복구)

모모스커피가 Cafe24 → imweb으로 갈아엎어서 `cate_no=162` 카탈로그 URL이
홈으로 301된다(2026-07-28 이후 상품 0개).

imweb 스토어프론트는 상품을 HTML에 렌더하지 않고 백오피스 공개 API를
브라우저에서 호출한다. HTML 어댑터를 다시 짜는 대신 그 API를 직접 쓴다:

    GET https://office.momos.co.kr/api/public/green-beans
    → {"greenBeans": [{prodNo, name, price, origin, process, sca, variety, ...}]}

산지·가공을 서버가 구조화해서 주므로 base.py 이름 휴리스틱보다 정확하다.
상품 URL은 `https://momos.co.kr/shop_view/?idx=<prodNo>`.
같은 백오피스에 `/api/public/products`, `/api/public/origins`,
`/api/public/filters`도 열려 있다.

### 네이버 스마트스토어 주의사항

봇 차단이 까다로워서 데이터센터 IP에서는 403이 날 수 있습니다.
일반 가정·회사 IP에서는 대체로 통하지만, GitHub Actions의 runner IP가
차단되면 **Playwright fallback이 필요**합니다.

증상: `RuntimeError: ... Naver returned 403`
대응: Playwright 의존성 추가 + 헤드리스 브라우저로 페이지 로드 후 HTML 재파싱.

### 식스샵 인증 메모

식스샵 API는 `Authorization: Basic <base64(site_id)>` 방식.
- 카페노갈레스: `site_id=10202`
- 콤파스: `site_id=224244`

다른 식스샵 사이트를 추가하려면, 사이트의 페이지 소스에서
`contents.sixshop.com/uploadedFiles/<숫자>/...` 패턴을 찾아 그 숫자를
`site_id`로 쓰면 됩니다.

콤파스는 카테고리 ID가 아직 확인되지 않아 전체 카탈로그로 호출합니다.
생두 외 상품(원두 등)이 섞이면 콤파스도 브라우저 inspection으로
생두 카테고리 ID를 알아내 `CompassCoffeeScraper.categories`에 추가하세요.

## 스크레이퍼 추가하기

### Cafe24 기반 사이트라면 (대부분)

`scrapers/<name>.py` 파일에 다음 3가지만 채우면 됩니다:

```python
from scrapers.base import Cafe24Scraper

class XxxScraper(Cafe24Scraper):
    name = "xxx"                        # SKU prefix
    supplier_name = "공급사 한글명"
    base = "https://supplier.com"
    catalog_url_template = "{base}/category/.../?page={page}"
    # (선택) 무관 상품 필터, 기본 단위 등
```

그리고 `run.py`의 `SCRAPERS` 리스트에 추가.

여러 카테고리(대륙별 등)로 쪼개져 있으면 `cate_nos = (24, 26, 27)`만 채우면
기본 `catalog_url_template`(`/product/list.html?cate_no={cate}&page={page}`)이
카테고리마다 돌아간다.

### 고도몰 / 메이크샵 / 영카트 / Shopify / 식스샵이라면

해당 베이스 클래스를 상속하고 카테고리 코드만 채운다. 코드 찾는 법:
- 고도몰 · 메이크샵 · 영카트 → 홈페이지 네비게이션의 `cateCd=` / `xcode=` / `ca_id=` 링크
- Shopify → `/collections.json?limit=250`
- 식스샵 → 브라우저 개발자도구 네트워크 탭에서 `/apis/mall/shop/products-catalog`
  요청의 `categories=` 파라미터. **`categories`는 필수**라서 빼면 400이 난다.
  `site_id`는 페이지 소스의 `data-siteNo` 또는 `contents.sixshop.com/uploadedFiles/<숫자>/`.

### 그 외 (네이버 스마트스토어, 자체 솔루션)

`Scraper`를 직접 상속하고 `fetch()` 구현. base.py의 휴리스틱(`guess_origin`, `guess_process`, `parse_price_krw`, `parse_unit_g`)은 그대로 재활용 가능.

## 구조

```
green-coffee-radar/
├── core/
│   ├── models.py    # Product dataclass
│   ├── state.py     # SQLite seen-tracker
│   └── notify.py    # Telegram push (DRY-RUN 지원)
├── scrapers/
│   ├── base.py      # 인터페이스 + 공통 휴리스틱 (origin/process 추정)
│   └── momos.py     # imweb — 백오피스 JSON API 직접 호출
├── tools/
│   ├── build_feed.py # 카탈로그 → web/feed.json (run.py가 재사용)
│   └── make_icons.py # PWA 아이콘 생성
├── web/             # 아이폰 앱 (PWA) — Pages로 배포
│   ├── index.html · styles.css · app.js
│   ├── manifest.webmanifest · sw.js
│   ├── feed.json    # 데이터 (워크플로가 30분마다 갱신)
│   └── icons/
├── run.py           # 스크레이프 → 알림 → feed.json 생성
├── seen.sqlite      # 상태 (레포에 커밋됨)
└── .github/workflows/cron.yml
```
