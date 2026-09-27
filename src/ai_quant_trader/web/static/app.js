const state = { market: "KR", rows: [], query: "", timer: null };
const $ = (id) => document.getElementById(id);

const number = new Intl.NumberFormat("ko-KR");
const usd = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 2 });
const krw = new Intl.NumberFormat("ko-KR", { style: "currency", currency: "KRW", maximumFractionDigits: 0 });

function formatPrice(value, currency) {
  const numeric = Number(value);
  return currency === "KRW" ? krw.format(numeric) : usd.format(numeric);
}

function formatCap(value, currency) {
  const amount = Number(value);
  if (currency === "KRW") {
    if (amount >= 100000000) return `${(amount / 100000000).toLocaleString("ko-KR", { maximumFractionDigits: 1 })}억원`;
    return `${number.format(amount)}원`;
  }
  if (amount >= 1000000000000) return `$${(amount / 1000000000000).toFixed(2)}T`;
  if (amount >= 1000000000) return `$${(amount / 1000000000).toFixed(2)}B`;
  if (amount >= 1000000) return `$${(amount / 1000000).toFixed(2)}M`;
  return `$${number.format(amount)}`;
}

function render() {
  const query = state.query.trim().toLowerCase();
  const visible = state.rows.filter((row) => `${row.name} ${row.symbol}`.toLowerCase().includes(query));
  $("visibleCount").textContent = `${visible.length} / ${state.rows.length || 100}`;
  $("stockRows").innerHTML = visible.map((row) => {
    const change = Number(row.change_percent);
    const direction = change > 0 ? "positive" : change < 0 ? "negative" : "";
    const sign = change > 0 ? "+" : "";
    return `<tr>
      <td class="rank">${row.rank}</td>
      <td><span class="stock-name">${escapeHtml(row.name)}</span><span class="stock-meta">${escapeHtml(row.symbol)} · ${escapeHtml(row.exchange)}</span></td>
      <td class="numeric">${formatPrice(row.price, row.currency)}</td>
      <td class="numeric ${direction}">${sign}${change.toFixed(2)}%</td>
      <td class="numeric">${formatCap(row.market_cap, row.currency)}</td>
      <td class="numeric desktop-only">${number.format(row.volume)}</td>
    </tr>`;
  }).join("");
}

function escapeHtml(value) {
  return String(value).replace(/[&<>'"]/g, (character) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" }[character]));
}

async function load() {
  $("refreshButton").disabled = true;
  $("statusLabel").textContent = "갱신 중";
  $("statusDot").style.background = "#f4b942";
  $("message").hidden = true;
  try {
    const response = await fetch(`/api/market-cap?market=${state.market}&limit=100`, { cache: "no-store" });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || "시장 데이터를 불러오지 못했습니다.");
    state.rows = payload.stocks;
    $("sourceName").textContent = payload.source;
    $("updatedAt").textContent = new Date(payload.as_of).toLocaleString("ko-KR");
    $("delayNote").textContent = payload.delay_note;
    $("statusLabel").textContent = payload.mode === "demo" ? "DEMO · 실제 시세 아님" : "데이터 연결됨";
    $("statusDot").style.background = payload.mode === "demo" ? "#f4b942" : "#6ee7b7";
    render();
  } catch (error) {
    state.rows = [];
    $("statusLabel").textContent = "데이터 미연결";
    $("statusDot").style.background = "#ff6b6b";
    $("sourceName").textContent = "환경 설정 필요";
    $("delayNote").textContent = "실제 API 키는 브라우저가 아니라 서버 환경변수에만 설정합니다.";
    $("message").hidden = false;
    $("message").textContent = `${error.message} 화면만 확인하려면 서버에서 MARKET_DATA_DEMO=true를 사용해 주세요.`;
    render();
  } finally {
    $("refreshButton").disabled = false;
  }
}

document.querySelectorAll(".market-tab").forEach((button) => {
  button.addEventListener("click", () => {
    state.market = button.dataset.market;
    document.querySelectorAll(".market-tab").forEach((tab) => {
      const active = tab === button;
      tab.classList.toggle("is-active", active);
      tab.setAttribute("aria-selected", String(active));
    });
    $("marketName").textContent = state.market === "KR" ? "대한민국 · KRX" : "미국 · NYSE/NASDAQ/AMEX";
    $("rankingTitle").textContent = state.market === "KR" ? "국내 시가총액 순위" : "미국 시가총액 순위";
    load();
  });
});

$("searchInput").addEventListener("input", (event) => { state.query = event.target.value; render(); });
$("refreshButton").addEventListener("click", load);
load();
state.timer = window.setInterval(load, 30000);
