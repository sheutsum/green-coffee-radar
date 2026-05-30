// 생두 레이더 — PWA front-end
// Data source: feed.json produced by tools/build_feed.py

const NEW_DAYS = 7;            // a product is "신상품" if first_seen is within this many days
const DEFAULT_FEED = "./feed.json";

// GitHub Actions workflow that scrapes + rebuilds feed.json (see .github/workflows/cron.yml).
// The PWA can trigger it via workflow_dispatch using a token kept ONLY in this device's
// localStorage — never committed to the public repo / served in the page source.
const GH = { repo: "sheutsum/green-coffee-radar", workflow: "cron.yml", branch: "main" };

const LS = {
  feedUrl: "gcr.feedUrl",
  favorites: "gcr.favorites",
  known: "gcr.knownSkus",
  unack: "gcr.unackSkus",
  notify: "gcr.notify",
  cache: "gcr.feedCache",
  ghToken: "gcr.ghToken",
};

// ---------- tiny storage helpers ----------
const store = {
  getJSON(key, fallback) {
    try { const v = localStorage.getItem(key); return v == null ? fallback : JSON.parse(v); }
    catch { return fallback; }
  },
  setJSON(key, val) { try { localStorage.setItem(key, JSON.stringify(val)); } catch {} },
  get(key, fallback) { const v = localStorage.getItem(key); return v == null ? fallback : v; },
  set(key, val) { try { localStorage.setItem(key, val); } catch {} },
};

// ---------- app state ----------
const state = {
  products: [],
  generatedAt: null,
  suppliers: [],
  view: "all",            // all | new | fav | settings
  search: "",
  filterSupplier: null,   // string or null
  filterOrigin: null,
  filterProcess: null,
  inStockOnly: false,
  sort: "new",            // new | price_asc | price_desc | name
  favorites: new Set(store.getJSON(LS.favorites, [])),
  known: new Set(store.getJSON(LS.known, [])),
  unack: new Set(store.getJSON(LS.unack, [])),
  offline: false,
  refreshing: false,
};

// ---------- DOM refs ----------
const $ = (sel) => document.querySelector(sel);
const el = {
  list: $("#list"),
  loader: $("#loader"),
  empty: $("#emptyState"),
  emptyText: $("#emptyText"),
  title: $("#viewTitle"),
  sub: $("#headerSub"),
  search: $("#searchInput"),
  clearSearch: $("#clearSearch"),
  chips: $("#filterChips"),
  refresh: $("#refreshBtn"),
  tabbar: $("#tabbar"),
  newBadge: $("#newBadge"),
  offlineBanner: $("#offlineBanner"),
  sheet: $("#detailSheet"),
  sheetBody: $("#sheetBody"),
  sheetBackdrop: $("#sheetBackdrop"),
  toast: $("#toast"),
  header: $("#appHeader"),
  main: $("#main"),
};

// ---------- utilities ----------
function feedUrl() { return store.get(LS.feedUrl, DEFAULT_FEED) || DEFAULT_FEED; }

function daysSince(iso) {
  if (!iso) return Infinity;
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return Infinity;
  return (Date.now() - t) / 86400000;
}

function isCatalogNew(p) { return daysSince(p.first_seen) <= NEW_DAYS; }

function fmtWon(n) {
  if (!n || n <= 0) return null;
  return "₩" + n.toLocaleString("ko-KR");
}

function relTime(iso) {
  if (!iso) return "";
  const mins = (Date.now() - Date.parse(iso)) / 60000;
  if (Number.isNaN(mins)) return "";
  if (mins < 1) return "방금";
  if (mins < 60) return `${Math.floor(mins)}분 전`;
  const h = mins / 60;
  if (h < 24) return `${Math.floor(h)}시간 전`;
  const d = h / 24;
  if (d < 30) return `${Math.floor(d)}일 전`;
  return new Date(iso).toLocaleDateString("ko-KR", { month: "long", day: "numeric" });
}

let toastTimer = null;
function toast(msg) {
  el.toast.textContent = msg;
  el.toast.classList.remove("hidden");
  requestAnimationFrame(() => el.toast.classList.add("show"));
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => {
    el.toast.classList.remove("show");
    setTimeout(() => el.toast.classList.add("hidden"), 220);
  }, 2200);
}

