// Dashboard for the trading-agents experiment. Plain browser JavaScript, no build step.
//
// Safety: every string from the data files is written with textContent (via el() below), and
// markdown goes through marked and then DOMPurify with a short tag list. Links from data are only
// ever set through httpsHref(), which accepts https URLs and nothing else.
"use strict";

(function () {
  const BASE = (document.querySelector('meta[name="data-base"]') || {}).content ||
    "https://raw.githubusercontent.com/Stasieniec/trading-agents/main/site-data/";
  const DEFAULT_REPO = "Stasieniec/trading-agents";
  const MINUS = "−";
  const DASH = "–";
  const MON = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"];
  const WD = ["SUN", "MON", "TUE", "WED", "THU", "FRI", "SAT"];

  // Canvas needs real colours; the DOM uses the matching .ag-N classes from app.css.
  const AGENT_SLOTS = { "open-quality": 1, "tech-ten": 2, "weird-links": 3, "no-news": 4 };
  const SLOT_COLORS = ["", "#FFB000", "#4FC3F7", "#FF6EC7", "#C9D1CC", "#3DDC84", "#B39DFF", "#FF8A3D", "#7FD1B9"];
  const C = { ink: "#D7DED9", muted: "#6B7A72", hair: "#1E2622", hair2: "#141A17", zero: "#34433B", bench: "#56635C", bg: "#07090A" };
  const BENCH_SHORT = { "bench:spy": "S&P 500", "bench:qqq": "QQQ", "bench:tech-ten-ew": "TECH-10 EW" };

  // NYSE weekday closures, from exchange_calendars XNYS (the calendar the harness uses), read
  // 2026-10-28. It ends 2027-10-28; after that only weekends are skipped.
  const HOLIDAYS = new Set(["2026-01-01", "2026-01-19", "2026-02-16", "2026-04-03", "2026-05-25", "2026-06-19",
    "2026-07-03", "2026-09-07", "2026-11-26", "2026-12-25", "2027-01-01", "2027-01-18", "2027-02-15", "2027-03-26",
    "2027-05-31", "2027-06-18", "2027-07-05", "2027-09-06"]);
  const EARLY_CLOSES = new Set(["2026-11-27", "2026-12-24"]); // 13:00 New York; same lists as src/calendar.js

  const state = { meta: null, equity: null, stats: null, comparison: null, holdings: null, agents: {} };
  let charts = [];
  // Charts are drawn after their container is in the page, so it has a width.
  let pending = [];
  const later = (fn) => pending.push(fn);

  // ---------------------------------------------------------------------------------------------
  // DOM helpers

  function el(tag, attrs, ...children) {
    const node = document.createElement(tag);
    if (attrs) {
      for (const [k, v] of Object.entries(attrs)) {
        if (v == null || v === false) continue;
        if (k === "class") node.className = v;
        else if (k === "text") node.textContent = String(v);
        else if (k === "href") {
          const safe = String(v).startsWith("#") ? String(v) : httpsHref(v);
          if (safe) node.setAttribute("href", safe);
        } else node.setAttribute(k, String(v));
      }
    }
    for (const c of children.flat(Infinity)) {
      if (c == null || c === false) continue;
      node.append(c instanceof Node ? c : String(c));
    }
    return node;
  }

  function svgEl(tag, attrs) {
    const node = document.createElementNS("http://www.w3.org/2000/svg", tag);
    for (const [k, v] of Object.entries(attrs || {})) node.setAttribute(k, String(v));
    return node;
  }

  function httpsHref(u) {
    if (typeof u !== "string") return null;
    try {
      const url = new URL(u.trim());
      return url.protocol === "https:" ? url.href : null;
    } catch {
      return null;
    }
  }

  function extLink(href, ...children) {
    const safe = httpsHref(href);
    if (!safe) return el("span", null, ...children);
    return el("a", { href: safe, rel: "nofollow noopener noreferrer ugc", target: "_blank" }, ...children);
  }

  // ---------------------------------------------------------------------------------------------
  // Formatting

  const isNum = (x) => typeof x === "number" && isFinite(x);
  function signed(x, d) {
    const s = Math.abs(x).toFixed(d);
    if (Number(s) === 0) return (0).toFixed(d);
    return (x < 0 ? MINUS : "+") + s;
  }
  const pct = (x, d = 1) => (isNum(x) ? signed(x * 100, d) + "%" : DASH);
  const pctPlain = (x, d = 0) => (isNum(x) ? (x * 100).toFixed(d).replace("-", MINUS) + "%" : DASH);
  const band = (se) => (isNum(se) ? `±${(2 * se * 100).toFixed(1)}` : "");
  function money(x, d = 0) {
    if (!isNum(x)) return DASH;
    const s = Math.abs(x).toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d });
    return (x < 0 ? MINUS : "") + "$" + s;
  }
  const dir = (x) => (isNum(x) && Number(x.toFixed(4)) > 0 ? "up" : isNum(x) && Number(x.toFixed(4)) < 0 ? "down" : "");
  function parts(iso) {
    const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(iso || ""));
    return m ? { y: Number(m[1]), m: Number(m[2]), d: Number(m[3]) } : null;
  }
  const dShort = (iso) => { const p = parts(iso); return p ? `${p.d} ${MON[p.m - 1]}` : DASH; };
  const dLong = (iso) => { const p = parts(iso); return p ? `${p.d} ${MON[p.m - 1]} ${p.y}` : DASH; };
  function fmtMonth(ym) {
    const m = /^(\d{4})-(\d{2})/.exec(String(ym || ""));
    return m ? `${MON[Number(m[2]) - 1]} ${m[1]}` : "";
  }
  function fmtStamp(iso) {
    const d = new Date(iso);
    if (isNaN(d)) return "";
    const p = (n) => String(n).padStart(2, "0");
    return `${dLong(d.toISOString())} ${p(d.getUTCHours())}:${p(d.getUTCMinutes())} UTC`;
  }
  const upper = (s) => String(s == null ? "" : s).toUpperCase();

  // ---------------------------------------------------------------------------------------------
  // Trading days

  function isoOf(dt) {
    return dt.toISOString().slice(0, 10);
  }
  function isTradingDay(iso) {
    const p = parts(iso);
    if (!p) return false;
    const wd = new Date(Date.UTC(p.y, p.m - 1, p.d)).getUTCDay();
    return wd !== 0 && wd !== 6 && !HOLIDAYS.has(iso);
  }
  function addDays(iso, n) {
    const p = parts(iso);
    return isoOf(new Date(Date.UTC(p.y, p.m - 1, p.d + n)));
  }
  function nextTradingDay(iso) {
    let d = addDays(iso, 1);
    for (let i = 0; i < 15 && !isTradingDay(d); i++) d = addDays(d, 1);
    return d;
  }
  // Trading days after a, up to and including b.
  function tradingDaysBetween(a, b) {
    if (!parts(a) || !parts(b) || b <= a) return 0;
    let n = 0;
    for (let d = addDays(a, 1); d <= b && n < 400; d = addDays(d, 1)) if (isTradingDay(d)) n++;
    return n;
  }
  function amsterdamNow() {
    const f = new Intl.DateTimeFormat("en-CA", { timeZone: "Europe/Amsterdam", year: "numeric", month: "2-digit",
      day: "2-digit", hour: "2-digit", minute: "2-digit", hourCycle: "h23" });
    const o = Object.fromEntries(f.formatToParts(new Date()).map((x) => [x.type, x.value]));
    return { date: `${o.year}-${o.month}-${o.day}`, time: `${o.hour}:${o.minute}` };
  }
  // Sessions run on trading days from 13:30 Amsterdam time, before the US open.
  function nextSession() {
    const m = state.meta;
    if (!m.start_date) return null;
    const now = amsterdamNow();
    const newest = (m.health && m.health.newest_session) || "";
    let d;
    if (m.start_date > now.date) d = m.start_date;
    else if (isTradingDay(now.date) && newest < now.date && now.time < "15:30") d = now.date;
    else d = nextTradingDay(now.date);
    const p = parts(d);
    const wd = WD[new Date(Date.UTC(p.y, p.m - 1, p.d)).getUTCDay()];
    return d === now.date ? "TODAY 13:30 AMS" : `${wd} ${dShort(d)} 13:30 AMS`;
  }

  // ---------------------------------------------------------------------------------------------
  // Markdown, sanitised

  const MD_TAGS = ["p", "br", "strong", "em", "code", "pre", "ul", "ol", "li", "h1", "h2", "h3", "h4",
    "blockquote", "table", "thead", "tbody", "tr", "th", "td", "hr", "a"];
  let hookInstalled = false;
  let mdParser = null;

  function escapeHtml(t) {
    return String(t).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }

  // Raw HTML in the markdown is shown as literal text and images as their alt text, so nothing
  // the model wrote is ever parsed as markup. DOMPurify below is the second line, not the only one.
  function markedInstance() {
    if (!mdParser) {
      mdParser = new window.marked.Marked({
        async: false, gfm: true, breaks: false,
        renderer: {
          html: (token) => escapeHtml(token.text != null ? token.text : token.raw || ""),
          image: (token) => escapeHtml(token.text || ""),
        },
      });
    }
    return mdParser;
  }

  function markdown(src) {
    const box = el("div", { class: "prose" });
    if (!src || !String(src).trim()) return box;
    if (!window.marked || !window.DOMPurify) {
      box.append(el("pre", { text: String(src) }));
      return box;
    }
    if (!hookInstalled) {
      window.DOMPurify.addHook("afterSanitizeAttributes", (node) => {
        if (node.nodeName !== "A") return;
        const safe = httpsHref(node.getAttribute("href"));
        if (!safe) {
          node.removeAttribute("href");
          return;
        }
        node.setAttribute("href", safe);
        node.setAttribute("rel", "nofollow noopener noreferrer ugc");
        node.setAttribute("target", "_blank");
      });
      hookInstalled = true;
    }
    const frag = window.DOMPurify.sanitize(markedInstance().parse(String(src)), {
      ALLOWED_TAGS: MD_TAGS, ALLOWED_ATTR: ["href"], ALLOW_DATA_ATTR: false, ALLOW_ARIA_ATTR: false,
      RETURN_DOM_FRAGMENT: true,
    });
    for (const a of frag.querySelectorAll("a:not([href])")) a.replaceWith(document.createTextNode(a.textContent));
    box.append(frag);
    return box;
  }

  // ---------------------------------------------------------------------------------------------
  // Data

  async function getJSON(path) {
    const r = await fetch(BASE + path, { cache: "no-cache", credentials: "omit", referrerPolicy: "no-referrer" });
    if (!r.ok) {
      const e = new Error(`${path}: HTTP ${r.status}`);
      e.status = r.status;
      throw e;
    }
    return r.json();
  }

  async function loadCore() {
    if (state.meta) return;
    // meta.json first: if it is missing, the rest are too, and one failed request is enough.
    const meta = await getJSON("meta.json");
    const [equity, stats, comparison] = await Promise.all(["equity.json", "stats.json", "comparison.json"].map(getJSON));
    // holdings.json drives the live values; without it the page shows marked numbers only.
    const holdings = await getJSON("holdings.json").catch(() => null);
    Object.assign(state, { meta, equity, stats, comparison, holdings: holdings && holdings.portfolios ? holdings : null });
  }

  async function loadAgent(name) {
    if (!state.agents[name]) state.agents[name] = await getJSON(`agents/${encodeURIComponent(name)}.json`);
    return state.agents[name];
  }

  async function loadAllAgents() {
    await Promise.all(agentsList().map((a) => loadAgent(a.name).catch(() => null)));
  }

  const agentsList = () => (state.meta && Array.isArray(state.meta.agents) ? state.meta.agents : []);
  // The page shows one benchmark, the S&P 500 (SPY). QQQ and the tech-ten basket are still computed.
  const benchList = () => (state.meta && Array.isArray(state.meta.benchmarks) ? state.meta.benchmarks : [])
    .filter((b) => b.name === "bench:spy");
  const repo = () => (state.meta && typeof state.meta.repo === "string" ? state.meta.repo : DEFAULT_REPO);
  const repoUrl = (path) => `https://github.com/${repo()}${path || ""}`;
  const statsOf = (n) => (state.stats && state.stats[n]) || {};
  const daysMarked = () => statsOf("bench:spy").days || Math.max(0, ...agentsList().map((a) => statsOf(a.name).days || 0));

  function slotOf(name) {
    if (AGENT_SLOTS[name]) return AGENT_SLOTS[name];
    const extra = agentsList().map((a) => a.name).filter((n) => !AGENT_SLOTS[n]);
    return Math.min(8, 5 + Math.max(0, extra.indexOf(name)));
  }
  const colorOf = (name) => (String(name).startsWith("bench:") ? C.bench : SLOT_COLORS[slotOf(name)]);
  const agClass = (name) => (String(name).startsWith("bench:") ? "bench" : `ag-${slotOf(name)}`);
  const shortName = (name) => BENCH_SHORT[name] || upper(String(name).replace(/^bench:/, ""));

  function square(name) {
    return el("span", { class: `sq ${agClass(name)}`, "aria-hidden": "true" });
  }

  // ---------------------------------------------------------------------------------------------
  // Charts (uPlot). x is the trading-day index; the first point is the starting cash.

  function rebased(values) {
    const start = isNum(state.equity && state.equity.start_cash) ? state.equity.start_cash : 100000;
    if (!Array.isArray(values)) return null;
    return [100].concat(values.map((v) => (isNum(v) ? (v / start) * 100 : null)));
  }

  const labelText = (l) => (l === "START" || l === "NOW" ? l : dShort(l));

  function chartLabels() {
    const dates = state.equity && Array.isArray(state.equity.dates) ? state.equity.dates : [];
    return dates.length ? ["START"].concat(dates) : null;
  }

  function tickIndices(n, width) {
    const max = Math.max(2, Math.floor(width / 70));
    const step = Math.max(1, Math.ceil(n / max));
    const out = [];
    for (let i = 0; i < n; i += step) out.push(i);
    return out;
  }

  // A legend that is also the hover readout: each key carries the value at the cursor, or at the
  // latest day when the pointer is elsewhere.
  function readout(labels, series, fmt) {
    const day = el("span", { class: "ro-day" });
    const vals = series.map(() => el("span", { class: "ro-val" }));
    const box = el("div", { class: "readout" }, day, series.map((s, i) =>
      el("span", { class: "ro-item" }, el("span", { class: `key ${s.dash ? (s.dash[0] > 2 ? "key-dash" : "key-dot") : ""} ${s.cls || ""}`, "aria-hidden": "true" }),
        el("span", { class: `ro-name ${s.cls || ""}`, text: s.label }), vals[i])));
    const set = (idx) => {
      const i = idx == null ? labels.length - 1 : idx;
      day.textContent = labelText(labels[i]);
      series.forEach((s, k) => { const v = s.values[i]; vals[k].textContent = isNum(v) ? fmt(v) : DASH; });
    };
    set(null);
    return { box, set };
  }

  function lineChart(container, cfg) {
    // cfg: labels, series [{label, values, color, dash, width, fill}], height [phone, desktop], fmt, yRange, markers, onCursor
    if (!window.uPlot) {
      container.append(el("p", { class: "empty", text: "CHART LIBRARY DID NOT LOAD" }));
      return null;
    }
    const font = "11px 'JetBrains Mono', ui-monospace, monospace";
    const xs = cfg.labels.map((_, i) => i);
    const heightFor = () => (container.clientWidth < 560 ? cfg.height[0] : cfg.height[1]);
    const opts = {
      width: Math.max(240, container.clientWidth),
      height: heightFor(),
      padding: [10, 8, 0, 0],
      legend: { show: false },
      scales: { x: { time: false, range: (u, mn, mx) => [mn, Math.max(mx, mn + 1)] }, y: { range: cfg.yRange } },
      series: [{}, ...cfg.series.map((s) => ({
        stroke: s.color, width: s.width || 2, dash: s.dash || undefined, cap: s.dash ? "round" : "butt",
        fill: s.fill || undefined, spanGaps: false, points: { show: false },
      }))],
      axes: [
        { stroke: C.muted, font, gap: 6, size: 26, grid: { show: false }, ticks: { show: false },
          splits: (u) => tickIndices(cfg.labels.length, u.width),
          values: (u, splits) => splits.map((i) => labelText(cfg.labels[i])) },
        { stroke: C.muted, font, gap: 8, size: 40, grid: { stroke: C.hair2, width: 1 }, ticks: { show: false },
          incrs: cfg.incrs || [1, 2, 5, 10, 20, 25, 50, 100],
          values: (u, splits) => splits.map(cfg.axisFmt || cfg.fmt) },
      ],
      cursor: {
        y: false, drag: { x: false, y: false, setScale: false },
        points: { size: 8, width: 2, stroke: () => C.bg, fill: (u, si) => (cfg.series[si - 1] || {}).color || C.ink },
      },
      hooks: {
        setCursor: [(u) => cfg.onCursor && cfg.onCursor(u.cursor.idx)],
        drawAxes: [(u) => {
          if (cfg.baseline == null) return;
          const ctx = u.ctx;
          const y = Math.round(u.valToPos(cfg.baseline, "y", true)) + 0.5;
          ctx.save();
          ctx.strokeStyle = C.zero;
          ctx.lineWidth = 1 * (window.uPlot.pxRatio || 1);
          ctx.beginPath();
          ctx.moveTo(u.bbox.left, y);
          ctx.lineTo(u.bbox.left + u.bbox.width, y);
          ctx.stroke();
          ctx.restore();
        }],
        draw: [(u) => {
          if (!cfg.markers || !cfg.markers.length) return;
          const ctx = u.ctx;
          const r = window.uPlot.pxRatio || 1;
          ctx.save();
          ctx.font = `${10 * r}px 'JetBrains Mono', monospace`;
          ctx.textBaseline = "top";
          for (const m of cfg.markers) {
            const x = Math.round(u.valToPos(m.idx, "x", true)) + 0.5;
            ctx.strokeStyle = m.color;
            ctx.lineWidth = 1 * r;
            ctx.setLineDash([2 * r, 3 * r]);
            ctx.beginPath();
            ctx.moveTo(x, u.bbox.top);
            ctx.lineTo(x, u.bbox.top + u.bbox.height);
            ctx.stroke();
            ctx.fillStyle = m.color;
            const w = ctx.measureText(m.text).width;
            const tx = x + 4 * r + w > u.bbox.left + u.bbox.width ? x - 4 * r - w : x + 4 * r;
            ctx.fillText(m.text, tx, u.bbox.top + 2 * r);
          }
          ctx.restore();
        }],
      },
    };
    const u = new window.uPlot(opts, [xs, ...cfg.series.map((s) => s.values)], container);
    const ro = new ResizeObserver(() => {
      const w = Math.max(240, container.clientWidth);
      if (Math.abs(w - u.width) > 1) u.setSize({ width: w, height: heightFor() });
    });
    ro.observe(container);
    charts.push({ destroy: () => { ro.disconnect(); u.destroy(); } });
    return u;
  }

  function sparkline(values, color) {
    const W = 560, H = 120;
    const svg = svgEl("svg", { viewBox: `0 0 ${W} ${H}`, preserveAspectRatio: "none", "aria-hidden": "true", class: "spark" });
    const pts = (values || []).map((v, i) => [i, v]).filter(([, v]) => isNum(v));
    if (pts.length < 2) {
      svg.append(svgEl("line", { x1: 0, y1: H / 2, x2: W, y2: H / 2, stroke: C.hair, "vector-effect": "non-scaling-stroke" }));
      return svg;
    }
    const vs = pts.map(([, v]) => v).concat([100]);
    const lo = Math.min(...vs), hi = Math.max(...vs);
    const span = hi - lo || 1;
    const n = values.length - 1 || 1;
    const y = (v) => (H - 6 - ((v - lo) / span) * (H - 12)).toFixed(1);
    svg.append(svgEl("line", { x1: 0, y1: y(100), x2: W, y2: y(100), stroke: C.hair, "vector-effect": "non-scaling-stroke" }));
    svg.append(svgEl("polyline", { fill: "none", stroke: color, "stroke-width": 2, "vector-effect": "non-scaling-stroke",
      points: pts.map(([i, v]) => `${((i / n) * W).toFixed(1)},${y(v)}`).join(" ") }));
    return svg;
  }

  // ---------------------------------------------------------------------------------------------
  // Shared pieces

  function block(id, title, ...children) {
    return el("section", { class: "block", id }, title ? el("h2", null, title) : null, ...children);
  }
  const empty = (text) => el("p", { class: "empty", text });
  const scroll = (table, label) => el("div", { class: "scroll", role: "region", "aria-label": label, tabindex: "0" }, table);
  function table(cls, head, rows, label) {
    return scroll(el("table", { class: `grid-table ${cls || ""}` },
      el("thead", null, el("tr", null, head.map(([h, num]) => el("th", { scope: "col", class: num ? "num" : null, text: h })))),
      el("tbody", null, rows)), label);
  }
  const td = (text, cls) => el("td", { class: cls || null, text });
  const num = (text, extra) => el("td", { class: `num ${extra || ""}`, text });
  function more(rows, limit, render, label) {
    const out = el("div");
    out.append(render(rows.slice(0, limit)));
    if (rows.length > limit) out.append(el("details", { class: "more" }, el("summary", { text: `${rows.length - limit} MORE` }), render(rows.slice(limit))));
    return out;
  }

  function renderBanner() {
    const box = document.getElementById("banner");
    box.replaceChildren();
    const h = state.meta && state.meta.health;
    if (!h || !h.stale) return;
    box.append(el("div", { class: "banner", role: "alert" },
      el("strong", { text: "■ STALE" }),
      el("span", { text: h.newest_session ? `NEWEST SESSION ${dShort(h.newest_session)}` : "NO SESSION YET" }),
      el("span", { text: `DUE ${dShort(h.last_expected_session)}` }),
      el("a", { href: "#health", text: "HEALTH →" })));
  }

  function renderMasthead(active) {
    const m = state.meta;
    const n = daysMarked();
    document.getElementById("dayline").textContent = !m || !m.start_date ? "NOT STARTED"
      : n ? `DAY ${n} · ${dShort(m.last_marked)}` : `DAY 1 · ${dShort(m.start_date)}`;
    const nav = document.getElementById("nav");
    nav.replaceChildren();
    const first = agentsList()[0];
    const items = [["#", "OVERVIEW", "overview"], [first ? `#agent/${encodeURIComponent(first.name)}` : "#", "AGENTS", "agent"],
      ["#compare", "COMPARE", "compare"], ["#health", "HEALTH", "health"], ["#how", "METHOD", "how"]];
    for (const [href, text, key] of items) {
      nav.append(el("a", { href, class: active === key ? "active" : null, "aria-current": active === key ? "page" : null, text }));
    }
    const g = document.getElementById("generated");
    g.textContent = m && m.generated_at ? `BUILT ${fmtStamp(m.generated_at)}` : "";
  }

  // ---------------------------------------------------------------------------------------------
  // Live values during the US session. holdings.json says what each portfolio holds; the Worker's
  // /api/live and /api/intraday give IEX prices for exactly those symbols. Marked numbers (since
  // start, vs SPY) stay as they are; live numbers are labelled LIVE and measured against basis.

  const LIVE_MS = 1000;
  const PAUSED_MS = 15000; // while the agents run, the Worker answers without calling Alpaca
  const INTRA_MS = 60000;
  const live = { configured: null, error: null, prices: {}, latest: null, intraday: null, lastLive: 0, lastIntra: 0, busy: false };
  let liveSlots = [];
  let liveTimer = null;

  function nyNow() {
    const f = new Intl.DateTimeFormat("en-CA", { timeZone: "America/New_York", year: "numeric", month: "2-digit",
      day: "2-digit", hour: "2-digit", minute: "2-digit", hourCycle: "h23" });
    const o = Object.fromEntries(f.formatToParts(new Date()).map((x) => [x.type, x.value]));
    return { date: `${o.year}-${o.month}-${o.day}`, time: `${o.hour}:${o.minute}` };
  }
  function marketOpen() {
    const n = nyNow();
    return isTradingDay(n.date) && n.time >= "09:30" && n.time < (EARLY_CLOSES.has(n.date) ? "13:00" : "16:00");
  }
  const nyFmt = new Intl.DateTimeFormat("en-GB", { timeZone: "America/New_York", hour: "2-digit", minute: "2-digit", hourCycle: "h23" });
  const nyClock = (ms) => nyFmt.format(new Date(ms));

  // A function that repaints one live element; it runs now and after every poll.
  function liveSlot(fn) {
    liveSlots.push(fn);
    try { fn(); } catch { /* a slot must never break the page */ }
  }
  function paintLive() {
    for (const fn of liveSlots) {
      try { fn(); } catch { /* ignore */ }
    }
  }

  function barPrice(sym) {
    const b = live.intraday && live.intraday.bars && live.intraday.bars[sym];
    return Array.isArray(b) && b.length ? b[b.length - 1][1] : null;
  }
  function closePrice(sym) {
    for (const a of Object.values(state.agents)) {
      const p = a && Array.isArray(a.positions) && a.positions.find((x) => x.ticker === sym);
      if (p && isNum(p.last_close)) return p.last_close;
    }
    return null;
  }
  // Latest trade, else the latest 5-minute bar, else the last marked close.
  function priceOf(sym) {
    const p = live.prices[sym];
    if (p && isNum(p.price)) return p.price;
    const b = barPrice(sym);
    return isNum(b) ? b : closePrice(sym);
  }
  const portfolio = (name) => (state.holdings && state.holdings.portfolios && state.holdings.portfolios[name]) || null;
  const hasLive = () => live.configured === true && (Object.keys(live.prices).length > 0 || !!live.intraday);

  function liveValue(name) {
    const h = portfolio(name);
    if (!h || !isNum(h.cash)) return null;
    let v = h.cash;
    for (const [sym, qty] of Object.entries(h.positions || {})) {
      const px = priceOf(sym);
      if (!isNum(px) || !isNum(qty)) return null;
      v += qty * px;
    }
    return v;
  }
  function liveChange(name) {
    const h = portfolio(name);
    const v = liveValue(name);
    if (!h || !isNum(v) || !isNum(h.basis) || !h.basis) return null;
    return { value: v, diff: v - h.basis, pct: v / h.basis - 1 };
  }
  async function fetchApi(path) {
    const r = await fetch(path, { cache: "no-store", credentials: "omit" });
    if (!r.ok) await r.text().catch(() => ""); // read it, so the request completes
    if (r.status === 503) {
      live.configured = false;
      return null;
    }
    if (!r.ok) {
      live.error = r.status;
      return null;
    }
    live.configured = true;
    live.error = null;
    return r.json();
  }

  async function pollLive(force) {
    if (!state.holdings || live.configured === false || live.busy) return;
    live.busy = true;
    const now = Date.now();
    try {
      if (force || now - live.lastLive >= (live.paused ? PAUSED_MS : LIVE_MS) - 500) {
        live.lastLive = now;
        const j = await fetchApi("/api/live");
        live.paused = !!(j && j.paused);
        if (j && j.prices && typeof j.prices === "object") {
          for (const [sym, p] of Object.entries(j.prices)) {
            const t = Date.parse(p && p.time);
            if (p && isNum(p.price) && isFinite(t)) {
              live.prices[sym] = { price: p.price, t };
              if (!live.latest || t > live.latest) live.latest = t;
            }
          }
        }
      }
      if (live.configured && (force || now - live.lastIntra >= INTRA_MS - 500)) {
        live.lastIntra = now;
        const j = await fetchApi("/api/intraday");
        if (j && j.bars && typeof j.bars === "object") live.intraday = j;
        if (j && j.paused) live.paused = true;
      }
    } catch {
      live.error = "network";
    } finally {
      live.busy = false;
    }
    paintLive();
  }

  // Polls only while the market is open and the tab is visible. Outside hours one poll shows the
  // last prices, then it stops.
  function scheduleLive() {
    clearTimeout(liveTimer);
    if (live.configured === false || !state.holdings || document.hidden || !marketOpen()) return;
    liveTimer = setTimeout(async () => {
      await pollLive(false);
      scheduleLive();
    }, live.paused ? PAUSED_MS : LIVE_MS);
  }

  async function startLive() {
    if (!state.holdings || live.configured === false) return;
    if (!live.lastLive) await pollLive(true);
    else if (marketOpen() && Date.now() - live.lastLive >= LIVE_MS) await pollLive(false);
    scheduleLive();
  }

  document.addEventListener("visibilitychange", async () => {
    if (document.hidden) {
      clearTimeout(liveTimer);
    } else if (state.holdings && marketOpen()) {
      await pollLive(false);
      scheduleLive();
    }
  });

  // Status item: LIVE ● 13:29 NY while polling, CLOSED · LAST 16:00 NY after hours.
  function liveStatus() {
    const box = el("span", { class: "st-item" });
    liveSlot(() => {
      box.replaceChildren();
      if (!state.holdings || live.configured === false) return;
      const open = marketOpen();
      const t = live.latest ? `${nyClock(live.latest)} NY` : DASH;
      if (live.error && !hasLive()) box.append(el("span", { class: "label", text: "LIVE" }), " ", el("span", { class: "down", text: "UNAVAILABLE" }));
      else if (open && live.paused) box.append(el("span", { class: "label", text: "LIVE" }), " ", el("span", { class: "muted", text: "PAUSED · AGENTS RUNNING" }), live.latest ? ` · LAST ${t}` : "");
      else if (open) box.append(el("span", { class: "label", text: "LIVE" }), " ", el("span", { class: "up", text: "●" }), ` ${t}`);
      else box.append(el("span", { class: "label", text: "LIVE" }), " ", el("span", { class: "muted", text: "CLOSED" }), live.latest ? ` · LAST ${t}` : "");
    });
    return box;
  }

  const startCash = () => (isNum(state.equity && state.equity.start_cash) ? state.equity.start_cash : 100000);

  // What a portfolio is worth now: cash plus positions at live prices while they exist, else at the
  // last close. Every percentage in a headline comes from this one number.
  function valueNow(name) {
    const lv = hasLive() ? liveValue(name) : null;
    if (isNum(lv)) return { value: lv, live: true };
    const ser = ((state.equity && state.equity.series) || {})[name];
    const last = Array.isArray(ser) ? [...ser].reverse().find(isNum) : null;
    if (isNum(last)) return { value: last, live: false };
    const a = state.agents[name];
    return { value: a && isNum(a.equity) ? a.equity : startCash(), live: false };
  }
  const sinceStart = (name) => valueNow(name).value / startCash() - 1;

  // Value, return since start (big), today's change, and the gap to the S&P 500 over the same time.
  function headline(name) {
    const box = el("div", { class: "headline" });
    let prev = null;
    liveSlot(() => {
      const v = valueNow(name);
      const r = sinceStart(name);
      const today = v.live ? liveChange(name) : null;
      const tick = v.live && prev !== null && Math.abs(v.value - prev) >= 0.005 ? (v.value > prev ? " tick-up" : " tick-down") : "";
      prev = v.value;
      box.replaceChildren(
        el("div", { class: "hl-value" + tick, text: "$" + v.value.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) }),
        el("div", { class: `big ${dir(r) === "down" ? "down" : ""}`, text: pct(r) }),
        el("div", { class: "hl-sub" }, el("span", { class: "label", text: "SINCE START" }),
          today ? el("span", null, el("span", { class: "label", text: " · TODAY " }), el("span", { class: dir(today.pct), text: pct(today.pct, 2) })) : null));
    });
    return box;
  }

  // The agent's return since start minus the S&P 500's over the same days, live while prices are.
  function vsSp500(name) {
    const span = el("span");
    liveSlot(() => {
      const x = sinceStart(name) - sinceStart("bench:spy");
      span.className = dir(x);
      span.textContent = pct(x);
    });
    return span;
  }

  // Cells for the positions tables: live price and P&L against average cost.
  function livePriceCells(ticker, avgCost, short) {
    const price = el("td", { class: "num" });
    const pnl = el("td", { class: "num" });
    liveSlot(() => {
      const p = hasLive() ? live.prices[ticker] : null;
      const px = p ? p.price : hasLive() ? priceOf(ticker) : null;
      price.textContent = isNum(px) ? money(px, 2) : DASH;
      const r = isNum(px) && isNum(avgCost) && avgCost ? (short ? (avgCost - px) / avgCost : px / avgCost - 1) : null;
      pnl.textContent = isNum(r) ? pct(r) : DASH;
      pnl.className = `num ${dir(r)}`;
    });
    return [price, pnl];
  }

  // Standings cells: live value and today's change against basis.
  function liveCells(name) {
    const v = el("td", { class: "num" });
    const c = el("td", { class: "num" });
    liveSlot(() => {
      const ch = hasLive() ? liveChange(name) : null;
      v.textContent = ch ? money(ch.value) : DASH;
      c.textContent = ch ? pct(ch.pct, 2) : DASH;
      c.className = `num ${ch ? dir(ch.pct) : ""}`;
    });
    return [v, c];
  }

  // Percent change on the y axis, 0 = the start of the chosen period.
  const PCT_INCRS = [0.05, 0.1, 0.2, 0.5, 1, 2, 5, 10, 20, 50];
  function yRangeAround0(u, min, max) {
    const lo = Math.min(isNum(min) ? min : 0, 0), hi = Math.max(isNum(max) ? max : 0, 0);
    const pad = Math.max((hi - lo) * 0.1, 0.1);
    return [lo - pad, hi + pad];
  }
  const pctAxis = (v) => (Math.abs(v) < 1e-9 ? "0%" : (v > 0 ? "+" : MINUS) + Math.abs(v).toFixed(Math.abs(v - Math.round(v)) < 1e-9 ? 0 : Math.abs(v * 10 - Math.round(v * 10)) < 1e-9 ? 1 : 2) + "%");
  const pctVal = (v) => (isNum(v) ? signed(v, 2) + "%" : DASH);

  // DAY: every portfolio's change since the previous close, through today, so it matches the TODAY
  // figure in the headlines. A portfolio whose holdings were completed during the day starts there.
  function daySeries(names) {
    const j = live.intraday;
    const openMs = j && Date.parse(j.open);
    if (!j || !isFinite(openMs)) return null;
    const bars = j.bars || {};
    const ts = new Set();
    for (const list of Object.values(bars)) for (const [t] of list) ts.add(t + 300); // bar end
    const lastBarEnd = Math.max(0, ...ts);
    // The latest trade extends the curve past the last finished 5-minute bar.
    if (live.latest && live.latest / 1000 > lastBarEnd) ts.add(Math.floor(live.latest / 1000));
    const xs = [...ts].filter((t) => t * 1000 >= openMs).sort((a, b) => a - b);
    if (!xs.length) return null;
    const priceAt = (sym, t) => {
      if (t > lastBarEnd && live.prices[sym]) return live.prices[sym].price;
      const list = bars[sym];
      if (!Array.isArray(list) || !list.length) return priceOf(sym);
      let v = list[0][1];
      for (const [bt, c] of list) {
        if (bt + 300 <= t) v = c;
        else break;
      }
      return v;
    };
    const series = names.map((name) => {
      const h = portfolio(name);
      if (!h || !isNum(h.basis) || !h.basis) return null;
      const since = h.since ? Date.parse(h.since) : NaN;
      const start = Math.max(openMs, isFinite(since) ? since : openMs) / 1000;
      const values = xs.map((t) => {
        if (t < start) return null;
        let v = h.cash;
        for (const [sym, qty] of Object.entries(h.positions || {})) {
          const px = priceAt(sym, t);
          if (!isNum(px)) return null;
          v += qty * px;
        }
        return (v / h.basis - 1) * 100;
      });
      return { name, values };
    }).filter(Boolean);
    return { xs, open: openMs, series };
  }

  // WEEK, MONTH, ALL: daily closes, plus a NOW point while live prices are newer than the last close.
  function dailySeries(names, days) {
    const eq = state.equity || {};
    const dates = Array.isArray(eq.dates) ? eq.dates : [];
    const labels = ["START"].concat(dates);
    const raw = {};
    for (const n of names) raw[n] = [startCash()].concat(dates.map((_, i) => ((eq.series || {})[n] || [])[i]));
    const today = live.intraday && live.intraday.trading_day;
    if (hasLive() && today && (!dates.length || today > dates[dates.length - 1])) {
      labels.push("NOW");
      for (const n of names) raw[n].push(liveValue(n));
    }
    const from = days ? Math.max(0, labels.length - 1 - days) : 0;
    const out = { labels: labels.slice(from), series: [] };
    for (const n of names) {
      const vs = raw[n].slice(from);
      const base = vs.find(isNum);
      out.series.push({ name: n, values: vs.map((v) => (isNum(v) && base ? (v / base - 1) * 100 : null)) });
    }
    return out;
  }

  const RANGES = [["day", "DAY"], ["week", "WEEK"], ["month", "MONTH"], ["all", "ALL"]];
  const RANGE_DAYS = { week: 5, month: 21, all: null };

  function perfFigure(names) {
    const fig = el("figure", { class: "block figure perf" });
    let range = "day";
    try { range = localStorage.getItem("perf-range") || "day"; } catch { /* storage blocked */ }
    if (!RANGES.some(([k]) => k === range)) range = "day";
    const buttons = RANGES.map(([k, label]) => el("button", { type: "button", class: "seg-btn", "data-range": k, text: label }));
    const seg = el("div", { class: "seg", role: "group", "aria-label": "Period" }, buttons);
    const roSlot = el("div", { class: "ro-slot" });
    const head = el("div", { class: "fig-head" }, el("h2", null, "PERFORMANCE", el("span", { class: "h2-sub", text: " % CHANGE" })), seg);
    const box = el("div", { class: "chart" });
    const note = el("p", { class: "fig-note" });
    fig.append(head, roSlot, box, note);
    let chart = null, entry = null, defs = null, ro = null, shown = null, labels = null;

    const defsFor = (list) => list.map((s) => {
      const bench = String(s.name).startsWith("bench:");
      return { name: s.name, label: shortName(s.name), values: s.values, color: colorOf(s.name), dash: bench ? [2, 4] : null,
        width: bench ? 1.5 : 2, cls: agClass(s.name) };
    });
    function reset() {
      if (entry) {
        entry.destroy();
        const i = charts.indexOf(entry);
        if (i >= 0) charts.splice(i, 1);
      }
      chart = entry = defs = ro = labels = null;
      box.replaceChildren();
      roSlot.replaceChildren();
      note.textContent = "";
    }
    function paint() {
      for (const b of buttons) b.setAttribute("aria-pressed", String(b.dataset.range === range));
      if (shown !== range) reset();
      shown = range;
      if (range === "day") {
        const d = hasLive() ? daySeries(names) : null;
        if (!d || !d.series.length) {
          if (!chart) note.textContent = live.configured === false ? "NO LIVE PRICES" : "NO PRICES FOR TODAY YET";
          return;
        }
        note.textContent = "0 = PREVIOUS CLOSE";
        const late = d.series.filter((s) => { const h = portfolio(s.name); return h && h.since && Date.parse(h.since) > d.open; });
        if (late.length) note.textContent += " · STARTED LATER: " + late.map((s) => `${shortName(s.name)} ${nyClock(Date.parse(portfolio(s.name).since))} NY`).join(" · ");
        if (!defs) defs = defsFor(d.series);
        else for (const def of defs) def.values = (d.series.find((s) => s.name === def.name) || { values: d.xs.map(() => null) }).values;
        const labelAt = (i) => (d.xs[i] ? `${nyClock(d.xs[i] * 1000)} NY` : DASH);
        if (!ro) {
          ro = readoutWith(defs, pctVal, labelAt);
          roSlot.append(ro.box);
        }
        ro.relabel(labelAt, d.xs.length);
        const data = [d.xs, ...defs.map((s) => s.values)];
        if (chart) {
          chart.setData(data);
          ro.set(null);
          return;
        }
        const closeMs = d.open + (EARLY_CLOSES.has(String(live.intraday.trading_day)) ? 3.5 : 6.5) * 3600e3;
        chart = timeChart(box, { data, series: defs, open: d.open / 1000, close: closeMs / 1000, onCursor: (idx) => ro.set(idx) });
        entry = charts[charts.length - 1];
        return;
      }
      const d = dailySeries(names, RANGE_DAYS[range]);
      if (d.labels.length < 2) {
        if (!chart) note.textContent = "NO CLOSES YET";
        return;
      }
      note.textContent = `0 = ${labelText(d.labels[0])}${d.labels[0] === "START" ? "" : " CLOSE"}${d.labels.includes("NOW") ? " · NOW IS LIVE" : ""}`;
      if (chart && labels && labels.length === d.labels.length) {
        for (const def of defs) def.values = (d.series.find((s) => s.name === def.name) || {}).values;
        chart.setData([d.labels.map((_, i) => i), ...defs.map((s) => s.values)]);
        ro.set(null);
        return;
      }
      if (chart) reset();
      labels = d.labels;
      defs = defsFor(d.series);
      ro = readout(labels, defs, pctVal);
      roSlot.append(ro.box);
      chart = lineChart(box, { labels, height: [240, 300], series: defs, fmt: pctVal, axisFmt: pctAxis, incrs: PCT_INCRS,
        yRange: yRangeAround0, baseline: 0, onCursor: (idx) => ro.set(idx) });
      entry = charts[charts.length - 1];
    }
    seg.addEventListener("click", (e) => {
      const b = e.target.closest("button[data-range]");
      if (!b || b.dataset.range === range) return;
      range = b.dataset.range;
      try { localStorage.setItem("perf-range", range); } catch { /* storage blocked */ }
      paint();
    });
    // The chart needs its container laid out first, then follows the live prices.
    later(() => liveSlot(paint));
    return fig;
  }

  // Readout whose labels come from a function, for the time axis.
  function readoutWith(series, fmt, labelAt) {
    const day = el("span", { class: "ro-day" });
    const vals = series.map(() => el("span", { class: "ro-val" }));
    const box = el("div", { class: "readout" }, day, series.map((s, i) =>
      el("span", { class: "ro-item" }, el("span", { class: `key ${s.dash ? (s.dash[0] > 2 ? "key-dash" : "key-dot") : ""} ${s.cls || ""}`, "aria-hidden": "true" }),
        el("span", { class: `ro-name ${s.cls || ""}`, text: s.label }), vals[i])));
    let at = labelAt, n = 0;
    const set = (idx) => {
      const i = idx == null ? n - 1 : idx;
      day.textContent = at(i);
      series.forEach((s, k) => { const v = s.values[i]; vals[k].textContent = isNum(v) ? fmt(v) : DASH; });
    };
    return { box, set, relabel: (fn, len) => { at = fn; n = len; set(null); } };
  }

  function timeChart(container, cfg) {
    if (!window.uPlot) return null;
    const font = "11px 'JetBrains Mono', ui-monospace, monospace";
    const heightFor = () => (container.clientWidth < 560 ? 220 : 280);
    // New York hours fall on whole UTC hours, so hourly ticks are multiples of 3600 s.
    const hourSplits = (u, axisIdx, min, max) => {
      const step = u.width < 420 ? 7200 : 3600;
      const out = [];
      for (let t = Math.ceil(min / 3600) * 3600; t <= max; t += step) out.push(t);
      return out;
    };
    const opts = {
      width: Math.max(240, container.clientWidth),
      height: heightFor(),
      padding: [10, 24, 0, 0],
      legend: { show: false },
      scales: {
        x: { time: false, range: () => [cfg.open, cfg.close] },
        y: { range: yRangeAround0 },
      },
      series: [{}, ...cfg.series.map((s) => ({ stroke: s.color, width: s.width || 2, dash: s.dash || undefined,
        cap: s.dash ? "round" : "butt", spanGaps: false, points: { show: false } }))],
      axes: [
        { stroke: C.muted, font, gap: 6, size: 26, grid: { show: false }, ticks: { show: false },
          splits: hourSplits, values: (u, splits) => splits.map((t) => nyClock(t * 1000)) },
        { stroke: C.muted, font, gap: 8, size: 48, grid: { stroke: C.hair2, width: 1 }, ticks: { show: false },
          incrs: PCT_INCRS, values: (u, splits) => splits.map(pctAxis) },
      ],
      cursor: { y: false, drag: { x: false, y: false, setScale: false },
        points: { size: 8, width: 2, stroke: () => C.bg, fill: (u, si) => (cfg.series[si - 1] || {}).color || C.ink } },
      hooks: {
        setCursor: [(u) => cfg.onCursor && cfg.onCursor(u.cursor.idx)],
        drawAxes: [(u) => {
          const ctx = u.ctx;
          const y = Math.round(u.valToPos(0, "y", true)) + 0.5;
          ctx.save();
          ctx.strokeStyle = C.zero;
          ctx.lineWidth = window.uPlot.pxRatio || 1;
          ctx.beginPath();
          ctx.moveTo(u.bbox.left, y);
          ctx.lineTo(u.bbox.left + u.bbox.width, y);
          ctx.stroke();
          ctx.restore();
        }],
      },
    };
    const u = new window.uPlot(opts, cfg.data, container);
    const obs = new ResizeObserver(() => {
      const w = Math.max(240, container.clientWidth);
      if (Math.abs(w - u.width) > 1) u.setSize({ width: w, height: heightFor() });
    });
    obs.observe(container);
    charts.push({ destroy: () => { obs.disconnect(); u.destroy(); } });
    return u;
  }

  // ---------------------------------------------------------------------------------------------
  // Overview

  function sessionsToday() {
    const m = state.meta;
    const h = m.health || {};
    const N = agentsList().length;
    if (!m.start_date) return el("span", { class: "muted", text: "NOT STARTED" });
    if (!h.last_expected_session) return el("span", { text: "NONE DUE" });
    const bad = new Set([...(h.missing || []), ...(h.failed || [])].filter((x) => x.date === h.last_expected_session).map((x) => x.agent));
    const ok = N - bad.size;
    return el("span", { class: ok === N && !h.stale ? "up" : "down", text: `${ok} / ${N} ●` });
  }

  function statusLine() {
    const m = state.meta;
    const h = m.health || {};
    const b = m.budget || {};
    const item = (label, ...value) => el("span", { class: "st-item" }, el("span", { class: "label", text: label }), " ", ...value);
    const line = el("section", { class: "status-line", "aria-label": "Status" });
    line.append(liveStatus());
    line.append(item("SESSIONS", sessionsToday()));
    const missing = (h.missing || []).length, failed = (h.failed || []).length;
    if (missing || failed) {
      line.append(item("GAPS", el("a", { href: "#health", class: "down", text: [missing ? `${missing} MISSING` : "", failed ? `${failed} FAILED` : ""].filter(Boolean).join(" · ") })));
    }
    const next = nextSession();
    if (next) line.append(item("NEXT", next));
    if (isNum(b.cap)) {
      line.append(item("SPEND", `${money(b.spent, 2)} / ${money(b.cap)}`,
        isNum(b.projection) ? el("span", { class: b.projection > b.cap ? "warn" : "muted", text: ` PROJ ${money(b.projection, 0)}` }) : null));
    }
    line.append(item("MARKED", m.last_marked ? `${dShort(m.last_marked)} CLOSE` : "NOT YET"));
    return line;
  }

  function latestThesis(a) {
    const orders = a && Array.isArray(a.orders) ? a.orders : [];
    const o = orders.find((x) => x && x.action !== "close" && String(x.thesis || "").trim());
    return o ? `${o.ticker}: ${String(o.thesis).replace(/\s+/g, " ")}` : null;
  }

  // Longs plus shorts as a share of equity, and the net (shorts negative). The same before any short.
  function exposure(name) {
    const eq = state.equity || {};
    const last = (xs) => (Array.isArray(xs) ? [...xs].reverse().find(isNum) : null);
    const net = last((eq.invested_fraction || {})[name]);
    const g = last((eq.gross_fraction || {})[name]);
    return { gross: isNum(g) ? g : net, net };
  }
  const gross = (s) => (isNum(s.avg_gross) ? s.avg_gross : s.avg_invested);
  const netNote = (g, n) => (isNum(g) && isNum(n) && Math.abs(g - n) > 1e-6
    ? el("span", { class: "muted", text: ` · NET ${pctPlain(n)}` }) : null);

  function agentColumn(meta) {
    const name = meta.name;
    const s = statsOf(name);
    const a = state.agents[name];
    const has = (s.days || 0) > 0;
    const { gross: lastInv, net: lastNet } = exposure(name);
    const row = (label, ...value) => el("div", { class: "kv" }, el("span", { class: "label", text: label }), el("span", null, ...value));
    const quote = latestThesis(a);
    return el("article", { class: "agent-col" },
      el("a", { class: `agent-link ${agClass(name)}`, href: `#agent/${encodeURIComponent(name)}` }, square(name), `${upper(name)} →`),
      headline(name),
      sparkline(rebased((state.equity && state.equity.series || {})[name]), colorOf(name)),
      el("div", { class: "kvs" },
        row("VS S&P 500", vsSp500(name)),
        row("INVESTED", isNum(lastInv) ? pctPlain(lastInv) : DASH, netNote(lastInv, lastNet)),
        row("WORST DROP", has ? pct(s.max_drawdown) : DASH),
        row("TRADES", has || s.trades_closed ? `${(s.trades_closed || 0) + (s.trades_open || 0)}` : DASH,
          s.trades_open ? el("span", { class: "muted", text: ` · ${s.trades_open} OPEN` }) : null)),
      el("div", { class: "quote", title: quote || "", text: `> ${quote || "NO TRADES YET"}` }));
  }

  function horizonCell(p) {
    const lm = state.meta.last_marked;
    if (!p.horizon_end) return td(DASH);
    if (lm && p.horizon_end <= lm) return td("EXPIRED", "warn");
    const n = lm ? tradingDaysBetween(lm, p.horizon_end) : null;
    return td(n != null ? `${n}d` : dShort(p.horizon_end));
  }

  const tickerCell = (t, side) => el("td", { class: "ticker" }, String(t),
    side === "short" ? el("span", { class: "side-tag", text: "SHORT" }) : null);

  function positionsOverview() {
    const rows = [];
    for (const meta of agentsList()) {
      const a = state.agents[meta.name];
      for (const p of (a && Array.isArray(a.positions) ? a.positions : []).slice().sort((x, y) => Math.abs(y.weight || 0) - Math.abs(x.weight || 0))) {
        rows.push(el("tr", null,
          tickerCell(p.ticker, p.side),
          el("td", { class: `${agClass(meta.name)} nowrap`, text: meta.name }),
          num(pctPlain(p.weight, 1)),
          num(pct(p.pnl_pct), dir(p.pnl_pct)),
          ...livePriceCells(String(p.ticker), p.avg_cost, p.side === "short"),
          horizonCell(p),
          el("td", { class: "thesis", text: p.thesis ? String(p.thesis) : DASH })));
      }
    }
    if (!rows.length) return block("positions", "POSITIONS", empty(state.meta.last_marked ? "ALL CASH" : "NO POSITIONS YET"));
    return block("positions", "POSITIONS", table("positions", [["TICKER"], ["AGENT"], ["WEIGHT", 1], ["P&L CLOSE", 1], ["LIVE", 1], ["P&L LIVE", 1], ["HORIZON"], ["THESIS"]], rows, "Positions"));
  }

  function renderOverview(main) {
    main.append(statusLine());
    main.append(el("section", { class: "agent-cols", "aria-label": "Agents" }, agentsList().map(agentColumn)));
    main.append(perfFigure(agentsList().map((a) => a.name).concat(benchList().map((b) => b.name))));
    main.append(positionsOverview());
  }

  // ---------------------------------------------------------------------------------------------
  // Compare

  function standings() {
    const head = [["AGENT"], ["VALUE", 1], ["TODAY", 1], ["RETURN", 1], ["VS S&P 500", 1], ["±", 1], ["VS MATCHED", 1], ["±", 1], ["WORST DROP", 1],
      ["AVG INV", 1], ["TRADES", 1], ["TURNOVER", 1], ["SLIPPAGE", 1], ["SESSIONS", 1], ["API $", 1]];
    const rows = [];
    for (const name of agentsList().map((a) => a.name).concat(benchList().map((b) => b.name))) {
      const s = statsOf(name);
      const has = (s.days || 0) > 0;
      const bench = name.startsWith("bench:");
      const isSpy = name === "bench:spy";
      rows.push(el("tr", { class: bench ? "bench-row" : null },
        el("th", { scope: "row", class: agClass(name) }, square(name),
          bench ? shortName(name) : el("a", { href: `#agent/${encodeURIComponent(name)}`, class: agClass(name), text: upper(name) })),
        ...liveCells(name),
        num(has ? pct(s.total_return) : DASH, has ? dir(s.total_return) : ""),
        num(has && !isSpy ? pct(s.excess_vs_spy) : DASH, has && !isSpy ? dir(s.excess_vs_spy) : ""),
        num(has && !isSpy ? band(s.excess_vs_spy_se) || DASH : DASH, "muted"),
        num(has && !bench ? pct(s.excess_vs_matched) : DASH, has && !bench ? dir(s.excess_vs_matched) : ""),
        num(has && !bench ? band(s.excess_vs_matched_se) || DASH : DASH, "muted"),
        num(has ? pct(s.max_drawdown) : DASH),
        num(has ? pctPlain(gross(s)) : DASH),
        num(!bench && has ? `${s.trades_closed ?? 0} / ${s.trades_open ?? 0}` : DASH),
        num(has && isNum(s.turnover) ? `${s.turnover.toFixed(2)}×` : DASH),
        num(has ? money(s.slippage_paid) : DASH),
        num(!bench && isNum(s.days_run) ? (s.days ? `${s.days_run} / ${s.days}` : String(s.days_run)) : DASH),
        num(!bench && isNum(s.api_spend) ? money(s.api_spend, 2) : DASH)));
    }
    return block("standings", "STANDINGS", table("standings", head, rows, "Standings"),
      el("p", { class: "note-line", text: "VALUE AND TODAY ARE LIVE · RETURN ONWARD AT THE LAST CLOSE · ± = HOW FAR LUCK ALONE COULD MOVE IT · MATCHED = THE S&P 500 AT THE AGENT'S INVESTED SHARE · WORST DROP = BIGGEST FALL FROM A HIGH · TRADES CLOSED / OPEN · SESSIONS DECIDED / DAYS" }));
  }

  function pairsBlock() {
    const pairs = state.comparison && Array.isArray(state.comparison.pairs) ? state.comparison.pairs : [];
    if (!pairs.length) return block("pairs", "PAIRS", empty("NO PAIRS YET"));
    const rows = pairs.map((p) => el("tr", null,
      el("th", { scope: "row" }, el("span", { class: agClass(p.a) }, square(p.a), upper(p.a)), el("span", { class: "muted", text: " × " }),
        el("span", { class: agClass(p.b) }, square(p.b), upper(p.b))),
      num(isNum(p.overlap) ? pctPlain(p.overlap) : DASH),
      num(isNum(p.correlation) ? signed(p.correlation, 2) : DASH)));
    return block("pairs", "PAIRS", table("pairs", [["PAIR"], ["OVERLAP", 1], ["CORR", 1]], rows, "Pairs"),
      el("p", { class: "note-line", text: "OVERLAP = SHARED WEIGHT TODAY · CORR = DAILY RETURNS, NEEDS 5+ DAYS AND A BOOK THAT MOVES" }));
  }

  function renderCompare(main) {
    if (state.holdings) main.append(el("section", { class: "status-line", "aria-label": "Status" }, liveStatus()));
    main.append(standings(), pairsBlock());
  }

  // ---------------------------------------------------------------------------------------------
  // Health

  function renderHealth(main) {
    const m = state.meta;
    const h = m.health || {};
    const b = m.budget || {};
    const cells = el("div", { class: "cells" });
    const cell = (label, value, sub) => el("div", { class: "cell" }, el("div", { class: "label", text: label }), el("div", { class: "cell-value" }, value),
      sub ? el("div", { class: "cell-sub" }, sub) : null);
    cells.append(cell("SESSIONS", sessionsToday(), h.last_expected_session ? `DUE ${dShort(h.last_expected_session)} · NEWEST ${h.newest_session ? dShort(h.newest_session) : DASH}` : null));
    cells.append(cell("NEXT", nextSession() || DASH, m.start_date ? `DAY ONE ${dShort(m.start_date)}` : null));
    cells.append(cell("MARKED", m.last_marked ? `${dShort(m.last_marked)} CLOSE` : "NOT YET"));
    if (isNum(b.cap) && b.cap > 0) {
      const spent = isNum(b.spent) ? b.spent : 0;
      const proj = isNum(b.projection) ? b.projection : spent;
      const meter = el("div", { class: "meter", role: "img", "aria-label": `${money(spent, 2)} spent, ${money(proj, 2)} projected, cap ${money(b.cap)}` });
      const fill = el("span", { class: "meter-fill" });
      fill.style.width = `${Math.min(100, (spent / b.cap) * 100)}%`;
      const tick = el("span", { class: `meter-proj ${proj > b.cap ? "over" : ""}` });
      tick.style.left = `${Math.min(100, (proj / b.cap) * 100)}%`;
      meter.append(fill, tick);
      cells.append(cell(`SPEND ${fmtMonth(b.month)}`, el("span", null, money(spent, 2), el("span", { class: "muted", text: ` / ${money(b.cap)}` })),
        el("span", null, meter, el("span", { class: proj > b.cap ? "warn" : "" , text: `PROJ ${money(proj, 2)}` }))));
    }
    cells.classList.add("cells-wide");
    main.append(block("health-now", "HEALTH", cells));
    const missing = (h.missing || []).slice().sort((x, y) => (x.date < y.date ? 1 : -1));
    const failed = (h.failed || []).slice().sort((x, y) => (x.date < y.date ? 1 : -1));
    main.append(block("missing", `MISSING ${missing.length}`, missing.length
      ? table("gaps", [["DATE"], ["AGENT"]], missing.map((x) => el("tr", null, td(dLong(x.date)), td(x.agent, agClass(x.agent)))), "Missing sessions")
      : empty("NONE")));
    main.append(block("failed", `FAILED ${failed.length}`, failed.length
      ? table("gaps", [["DATE"], ["AGENT"], ["REASON"]], failed.map((x) => el("tr", null, td(dLong(x.date)), td(x.agent, agClass(x.agent)), td(x.reason || DASH, "wrap"))), "Failed sessions")
      : empty("NONE")));
  }

  // ---------------------------------------------------------------------------------------------
  // Method

  function renderHow(main) {
    const tt = Array.isArray(state.meta.tech_ten) ? state.meta.tech_ten : [];
    const li = (...c) => el("li", null, ...c);
    main.append(block("how", "METHOD", el("ul", { class: "terse" },
      li("$100,000 PAPER MONEY PER AGENT · REAL PRICES (ALPACA)"),
      li("ONE SESSION PER TRADING DAY, FROM 13:30 AMSTERDAM, BEFORE THE US OPEN"),
      li("SAME MODEL FOR EVERY AGENT"),
      li("FILLS AT THE OPEN, OR THE FIRST MINUTE AFTER A LATE DECISION · NO COMMISSION"),
      li("SLIPPAGE PER SIDE: 0.10% ABOVE $10B · 0.25% $2B–10B · 0.50% $300M–2B"),
      li("LONG AND SHORT · NO LEVERAGE: LONGS PLUS SHORTS AT MOST 100% OF VALUE"),
      li("SHORTS: EASY-TO-BORROW STOCKS ONLY · 0.5% A YEAR BORROW FEE · SHORTS PAY DIVIDENDS"),
      li("OPEN UNIVERSE: US STOCKS AND ADRS, PRICE ≥ $5, MARKET CAP ≥ $300M"),
      li("EVERY POSITION: STOP, TARGET, HORIZON · ENFORCED BY CODE ON THE DAILY HIGH AND LOW"),
      li("PAST HORIZON: AGENT MUST CLOSE OR EXTEND WITH A NEW THESIS"),
      tt.length ? li(`TECH TEN: ${tt.join(" ")}`) : null)));
    main.append(block("benchmarks", "BENCHMARKS", el("ul", { class: "terse" },
      li(el("span", { class: "label", text: "S&P 500 " }), "$100,000 IN SPY ON DAY ONE, HELD, DIVIDENDS CREDITED"),
      li(el("span", { class: "label", text: "MATCHED " }), "PER AGENT: THE S&P 500 AT THE SHARE THE AGENT HAD INVESTED THE DAY BEFORE, REST CASH"))));
    main.append(block("agents", "AGENTS", el("ul", { class: "terse" }, agentsList().map((a) =>
      li(el("a", { href: `#agent/${encodeURIComponent(a.name)}`, class: agClass(a.name) }, square(a.name), upper(a.name)), el("span", { class: "muted", text: ` ${a.description || ""}` }))))));
    main.append(block("links", "SOURCE", el("ul", { class: "terse" },
      li(el("a", { href: repoUrl(""), rel: "noopener noreferrer", text: "GITHUB REPOSITORY" })),
      li(el("a", { href: repoUrl("/blob/main/docs/PLAN.md"), rel: "noopener noreferrer", text: "DOCS/PLAN.MD" })),
      li(el("a", { href: BASE.startsWith("https://") ? BASE : "#", rel: "noopener noreferrer", text: "RAW DATA FILES" })))));
  }

  // ---------------------------------------------------------------------------------------------
  // Agent page

  function sourceList(sources) {
    const list = (Array.isArray(sources) ? sources : []).map((s) => (typeof s === "string" ? { url: s } : s || {}));
    if (!list.length) return null;
    return el("ul", { class: "sources" }, list.map((s) => {
      const raw = String(s.url || "");
      const safe = httpsHref(raw);
      let item;
      if (safe) {
        const u = new URL(safe);
        const rest = (u.pathname + u.search).replace(/\/$/, "");
        item = el("li", null, extLink(safe, el("span", { class: "src-domain", text: u.hostname.replace(/^www\./, "") }),
          el("span", { class: "src-path", text: rest.length > 60 ? rest.slice(0, 59) + "…" : rest })));
      } else {
        item = el("li", null, el("span", { class: "src-domain", text: raw.slice(0, 120) || "(EMPTY)" }), el("span", { class: "muted", text: " NOT LINKED (NOT HTTPS)" }));
      }
      if (s.read) item.append(el("span", { class: "muted", text: " · READ" }));
      if (s.answer) item.append(el("div", { class: "src-answer", text: String(s.answer) }));
      return item;
    }));
  }

  function chainList(chain) {
    const steps = Array.isArray(chain) ? chain.filter((c) => c && String(c.step || "").trim()) : [];
    if (!steps.length) return null;
    return el("ol", { class: "chain" }, steps.map((c) => el("li", null, String(c.step), c.source_url ? sourceList([c.source_url]) : null)));
  }

  function agentSwitcher(active) {
    return el("nav", { class: "switcher", "aria-label": "Agents" }, agentsList().map((a) =>
      el("a", { href: `#agent/${encodeURIComponent(a.name)}`, class: `${agClass(a.name)} ${a.name === active ? "active" : ""}`,
        "aria-current": a.name === active ? "page" : null }, square(a.name), upper(a.name))));
  }

  function agentHead(name, a) {
    const s = statsOf(name);
    const has = (s.days || 0) > 0;
    const cell = (label, value, cls, sub) => el("div", { class: "cell" }, el("div", { class: "label", text: label }),
      el("div", { class: `cell-value ${cls || ""}`, text: value }), sub ? el("div", { class: "cell-sub", text: sub }) : null);
    const { gross: lastInv, net: lastNet } = exposure(name);
    const netSub = isNum(lastNet) && isNum(lastInv) && Math.abs(lastNet - lastInv) > 1e-6 ? `NET ${pctPlain(lastNet)} · ` : "";
    const vs = el("div", { class: "cell" }, el("div", { class: "label", text: "VS S&P 500" }),
      el("div", { class: "cell-value" }, vsSp500(name)), has ? el("div", { class: "cell-sub", text: band(s.excess_vs_spy_se) }) : null);
    return el("section", { class: "agent-head" },
      el("h1", { class: `agent-title ${agClass(name)}` }, square(name), upper(name)),
      el("p", { class: "desc", text: String(a.description || "") }),
      el("div", { class: "hero" },
        headline(name),
        el("div", { class: "cells" },
          cell("CASH", money(a.cash)),
          vs,
          cell("VS MATCHED", has ? pct(s.excess_vs_matched) : DASH, dir(s.excess_vs_matched), has ? band(s.excess_vs_matched_se) : null),
          cell("WORST DROP", has ? pct(s.max_drawdown) : DASH, "", "BIGGEST FALL FROM A HIGH"),
          cell("INVESTED", isNum(lastInv) ? pctPlain(lastInv) : DASH, "", has ? `${netSub}AVG ${pctPlain(gross(s))}` : null),
          cell("TRADES", has ? `${s.trades_closed ?? 0} / ${s.trades_open ?? 0}` : DASH, "", "CLOSED / OPEN"),
          cell("TURNOVER", has && isNum(s.turnover) ? `${s.turnover.toFixed(2)}×` : DASH),
          cell("SLIPPAGE", has ? money(s.slippage_paid) : DASH),
          cell("SESSIONS", isNum(s.days_run) ? (s.days ? `${s.days_run} / ${s.days}` : String(s.days_run)) : DASH, "", "DECIDED / DAYS"),
          cell("API $", isNum(s.api_spend) ? money(s.api_spend, 2) : DASH),
          cell("BRIER", isNum(s.brier) && s.brier_n ? s.brier.toFixed(3) : DASH, "", s.brier_n ? `N=${s.brier_n} · 0.5 ALWAYS = 0.250` : "AFTER FIRST SETTLED TRADE"))),
      has ? el("p", { class: "note-line", text: `± = HOW FAR LUCK ALONE COULD PLAUSIBLY MOVE IT AFTER ${s.days} ${s.days === 1 ? "DAY" : "DAYS"} · CASH AND INVESTED ARE AT THE LAST CLOSE` }) : null);
  }

  function agentCharts(name) {
    const eq = state.equity || {};
    const out = [perfFigure([name, "bench:spy"])];
    const inv = (eq.gross_fraction || eq.invested_fraction || {})[name];
    const labels = chartLabels();
    if (labels && Array.isArray(inv) && inv.length) {
      const vals = [0].concat(inv.map((v) => (isNum(v) ? v * 100 : null)));
      const fig = el("figure", { class: "block figure" });
      const ro = readout(labels, [{ label: "INVESTED", values: vals, cls: agClass(name) }], (v) => `${v.toFixed(0)}%`);
      fig.append(el("div", { class: "fig-head" }, el("h2", { text: "INVESTED" }), ro.box));
      const box = el("div", { class: "chart chart-small" });
      fig.append(box);
      out.push(fig);
      const c = colorOf(name);
      const n = parseInt(c.slice(1), 16);
      later(() => lineChart(box, { labels, height: [120, 140], series: [{ values: vals, color: c, width: 2, fill: `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},0.12)` }],
        fmt: (v) => `${v.toFixed(0)}%`, yRange: () => [0, 100], onCursor: (idx) => ro.set(idx) }));
    }
    return out;
  }

  function positionsAgent(a) {
    const pos = Array.isArray(a.positions) ? a.positions : [];
    if (!pos.length) return block("positions", "POSITIONS", empty(state.meta.last_marked ? "ALL CASH" : "NO POSITIONS YET"));
    const rows = pos.map((p) => {
      const thesis = el("td", { class: "thesis" }, p.thesis ? String(p.thesis) : DASH);
      if (p.extensions && p.original_thesis && p.original_thesis !== p.thesis) {
        thesis.append(el("div", { class: "orig" }, el("span", { class: "label", text: `ORIGINAL ${dShort(p.opened)} · EXTENDED ${p.extensions}× ` }), String(p.original_thesis)));
      }
      return el("tr", null,
        tickerCell(p.ticker, p.side),
        num(pctPlain(p.weight, 1)),
        num(pct(p.pnl_pct), dir(p.pnl_pct)),
        ...livePriceCells(String(p.ticker), p.avg_cost, p.side === "short"),
        num(isNum(p.stop_price) ? money(p.stop_price, 2) : DASH),
        num(isNum(p.target_price) ? money(p.target_price, 2) : DASH),
        horizonCell(p),
        td(dShort(p.opened), "nowrap"),
        thesis);
    });
    return block("positions", "POSITIONS", table("positions", [["TICKER"], ["WEIGHT", 1], ["P&L CLOSE", 1], ["LIVE", 1], ["P&L LIVE", 1], ["STOP", 1], ["TARGET", 1], ["HORIZON"], ["OPENED"], ["THESIS"]], rows, "Positions"));
  }

  const EXIT = { close: "AGENT CLOSED", set_weight: "AGENT SOLD DOWN" };
  const EXIT_SHORT = { close: "AGENT COVERED", set_weight: "AGENT COVERED" };

  function tradesBlock(a) {
    const trades = Array.isArray(a.trades) ? a.trades : [];
    if (!trades.length) return block("trades", "TRADES", empty("NO TRADES"));
    const head = [["TICKER"], ["OPENED"], ["CLOSED"], ["RETURN", 1], ["SPY", 1], ["EXCESS", 1], ["EXIT"], ["P", 1]];
    const render = (list) => {
      const rows = [];
      for (const t of list) {
        const open = !t.closed;
        rows.push(el("tr", { class: "trade" },
          tickerCell(t.ticker, t.side),
          td(dShort(t.opened), "nowrap"),
          td(open ? "OPEN" : dShort(t.closed), open ? "nowrap warn" : "nowrap"),
          num(open ? DASH : pct(t.return), open ? "" : dir(t.return)),
          num(open ? DASH : pct(t.spy_return), "muted"),
          num(open ? DASH : pct(t.excess), open ? "" : dir(t.excess)),
          td(open ? DASH : (t.side === "short" ? EXIT_SHORT : EXIT)[t.exit_reason] || upper(t.exit_reason || DASH), "nowrap"),
          num(isNum(t.probability) ? t.probability.toFixed(2) : DASH)));
        const d = el("details", { class: "detail-body" }, el("summary", { text: "THESIS · SOURCES" + (Array.isArray(t.causal_chain) && t.causal_chain.length ? " · CHAIN" : "") }));
        d.append(el("p", { class: "thesis", text: t.thesis ? String(t.thesis) : DASH }));
        const facts = [];
        if (isNum(t.horizon_days)) facts.push(`HORIZON ${t.horizon_days}d${t.horizon_end ? ` → ${dShort(t.horizon_end)}` : ""}`);
        const short = t.side === "short";
        if (isNum(t.stop_pct)) facts.push(`STOP ${short ? "+" : "−"}${t.stop_pct}%`);
        if (isNum(t.target_pct)) facts.push(`TARGET ${short ? "−" : "+"}${t.target_pct}%`);
        if (isNum(t.dividends) && t.dividends > 0) facts.push(`DIVIDENDS ${money(t.dividends, 2)}`);
        if (isNum(t.dividends) && t.dividends < 0) facts.push(`DIVIDENDS PAID ${money(-t.dividends, 2)}`);
        if (isNum(t.fees) && t.fees > 0) facts.push(`BORROW FEES ${money(t.fees, 2)}`);
        if (facts.length) d.append(el("p", { class: "label", text: facts.join(" · ") }));
        if (Array.isArray(t.extensions) && t.extensions.length) {
          d.append(el("p", { class: "label", text: "EXTENSIONS" }), el("ul", { class: "plain" }, t.extensions.map((x) =>
            el("li", null, el("span", { class: "muted", text: `${dShort(x.date)} ` }), String(x.thesis || "")))));
        }
        d.append(el("p", { class: "label", text: "SOURCES" }), sourceList(t.sources) || el("p", { class: "muted", text: "NONE" }));
        const ch = chainList(t.causal_chain);
        if (ch) d.append(el("p", { class: "label", text: "CAUSAL CHAIN" }), ch);
        rows.push(el("tr", { class: "detail" }, el("td", { colspan: String(head.length) }, d)));
      }
      return table("trades", head, rows, "Trades");
    };
    return block("trades", "TRADES", more(trades, 15, render));
  }

  const ACTION = { set_weight: "SET WEIGHT", close: "CLOSE", extend: "EXTEND" };

  function ordersBlock(a) {
    const orders = Array.isArray(a.orders) ? a.orders : [];
    if (!orders.length) return block("orders", "ORDERS", empty("NO ORDERS"));
    const lm = state.meta.last_marked;
    const render = (list) => table("orders", [["SESSION"], ["TICKER"], ["ACTION"], ["WEIGHT", 1], ["STOP", 1], ["TARGET", 1], ["HORIZON", 1], ["P", 1]],
      list.map((o) => {
        const close = o.action === "close";
        return el("tr", null,
          td(dShort(o.session_date), "nowrap"),
          el("td", { class: "ticker-sm", text: String(o.ticker) }),
          el("td", { class: "nowrap" }, ACTION[o.action] || upper(o.action), !lm || o.session_date > lm ? el("span", { class: "warn", text: " · PENDING" }) : null),
          num(o.action === "set_weight" ? pctPlain(o.target_weight, 1) : DASH),
          num(!close && isNum(o.stop_pct) ? `${MINUS}${o.stop_pct}%` : DASH),
          num(!close && isNum(o.target_pct) ? `+${o.target_pct}%` : DASH),
          num(!close && isNum(o.horizon_days) ? `${o.horizon_days}d` : DASH),
          num(!close && isNum(o.probability) ? o.probability.toFixed(2) : DASH));
      }), "Orders");
    return block("orders", "ORDERS", more(orders, 12, render));
  }

  function sessionsBlock(a) {
    const sess = Array.isArray(a.sessions) ? a.sessions : [];
    if (!sess.length) return block("sessions", "SESSIONS", empty("NO SESSIONS"));
    const cls = { decided: "up", hold: "warn", failed: "down" };
    const render = (list) => table("sessions", [["DATE"], ["STATUS"], ["ORDERS", 1], ["COST", 1], ["NOTE"], ["LOG"]], list.map((s) => {
      const rej = Array.isArray(s.rejected) ? s.rejected : [];
      return el("tr", null,
        td(dShort(s.date), "nowrap"),
        td(`● ${upper(s.status || "unknown")}`, `nowrap ${cls[s.status] || "muted"}`),
        num(isNum(s.orders) ? String(s.orders) : DASH),
        num(isNum(s.cost) ? money(s.cost, 2) : DASH),
        el("td", { class: "wrap" }, s.reason ? String(s.reason) : "", rej.length ? el("details", { class: "rejected" },
          el("summary", { text: `${rej.length} REJECTED` }), el("ul", { class: "plain" }, rej.map((r) => el("li", { text: String(r) })))) : null),
        el("td", null, httpsHref(s.url) ? extLink(s.url, "GITHUB →") : DASH));
    }), "Sessions");
    return block("sessions", "SESSIONS", more(sess, 10, render));
  }

  const md = (src, emptyText) => { const b = markdown(src); return b.childNodes.length ? b : empty(emptyText); };

  function renderAgent(main, name, a) {
    main.append(agentSwitcher(name), agentHead(name, a));
    main.append(...agentCharts(name));
    main.append(positionsAgent(a), tradesBlock(a), ordersBlock(a), sessionsBlock(a));
    main.append(el("div", { class: "two-col" },
      block("summary", "LATEST SUMMARY", md(a.summary, "NONE YET")),
      block("notes", "NOTES", md(a.notes, "NONE YET"))));
    const tickers = a.tickers && typeof a.tickers === "object" ? Object.entries(a.tickers) : [];
    main.append(block("ticker-notes", "TICKER NOTES", tickers.length
      ? el("div", { class: "files" }, tickers.map(([t, src]) => el("details", { class: "file" }, el("summary", { class: "ticker-sm", text: String(t) }), md(src, "EMPTY"))))
      : empty("NONE YET")));
    main.append(block("prompt", "PROMPT", el("details", { class: "file" }, el("summary", { text: "SHOW PROMPT" }), md(a.prompt, "NONE")),
      el("p", { class: "note-line" }, el("a", { href: repoUrl(`/tree/main/agents/${encodeURIComponent(name)}`), rel: "noopener noreferrer", text: "AGENT FOLDER ON GITHUB →" }))));
  }

  // ---------------------------------------------------------------------------------------------
  // Router

  function errorView(main, e) {
    main.append(el("div", { class: "banner", role: "alert" },
      el("strong", { text: e && e.status === 404 ? "■ NO DATA YET" : "■ DATA DID NOT LOAD" }),
      el("span", { text: e && e.status === 404 ? "PUBLISHED AFTER THE FIRST MARKING JOB" : "RELOAD IN A MINUTE" })),
      el("p", { class: "note-line", text: `${BASE}${e && e.message ? ` · ${e.message}` : ""}` }));
  }

  async function render() {
    const main = document.getElementById("main");
    const route = decodeURIComponent(location.hash.replace(/^#\/?/, ""));
    charts.forEach((c) => c.destroy());
    charts = [];
    pending = [];
    liveSlots = [];
    clearTimeout(liveTimer);
    try {
      await loadCore();
    } catch (e) {
      main.replaceChildren();
      renderMasthead("overview");
      errorView(main, e);
      return;
    }
    renderBanner();
    const agentMatch = /^agent\/(.+)$/.exec(route);
    if (agentMatch) {
      const name = agentMatch[1];
      const known = agentsList().find((x) => x.name === name);
      renderMasthead("agent");
      let a = null, err = null;
      if (known) { try { a = await loadAgent(name); } catch (e) { err = e; } }
      main.replaceChildren();
      if (!known || !a) {
        main.append(agentSwitcher(name), empty(known ? `AGENT FILE DID NOT LOAD${err ? ` · ${err.message}` : ""}` : "NO SUCH AGENT"));
        return;
      }
      document.title = `${upper(name)} · Trading agents`;
      renderAgent(main, name, a);
      flush();
      startLive();
      window.scrollTo(0, 0);
      return;
    }
    const page = ["compare", "health", "how"].includes(route) ? route : "overview";
    document.title = page === "overview" ? "Trading agents" : `${upper(page === "how" ? "method" : page)} · Trading agents`;
    renderMasthead(page);
    if (page === "overview") await loadAllAgents();
    main.replaceChildren();
    if (page === "compare") renderCompare(main);
    else if (page === "health") renderHealth(main);
    else if (page === "how") renderHow(main);
    else renderOverview(main);
    flush();
    if (page === "overview" || page === "compare") startLive();
    if (route && page === "overview") history.replaceState(null, "", "#");
    window.scrollTo(0, 0);
  }

  function flush() {
    const fns = pending;
    pending = [];
    fns.forEach((fn) => fn());
  }

  window.addEventListener("hashchange", render);
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", render);
  else render();
})();
