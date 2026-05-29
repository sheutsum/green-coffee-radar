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

## 현재 등록된 스크레이퍼 (11곳)

| name | supplier | 플랫폼 | URL 패턴 |
|---|---|---|---|
| `momos` | 모모스커피 | Cafe24 (new skin) | `/product/<slug>/<id>/` |
| `coffeemeup` | 커피미업 | Cafe24 (new skin) | `/product/<slug>/<id>/` |
| `libre` | 커피 리브레 | Cafe24 (old skin) | `/product/detail.html?product_no=<id>` |
| `cobeans` | 코빈즈커피 | Wisa | `/shop/detail.php?pno=<HEX>` |
| `blackroad` | 블랙로드커피 | imweb | `/<cat>/?idx=<id>` |
| `verde` | 베르데 트레이드 | 네이버 스마트스토어 | SSR JSON 파싱 |
| `ryubeans` | 류빈스커피 | 네이버 스마트스토어 | SSR JSON 파싱 |
| `chbean` | 씨에이치빈 | 네이버 스마트스토어 | SSR JSON 파싱 |
| `doan` | 도안 셀렉트 샵 | 네이버 스마트스토어 | SSR JSON 파싱 |
| `cafenogales` | 카페노갈레스 | 식스샵 | 내부 API (`/apis/mall/shop/products-catalog`) |
| `compass` | 콤파스 커피 | 식스샵 | 내부 API (`/apis/mall/shop/products-catalog`) |

플랫폼별로 공통 베이스 클래스로 묶여 있음:
- `Cafe24Scraper` → momos / coffeemeup / libre
- `NaverSmartStoreScraper` → verde / ryubeans / chbean / doan
- `SixshopScraper` → cafenogales / compass
- 단일 사이트: cobeans (Wisa), blackroad (imweb)

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

### Cafe24가 아닌 경우 (네이버 스마트스토어, 자체 솔루션)

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
│   └── momos.py     # 첫 스크레이퍼 (Cafe24 패턴 예제)
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