function escapeHtml(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

// ---------- feed loading ----------
async function loadFeed({ silent = false, manual = false } = {}) {
  if (state.refreshing) return;
  state.refreshing = true;
  if (!silent) {
    el.loader.classList.remove("hidden");
    el.list.innerHTML = "";
    el.empty.classList.add("hidden");
  }
  el.refresh.classList.add("spinning");

  let data = null;
  let fromNetwork = false;
  try {
    const res = await fetch(feedUrl(), { cache: "no-store" });
    if (!res.ok) throw new Error("HTTP " + res.status);
    data = await res.json();
    fromNetwork = true;
    store.setJSON(LS.cache, data);
    state.offline = false;
  } catch (err) {
    data = store.getJSON(LS.cache, null);
    state.offline = true;
    if (!data) {
      el.loader.classList.add("hidden");
      el.refresh.classList.remove("spinning");
      el.empty.classList.remove("hidden");
      el.emptyText.textContent = "피드를 불러올 수 없습니다. 설정에서 피드 주소를 확인하세요.";
      state.refreshing = false;
      if (manual) toast("피드를 불러올 수 없습니다");
      return;
    }
  }

  const appeared = applyFeed(data, { fromNetwork });
  el.loader.classList.add("hidden");
  el.refresh.classList.remove("spinning");
  state.refreshing = false;

  if (manual) {
    // new arrivals already surface their own toast via notifyNewArrivals
    if (state.offline) toast("오프라인 — 저장된 데이터를 보는 중");
    else if (!appeared) toast("최신 상태입니다 ☕");
  }
}

function applyFeed(data, { fromNetwork }) {
  const products = Array.isArray(data.products) ? data.products : [];
  state.products = products;
  state.generatedAt = data.generated_at || null;
  state.suppliers = data.suppliers || [...new Set(products.map((p) => p.supplier))].sort();

  const currentSkus = products.map((p) => p.sku);
  const firstEverLoad = state.known.size === 0;
  const appeared = currentSkus.filter((s) => !state.known.has(s));
  const newCount = firstEverLoad ? 0 : appeared.length;

  if (firstEverLoad) {
    // baseline: treat everything currently listed as already-known (no notification spam)
    currentSkus.forEach((s) => state.known.add(s));
  } else if (appeared.length) {
    // genuinely new since last visit on this device
    appeared.forEach((s) => {
      state.known.add(s);
      state.unack.add(s);
    });
    notifyNewArrivals(appeared);
  } else {
    currentSkus.forEach((s) => state.known.add(s)); // keep set fresh
  }

  // prune unack/known of skus no longer present to avoid unbounded growth handled lightly
  store.setJSON(LS.known, [...state.known]);
  store.setJSON(LS.unack, [...state.unack]);

  el.offlineBanner.classList.toggle("hidden", !state.offline);
  render();
  return newCount;
}

// ---------- notifications ----------
function notifyNewArrivals(skus) {
  const items = state.products.filter((p) => skus.includes(p.sku));
  const recent = items.filter(isCatalogNew);
  const n = recent.length || items.length;
  if (n <= 0) return;

  const sample = (recent[0] || items[0]);
  toast(`신상품 ${n}종 입고 🆕`);

  if (store.get(LS.notify, "0") === "1" && "Notification" in window &&
      Notification.permission === "granted") {
    const title = `생두 신상품 ${n}종`;
    const body = sample
      ? `${sample.supplier} · ${sample.name}` + (n > 1 ? ` 외 ${n - 1}종` : "")
      : "새로운 생두가 입고되었습니다.";
    try {
      if (navigator.serviceWorker && navigator.serviceWorker.ready) {
        navigator.serviceWorker.ready.then((reg) =>
          reg.showNotification(title, { body, icon: "./icons/icon-192.png", badge: "./icons/icon-192.png", tag: "gcr-new" })
        );
      } else {
        new Notification(title, { body, icon: "./icons/icon-192.png" });
      }
    } catch {}
  }
}

async function enableNotifications() {
  if (!("Notification" in window)) { toast("이 브라우저는 알림을 지원하지 않습니다"); return false; }
  let perm = Notification.permission;
  if (perm === "default") perm = await Notification.requestPermission();
  if (perm === "granted") { store.set(LS.notify, "1"); toast("새 상품 알림이 켜졌습니다"); return true; }
  store.set(LS.notify, "0");
  toast("알림 권한이 거부되었습니다");
  return false;
}

// ---------- filtering / sorting ----------
function visibleProducts() {
  let arr = state.products;

  if (state.view === "fav") arr = arr.filter((p) => state.favorites.has(p.sku));
  if (state.view === "new") arr = arr.filter(isCatalogNew);

  if (state.filterSupplier) arr = arr.filter((p) => p.supplier === state.filterSupplier);
  if (state.filterOrigin) arr = arr.filter((p) => (p.origin || "기타") === state.filterOrigin);
  if (state.filterProcess) arr = arr.filter((p) => (p.process || "기타") === state.filterProcess);
  if (state.inStockOnly) arr = arr.filter((p) => p.in_stock);

  const q = state.search.trim().toLowerCase();
  if (q) {
    arr = arr.filter((p) =>
      (p.name || "").toLowerCase().includes(q) ||
      (p.supplier || "").toLowerCase().includes(q) ||
      (p.origin || "").toLowerCase().includes(q) ||
      (p.process || "").toLowerCase().includes(q));
  }

  const sorted = [...arr];
  switch (state.sort) {
    case "price_asc":
      sorted.sort((a, b) => (a.price_krw || Infinity) - (b.price_krw || Infinity)); break;
    case "price_desc":
      sorted.sort((a, b) => (b.price_krw || 0) - (a.price_krw || 0)); break;
    case "name":
      sorted.sort((a, b) => (a.name || "").localeCompare(b.name || "", "ko")); break;
    default: // new
      sorted.sort((a, b) => (b.first_seen || "").localeCompare(a.first_seen || ""));
  }
  return sorted;
}

// ---------- rendering ----------
const VIEW_TITLES = { all: "생두 레이더", new: "신상품", fav: "즐겨찾기", settings: "설정" };

function render() {
  el.title.textContent = VIEW_TITLES[state.view] || "생두 레이더";

  // tab badge
  const badgeN = state.unack.size;
  el.newBadge.textContent = badgeN > 99 ? "99+" : String(badgeN);
  el.newBadge.classList.toggle("hidden", badgeN === 0);

  if (state.view === "settings") {
    el.chips.classList.add("hidden");
    el.search.parentElement.classList.add("hidden");
    renderSettings();
    el.empty.classList.add("hidden");
    return;
  }
  el.chips.classList.remove("hidden");
  el.search.parentElement.classList.remove("hidden");

  renderChips();

  const items = visibleProducts();
  el.sub.textContent = subtitle(items.length);

  if (items.length === 0) {
    el.list.innerHTML = "";
    el.empty.classList.remove("hidden");
    el.emptyText.textContent =
      state.view === "fav" ? "즐겨찾기한 생두가 없습니다.\n별 아이콘을 눌러 저장하세요." :
      state.view === "new" ? "최근 7일간 새로 올라온 생두가 없습니다." :
      "조건에 맞는 생두가 없습니다.";
    return;
  }
  el.empty.classList.add("hidden");
  el.list.innerHTML = items.map(cardHtml).join("");
}

function subtitle(n) {
  if (state.offline) return `오프라인 · ${n}종`;
  const updated = state.generatedAt ? `${relTime(state.generatedAt)} 업데이트` : "";
  return `${n}종${updated ? " · " + updated : ""}`;
}

function cardHtml(p) {
  const fav = state.favorites.has(p.sku);
  const unseen = state.unack.has(p.sku);
  const isNew = isCatalogNew(p);
  const price = fmtWon(p.price_krw);
  const showPerKg = p.unit_g && p.unit_g !== 1000 && p.price_per_kg > 0;

  const meta = [p.origin, p.process].filter(Boolean)
    .map((m) => `<span class="meta-pill">${escapeHtml(m)}</span>`).join("");

  return `
  <article class="card" data-sku="${escapeHtml(p.sku)}">
    <div class="card-main" data-action="detail">
      <div class="card-top">
        ${unseen ? '<span class="badge-unseen"></span>' : ""}
        <span class="supplier-tag">${escapeHtml(p.supplier)}</span>
        ${isNew ? '<span class="badge-new">NEW</span>' : ""}
      </div>
      <h2 class="card-name">${escapeHtml(p.name)}</h2>
      ${meta ? `<div class="card-meta">${meta}</div>` : ""}
      <div class="card-bottom">
        ${price
          ? `<span class="price">${price}</span>${showPerKg ? `<span class="per-kg">₩${p.price_per_kg.toLocaleString("ko-KR")}/kg</span>` : ""}`
          : '<span class="price unknown">가격 미정</span>'}
        ${p.in_stock ? "" : '<span class="soldout">품절</span>'}
      </div>
    </div>
    <button class="fav-btn ${fav ? "on" : ""}" data-action="fav" aria-label="즐겨찾기">
      <svg viewBox="0 0 24 24" width="22" height="22"><path d="M12 21s-7.5-4.7-10-9.3C.4 8.4 2 5 5.3 5c2 0 3.3 1.1 4.2 2.3l.5.7.5-.7C11.4 6.1 12.7 5 14.7 5 18 5 19.6 8.4 22 11.7 19.5 16.3 12 21 12 21z" fill="${fav ? "currentColor" : "none"}" stroke="currentColor" stroke-width="2"/></svg>
    </button>
  </article>`;
}

// ---------- filter chips ----------
function renderChips() {
  const chips = [];
  chips.push(chip("sort", sortLabel(), false, true));
  chips.push(chip("stock", "재고있음", state.inStockOnly, false));
  chips.push(chip("supplier", state.filterSupplier || "공급사", !!state.filterSupplier, true));
  chips.push(chip("origin", state.filterOrigin || "산지", !!state.filterOrigin, true));
  chips.push(chip("process", state.filterProcess || "가공", !!state.filterProcess, true));
  el.chips.innerHTML = chips.join("");
}

function chip(key, label, active, caret) {
  return `<button class="chip ${active ? "active" : ""}" data-chip="${key}">${escapeHtml(label)}${caret ? '<span class="caret">▾</span>' : ""}</button>`;
}

function sortLabel() {
  return { new: "최신순", price_asc: "가격 낮은순", price_desc: "가격 높은순", name: "이름순" }[state.sort];
}

// ---------- pickers (rendered inside the sheet) ----------
function openPicker(kind) {
  let title, options, current, onPick;
  const counts = countBy(kind);

  if (kind === "sort") {
    title = "정렬";
    options = [["new", "최신순"], ["price_asc", "가격 낮은순"], ["price_desc", "가격 높은순"], ["name", "이름순"]];
    current = state.sort;
    onPick = (v) => { state.sort = v; };
  } else if (kind === "supplier") {
    title = "공급사";
    options = [["", "전체"], ...state.suppliers.map((s) => [s, s])];
    current = state.filterSupplier || "";
    onPick = (v) => { state.filterSupplier = v || null; };
  } else if (kind === "origin") {
    title = "산지";
    const origins = [...new Set(state.products.map((p) => p.origin || "기타"))].sort();
    options = [["", "전체"], ...origins.map((o) => [o, o])];
    current = state.filterOrigin || "";
    onPick = (v) => { state.filterOrigin = v || null; };
  } else if (kind === "process") {
    title = "가공방식";
    const procs = [...new Set(state.products.map((p) => p.process || "기타"))].sort();
    options = [["", "전체"], ...procs.map((o) => [o, o])];
    current = state.filterProcess || "";
    onPick = (v) => { state.filterProcess = v || null; };
  }

  const rows = options.map(([val, label]) => {
    const c = (kind === "sort" || val === "") ? "" : `<span class="cnt">${counts[val] || 0}</span>`;
    return `<div class="picker-item ${val === current ? "sel" : ""}" data-pick="${escapeHtml(val)}">
      <span>${escapeHtml(label)}</span>${c}<span class="check">✓</span></div>`;
  }).join("");

  el.sheetBody.innerHTML = `<h2 class="sheet-name" style="font-size:20px;margin-bottom:6px">${title}</h2>
    <div class="picker-list">${rows}</div>`;
  showSheet();

  el.sheetBody.querySelectorAll("[data-pick]").forEach((node) => {
    node.addEventListener("click", () => {
      onPick(node.getAttribute("data-pick"));
      hideSheet();
      render();
    });
  });
}

function countBy(kind) {
  const counts = {};
  // count within the current view scope (respecting other filters loosely → just view + search)
  let base = state.products;
  if (state.view === "fav") base = base.filter((p) => state.favorites.has(p.sku));
  if (state.view === "new") base = base.filter(isCatalogNew);
  for (const p of base) {
    let key;
    if (kind === "supplier") key = p.supplier;
    else if (kind === "origin") key = p.origin || "기타";
    else if (kind === "process") key = p.process || "기타";
    else continue;
    counts[key] = (counts[key] || 0) + 1;
  }
  return counts;
}

// ---------- detail sheet ----------
function openDetail(sku) {
  const p = state.products.find((x) => x.sku === sku);
  if (!p) return;
  const rows = [];
  rows.push(["공급사", p.supplier]);
  if (p.origin) rows.push(["산지", p.origin]);
  if (p.process) rows.push(["가공방식", p.process]);
  if (p.price_krw > 0) rows.push(["가격", fmtWon(p.price_krw) + (p.unit_g ? ` / ${p.unit_g >= 1000 ? p.unit_g / 1000 + "kg" : p.unit_g + "g"}` : "")]);
  if (p.price_per_kg > 0) rows.push(["kg당", "₩" + p.price_per_kg.toLocaleString("ko-KR")]);
  rows.push(["재고", p.in_stock ? "판매중" : "품절"]);
  if (p.first_seen) rows.push(["입고", relTime(p.first_seen)]);

  const rowsHtml = rows.map(([k, v]) =>
    `<div class="sheet-detail-row"><span class="k">${escapeHtml(k)}</span><span class="v">${escapeHtml(v)}</span></div>`).join("");

  const fav = state.favorites.has(p.sku);
  el.sheetBody.innerHTML = `
    <span class="sheet-supplier">${escapeHtml(p.supplier)}${isCatalogNew(p) ? " · 신상품" : ""}</span>
    <h2 class="sheet-name">${escapeHtml(p.name)}</h2>
    <div class="sheet-rows">${rowsHtml}</div>
    <div class="sheet-actions">
      <button class="sheet-btn secondary" id="sheetFav">${fav ? "★ 즐겨찾기됨" : "☆ 즐겨찾기"}</button>
      <a class="sheet-btn primary" href="${escapeHtml(p.url)}" target="_blank" rel="noopener">상품 보기 ↗</a>
    </div>`;
  showSheet();

  $("#sheetFav").addEventListener("click", () => {
    toggleFav(p.sku);
    $("#sheetFav").textContent = state.favorites.has(p.sku) ? "★ 즐겨찾기됨" : "☆ 즐겨찾기";
  });
}

function showSheet() {
  el.sheet.classList.remove("hidden");
  el.sheetBackdrop.classList.remove("hidden");
  requestAnimationFrame(() => {
    el.sheet.classList.add("show");
    el.sheetBackdrop.classList.add("show");
  });
}
function hideSheet() {
  el.sheet.classList.remove("show");
  el.sheetBackdrop.classList.remove("show");
  setTimeout(() => {
    el.sheet.classList.add("hidden");
    el.sheetBackdrop.classList.add("hidden");
  }, 280);
}

// ---------- settings ----------
function renderSettings() {
  const notifyOn = store.get(LS.notify, "0") === "1" &&
    ("Notification" in window) && Notification.permission === "granted";
  const url = feedUrl();
  const updated = state.generatedAt ? new Date(state.generatedAt).toLocaleString("ko-KR") : "—";
  const tokenSet = !!ghToken();

  el.sub.textContent = "환경설정";
  el.list.innerHTML = `
    <div class="settings-group">
      <h3>알림</h3>
      <div class="setting-row">
        <div><div class="label">새 상품 알림</div><div class="desc">새 생두가 입고되면 알려드립니다</div></div>
        <label class="switch"><input type="checkbox" id="setNotify" ${notifyOn ? "checked" : ""}><span class="track"></span><span class="knob"></span></label>
      </div>
    </div>

    <div class="settings-group">
      <h3>데이터</h3>
      <div class="setting-row"><div class="label">등록 생두</div><div class="value">${state.products.length}종 · ${state.suppliers.length}개 공급사</div></div>
      <div class="setting-row"><div class="label">마지막 업데이트</div><div class="value">${escapeHtml(updated)}</div></div>
      <div class="setting-row" style="flex-direction:column;align-items:stretch;gap:8px">
        <div class="label">피드 주소</div>
        <input class="setting-input" id="setFeedUrl" value="${escapeHtml(url)}" autocapitalize="off" autocorrect="off" spellcheck="false" />
        <div class="desc">스크레이퍼가 만든 feed.json의 위치 (기본값: ./feed.json)</div>
      </div>
    </div>

    <div class="settings-group">
      <h3>수집</h3>
      <div class="setting-row tappable" id="setRunScrape">
        <div><div class="label">지금 새로 수집하기</div><div class="desc">스크레이퍼를 즉시 실행합니다 · 완료까지 1~2분</div></div>
        <div class="value" id="scrapeState">▶ 실행</div>
      </div>
      <div class="setting-row" style="flex-direction:column;align-items:stretch;gap:8px">
        <div class="label">GitHub 토큰</div>
        <input class="setting-input" id="setGhToken" type="password" placeholder="${tokenSet ? "••••••••  (저장됨)" : "github_pat_… 붙여넣기"}" autocapitalize="off" autocorrect="off" spellcheck="false" />
        <div class="desc">${tokenSet ? "✓ 토큰이 이 기기에 저장돼 있습니다. " : ""}<strong>${escapeHtml(GH.repo)}</strong> 레포의 Actions 읽기/쓰기 권한이 있는 fine-grained 토큰. 이 기기에만 저장되며 공개 사이트에는 포함되지 않습니다.</div>
        ${tokenSet ? '<div class="setting-row tappable" id="setClearToken" style="padding:6px 0 0"><div class="label btn-danger">토큰 삭제</div></div>' : ""}
      </div>
      <a class="setting-row tappable" href="https://github.com/${escapeHtml(GH.repo)}/actions/workflows/${escapeHtml(GH.workflow)}" target="_blank" rel="noopener" style="text-decoration:none;color:inherit">
        <div class="label">GitHub Actions에서 열기 ↗</div><div class="value">수동 실행</div>
      </a>
    </div>

    <div class="settings-group">
      <h3>관리</h3>
      <div class="setting-row tappable" id="setResetFav"><div class="label btn-danger">즐겨찾기 비우기</div><div class="value">${state.favorites.size}개</div></div>
      <div class="setting-row tappable" id="setResetBaseline"><div class="label">신상품 기준 초기화</div><div class="value">다시 베이스라인</div></div>
    </div>

    <div class="settings-group">
      <h3>정보</h3>
      <div class="setting-row"><div class="label">앱</div><div class="value">생두 레이더 1.0</div></div>
      <div class="setting-row"><div class="label">추적 공급사</div><div class="value">${escapeHtml(state.suppliers.slice(0, 3).join(", "))} 외</div></div>
    </div>
    <p style="text-align:center;color:var(--text-3);font-size:12px;margin:8px 0 0">홈 화면에 추가하면 앱처럼 사용할 수 있어요</p>
  `;

  $("#setNotify").addEventListener("change", async (e) => {
    if (e.target.checked) {
      const ok = await enableNotifications();
      e.target.checked = ok;
    } else {
      store.set(LS.notify, "0");
      toast("알림이 꺼졌습니다");
    }
  });
  $("#setFeedUrl").addEventListener("change", (e) => {
    const v = e.target.value.trim();
    store.set(LS.feedUrl, v || DEFAULT_FEED);
    toast("피드 주소를 저장했습니다");
    loadFeed();
  });
  $("#setGhToken").addEventListener("change", (e) => {
    const v = e.target.value.trim();
    if (!v) return;
    store.set(LS.ghToken, v);
    e.target.value = "";
    toast("토큰을 이 기기에 저장했습니다");
    renderSettings();
  });
  $("#setRunScrape").addEventListener("click", triggerScrape);
  const clearTokenBtn = $("#setClearToken");
  if (clearTokenBtn) clearTokenBtn.addEventListener("click", () => {
    localStorage.removeItem(LS.ghToken);
    toast("토큰을 삭제했습니다");
    renderSettings();
  });

  $("#setResetFav").addEventListener("click", () => {
    state.favorites.clear();
    store.setJSON(LS.favorites, []);
    renderSettings();
    toast("즐겨찾기를 비웠습니다");
  });
  $("#setResetBaseline").addEventListener("click", () => {
    state.known = new Set(state.products.map((p) => p.sku));
    state.unack.clear();
    store.setJSON(LS.known, [...state.known]);
    store.setJSON(LS.unack, []);
    render();
    toast("신상품 기준을 현재 시점으로 초기화했습니다");
  });
}

// ---------- scraper trigger (GitHub Actions workflow_dispatch) ----------
function ghToken() { return store.get(LS.ghToken, "") || ""; }

function setScrapeState(text) {
  const node = document.getElementById("scrapeState");
  if (node) node.textContent = text;
}

async function ghApi(path, opts = {}) {
  return fetch(`https://api.github.com${path}`, {
    ...opts,
    headers: {
      Accept: "application/vnd.github+json",
      Authorization: `Bearer ${ghToken()}`,
      "X-GitHub-Api-Version": "2022-11-28",
      ...(opts.headers || {}),
    },
  });
}

async function latestRunId() {
  try {
    const res = await ghApi(`/repos/${GH.repo}/actions/workflows/${GH.workflow}/runs?per_page=1`);
    if (!res.ok) return null;
    const j = await res.json();
    const runs = j.workflow_runs || [];
    return runs[0] ? runs[0].id : 0;
  } catch { return null; }
}

let scrapePolling = false;

async function triggerScrape() {
  if (!ghToken()) {
    toast("먼저 GitHub 토큰을 입력하세요");
    return;
  }
  if (scrapePolling) { toast("이미 수집이 진행 중입니다"); return; }

  setScrapeState("시작 중…");
  const beforeId = await latestRunId(); // baseline so we can spot the run we just started

  let res;
  try {
    res = await ghApi(`/repos/${GH.repo}/actions/workflows/${GH.workflow}/dispatches`, {
      method: "POST",
      body: JSON.stringify({ ref: GH.branch }),
    });
  } catch {
    setScrapeState("▶ 실행");
    toast("GitHub에 연결할 수 없습니다");
    return;
  }

  if (res.status === 204) {
    toast("수집을 시작했어요 ☕ 끝나면 자동 새로고침됩니다");
    pollScrape(beforeId);
  } else if (res.status === 401 || res.status === 403) {
    setScrapeState("▶ 실행");
    toast("토큰 권한을 확인하세요 (Actions 읽기/쓰기)");
  } else {
    setScrapeState("▶ 실행");
    toast(`실행 실패 (HTTP ${res.status})`);
  }
}

function pollScrape(beforeId) {
  scrapePolling = true;
  setScrapeState("수집 중…");
  const started = Date.now();
  const TIMEOUT = 6 * 60 * 1000;
  let runId = null;

  const stop = (msg) => {
    scrapePolling = false;
    setScrapeState("▶ 실행");
    if (msg) toast(msg);
  };

  const tick = async () => {
    if (Date.now() - started > TIMEOUT) {
      stop("수집이 오래 걸려요 — 잠시 후 수동으로 새로고침하세요");
      return;
    }
    try {
      if (runId == null) {
        // find the run we just dispatched (newer than the baseline id)
        const res = await ghApi(`/repos/${GH.repo}/actions/workflows/${GH.workflow}/runs?per_page=5`);
        const j = await res.json();
        const runs = j.workflow_runs || [];
        const fresh = runs.find((r) => (beforeId == null ? r.status !== "completed" : r.id > beforeId));
        if (fresh) runId = fresh.id;
      } else {
        const res = await ghApi(`/repos/${GH.repo}/actions/runs/${runId}`);
        const r = await res.json();
        if (r.status === "completed") {
          if (r.conclusion === "success") {
            stop(null);
            toast("수집 완료! 새 피드를 불러옵니다 ✅");
            await loadFeed({ silent: true });
          } else {
            stop(`수집이 ${r.conclusion || "비정상"}(으)로 끝났어요`);
          }
          return;
        }
      }
    } catch { /* transient — keep polling */ }
    setTimeout(tick, 10000);
  };
  setTimeout(tick, 4000);
}

// ---------- actions ----------
function toggleFav(sku) {
  if (state.favorites.has(sku)) state.favorites.delete(sku);
  else state.favorites.add(sku);
  store.setJSON(LS.favorites, [...state.favorites]);
}

function switchView(view) {
  state.view = view;
  el.tabbar.querySelectorAll(".tab").forEach((t) =>
    t.classList.toggle("active", t.getAttribute("data-view") === view));
  el.main.scrollTop = 0;
  if (view === "new" && state.unack.size) {
    state.unack.clear();
    store.setJSON(LS.unack, []);
  }
  render();
}

// ---------- event wiring ----------
function wireEvents() {
  el.refresh.addEventListener("click", () => loadFeed({ manual: true }));
  wirePullToRefresh();

  el.search.addEventListener("input", (e) => {
    state.search = e.target.value;
    el.clearSearch.classList.toggle("hidden", !state.search);
    render();
  });
  el.clearSearch.addEventListener("click", () => {
    state.search = "";
    el.search.value = "";
    el.clearSearch.classList.add("hidden");
    render();
  });

  el.tabbar.querySelectorAll(".tab").forEach((tab) => {
    tab.addEventListener("click", () => switchView(tab.getAttribute("data-view")));
  });

  el.chips.addEventListener("click", (e) => {
    const btn = e.target.closest("[data-chip]");
    if (!btn) return;
    const kind = btn.getAttribute("data-chip");
    if (kind === "stock") { state.inStockOnly = !state.inStockOnly; render(); }
    else openPicker(kind);
  });

  el.list.addEventListener("click", (e) => {
    const card = e.target.closest(".card");
    if (!card) return;
    const sku = card.getAttribute("data-sku");
    const favBtn = e.target.closest('[data-action="fav"]');
    if (favBtn) {
      toggleFav(sku);
      favBtn.classList.toggle("on", state.favorites.has(sku));
      const path = favBtn.querySelector("path");
      if (path) path.setAttribute("fill", state.favorites.has(sku) ? "currentColor" : "none");
      if (state.view === "fav" && !state.favorites.has(sku)) render();
      return;
    }
    openDetail(sku);
  });

  el.sheetBackdrop.addEventListener("click", hideSheet);

  // refresh when returning to the app
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible" && state.products.length) {
      loadFeed({ silent: true });
    }
  });
}

// ---------- pull-to-refresh ----------
function wirePullToRefresh() {
  const main = el.main;
  const ind = document.createElement("div");
  ind.id = "ptr";
  ind.className = "ptr";
  ind.innerHTML = '<div class="ptr-spinner"></div>';
  main.prepend(ind);

  const THRESHOLD = 64;   // pull distance (px) needed to trigger
  const MAX = 96;         // max visible pull
  let startY = 0;
  let dist = 0;
  let pulling = false;

  const reset = (animate) => {
    ind.style.transition = animate ? "height .2s ease" : "none";
    ind.style.height = "0px";
    ind.classList.remove("ready", "loading");
  };

  main.addEventListener("touchstart", (e) => {
    if (main.scrollTop <= 0 && !state.refreshing && e.touches.length === 1) {
      startY = e.touches[0].clientY;
      pulling = true;
      dist = 0;
    } else {
      pulling = false;
    }
  }, { passive: true });

  main.addEventListener("touchmove", (e) => {
    if (!pulling) return;
    const dy = e.touches[0].clientY - startY;
    if (dy <= 0) { pulling = false; reset(true); return; }
    dist = Math.min(MAX, dy * 0.5); // resistance
    ind.style.transition = "none";
    ind.style.height = dist + "px";
    ind.classList.toggle("ready", dist >= THRESHOLD);
  }, { passive: true });

  const finish = async () => {
    if (!pulling) return;
    pulling = false;
    if (dist >= THRESHOLD) {
      ind.style.transition = "height .2s ease";
      ind.style.height = "44px";
      ind.classList.add("loading");
      ind.classList.remove("ready");
      await loadFeed({ silent: true, manual: true });
      reset(true);
    } else {
      reset(true);
    }
  };
  main.addEventListener("touchend", finish, { passive: true });
  main.addEventListener("touchcancel", finish, { passive: true });
}

// ---------- service worker ----------
function registerSW() {
  if ("serviceWorker" in navigator) {
    window.addEventListener("load", () => {
      navigator.serviceWorker.register("./sw.js").catch(() => {});
    });
  }
}

// ---------- init ----------
function init() {
  wireEvents();
  registerSW();
  loadFeed();
}

init();
