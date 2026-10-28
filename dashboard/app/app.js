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
  const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September",
    "October", "November", "December"];

  // Colour follows the agent, everywhere. Unknown future agents take the next slots in order.
  const AGENT_SLOTS = { "open-quality": 1, "tech-ten": 2, "weird-links": 3, "no-news": 4 };
  const BENCH_STYLE = {
    "bench:spy": { v: "--bench-1", dash: [6, 4] },
    "bench:qqq": { v: "--bench-2", dash: [2, 3] },
    "bench:tech-ten-ew": { v: "--bench-3", dash: [10, 3, 2, 3] },
  };

  const state = { meta: null, equity: null, stats: null, comparison: null, agents: {}, error: null };
  let charts = [];

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
    append(node, children);
    return node;
  }

  function append(node, children) {
    for (const c of children.flat(Infinity)) {
      if (c == null || c === false) continue;
      node.append(c instanceof Node ? c : String(c));
    }
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

  function cssVar(name) {
    return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  }

  function hexA(hex, a) {
    const m = /^#?([0-9a-f]{6})$/i.exec(hex);
    if (!m) return hex;
    const n = parseInt(m[1], 16);
    return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${a})`;
  }

  // ---------------------------------------------------------------------------------------------
  // Formatting

  const isNum = (x) => typeof x === "number" && isFinite(x);

  function signed(x, digits) {
    const s = Math.abs(x).toFixed(digits);
    if (Number(s) === 0) return (0).toFixed(digits);
    return (x < 0 ? MINUS : "+") + s;
  }
  const pct = (x, d = 1) => (isNum(x) ? signed(x * 100, d) + "%" : DASH);
  const pctPlain = (x, d = 0) => (isNum(x) ? (x * 100).toFixed(d).replace("-", MINUS) + "%" : DASH);
  const pts = (x, d = 1) => (isNum(x) ? signed(x * 100, d) + " pts" : DASH);
  function money(x, d = 0) {
    if (!isNum(x)) return DASH;
    const s = Math.abs(x).toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d });
    return (x < 0 ? MINUS : "") + "$" + s;
  }
  function range2se(x, se) {
    if (!isNum(x) || !isNum(se)) return null;
    return `${signed((x - 2 * se) * 100, 1)} to ${signed((x + 2 * se) * 100, 1)}`;
  }
  function fmtDate(iso) {
    const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(iso || ""));
    if (!m) return String(iso || DASH);
    return `${Number(m[3])} ${MONTHS[Number(m[2]) - 1].slice(0, 3)} ${m[1]}`;
  }
  function fmtShort(iso) {
    const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(iso || ""));
    if (!m) return String(iso || "");
    return `${MONTHS[Number(m[2]) - 1].slice(0, 3)} ${Number(m[3])}`;
  }
  function fmtMonth(ym) {
    const m = /^(\d{4})-(\d{2})/.exec(String(ym || ""));
    return m ? `${MONTHS[Number(m[2]) - 1]} ${m[1]}` : "this month";
  }
  function fmtStamp(iso) {
    const d = new Date(iso);
    if (isNaN(d)) return String(iso || "");
    const p = (n) => String(n).padStart(2, "0");
    return `${fmtDate(d.toISOString())}, ${p(d.getUTCHours())}:${p(d.getUTCMinutes())} UTC`;
  }
  const plural = (n, one, many) => `${n} ${n === 1 ? one : many || one + "s"}`;

  // ---------------------------------------------------------------------------------------------
  // Markdown, sanitised

  const MD_TAGS = ["p", "br", "strong", "em", "code", "pre", "ul", "ol", "li", "h1", "h2", "h3", "h4",
    "blockquote", "table", "thead", "tbody", "tr", "th", "td", "hr", "a"];
  let hookInstalled = false;

  function markdown(src) {
    const box = el("div", { class: "prose" });
    if (!src || !String(src).trim()) return box;
    if (!window.marked || !window.DOMPurify) {
      box.append(el("pre", { class: "plain", text: String(src) }));
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
    const html = window.marked.parse(String(src), { async: false, gfm: true, breaks: false });
    const frag = window.DOMPurify.sanitize(html, {
      ALLOWED_TAGS: MD_TAGS,
      ALLOWED_ATTR: ["href"],
      ALLOW_DATA_ATTR: false,
      ALLOW_ARIA_ATTR: false,
      RETURN_DOM_FRAGMENT: true,
    });
    // A link that lost its href keeps only its words.
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
    const [meta, equity, stats, comparison] = await Promise.all(
      ["meta.json", "equity.json", "stats.json", "comparison.json"].map(getJSON));
    Object.assign(state, { meta, equity, stats, comparison });
  }

  async function loadAgent(name) {
    if (!state.agents[name]) state.agents[name] = await getJSON(`agents/${encodeURIComponent(name)}.json`);
    return state.agents[name];
  }

  const agentsList = () => (state.meta && Array.isArray(state.meta.agents) ? state.meta.agents : []);
  const benchList = () => (state.meta && Array.isArray(state.meta.benchmarks) ? state.meta.benchmarks : []);
  const repo = () => (state.meta && typeof state.meta.repo === "string" ? state.meta.repo : DEFAULT_REPO);
  const repoUrl = (path) => `https://github.com/${repo()}${path || ""}`;

  function labelOf(name) {
    const a = agentsList().find((x) => x.name === name) || benchList().find((x) => x.name === name);
    return a && a.label ? String(a.label) : String(name);
  }

  function agentColor(name) {
    let slot = AGENT_SLOTS[name];
    if (!slot) {
      const extra = agentsList().map((a) => a.name).filter((n) => !AGENT_SLOTS[n]);
      slot = Math.min(8, 5 + Math.max(0, extra.indexOf(name)));
    }
    return cssVar(`--series-${slot}`);
  }

  function seriesStyle(name) {
    if (BENCH_STYLE[name]) return { color: cssVar(BENCH_STYLE[name].v), dash: BENCH_STYLE[name].dash, width: 1.5 };
    if (String(name).startsWith("bench:")) return { color: cssVar("--bench-2"), dash: [4, 4], width: 1.5 };
    return { color: agentColor(name), dash: null, width: 2 };
  }

  function swatch(name, opts) {
    const s = seriesStyle(name);
    const node = el("span", { class: "swatch" + (s.dash ? " swatch-dash" : ""), "aria-hidden": "true" });
    node.style.setProperty("--c", (opts && opts.color) || s.color);
    return node;
  }

  // ---------------------------------------------------------------------------------------------
  // Charts (uPlot). x is the trading-day index; the first point is the starting cash.

  function chartData(names, valuesFor) {
    const eq = state.equity || {};
    const dates = Array.isArray(eq.dates) ? eq.dates : [];
    if (!dates.length) return null;
    const labels = ["Start"].concat(dates);
    const series = names.map((n) => {
      const vals = valuesFor(n);
      if (!vals) return null;
      return { name: n, values: vals };
    }).filter(Boolean);
    return { labels, series };
  }

  function rebased(values) {
    const start = isNum(state.equity && state.equity.start_cash) ? state.equity.start_cash : 100000;
    if (!Array.isArray(values)) return null;
    return [100].concat(values.map((v) => (isNum(v) ? (v / start) * 100 : null)));
  }

  function tickIndices(n, width) {
    const max = Math.max(2, Math.floor(width / 76));
    const step = Math.max(1, Math.ceil(n / max));
    const out = [];
    for (let i = 0; i < n; i += step) out.push(i);
    if (n > 1 && out[out.length - 1] !== n - 1 && n - 1 - out[out.length - 1] >= step / 2) out.push(n - 1);
    return out;
  }

  function lineChart(container, cfg) {
    // cfg: labels, series [{label, values, color, dash, width, fill}], height, fmt, axisFmt, yRange, markers
    if (!window.uPlot) {
      container.append(el("p", { class: "empty", text: "The chart library did not load." }));
      return null;
    }
    const muted = cssVar("--text-muted");
    const grid = cssVar("--grid");
    const axis = cssVar("--axis");
    const surface = cssVar("--surface");
    const font = "12px system-ui, -apple-system, 'Segoe UI', sans-serif";
    const xs = cfg.labels.map((_, i) => i);
    const heightFor = () => (container.clientWidth < 560 ? cfg.height[0] : cfg.height[1]);
    const opts = {
      width: Math.max(260, container.clientWidth),
      height: heightFor(),
      padding: [14, 14, 0, 2],
      scales: {
        x: { time: false, range: (u, mn, mx) => [mn, Math.max(mx, mn + 1)] },
        y: { range: cfg.yRange },
      },
      series: [
        { label: "Day", value: (u, v) => (v == null ? "" : cfg.labels[v] === "Start" ? "Start" : fmtDate(cfg.labels[v])) },
        ...cfg.series.map((s) => ({
          label: s.label,
          stroke: s.color,
          width: s.width || 2,
          dash: s.dash || undefined,
          fill: s.fill || undefined,
          spanGaps: false,
          points: { size: 7, width: 2, stroke: s.color, fill: surface },
          value: (u, v) => (v == null ? DASH : cfg.fmt(v)),
        })),
      ],
      axes: [
        {
          stroke: muted, font, gap: 6, size: 30,
          grid: { show: false },
          ticks: { stroke: axis, width: 1, size: 4 },
          splits: (u) => tickIndices(cfg.labels.length, u.width),
          values: (u, splits) => splits.map((i) => (cfg.labels[i] === "Start" ? "Start" : fmtShort(cfg.labels[i]))),
        },
        {
          stroke: muted, font, gap: 6, size: 46,
          grid: { stroke: grid, width: 1 },
          ticks: { show: false },
          values: (u, splits) => splits.map(cfg.axisFmt || cfg.fmt),
        },
      ],
      cursor: {
        y: false,
        drag: { x: false, y: false, setScale: false },
        points: { size: 9, width: 2, stroke: surface },
      },
      legend: { live: true },
      hooks: {
        draw: [
          (u) => {
            if (!cfg.markers || !cfg.markers.length) return;
            const ctx = u.ctx;
            const r = window.uPlot.pxRatio || 1;
            const top = u.bbox.top;
            const bottom = u.bbox.top + u.bbox.height;
            ctx.save();
            ctx.font = `${11 * r}px system-ui, sans-serif`;
            ctx.textBaseline = "top";
            for (const m of cfg.markers) {
              const x = Math.round(u.valToPos(m.idx, "x", true)) + 0.5;
              ctx.strokeStyle = m.color;
              ctx.lineWidth = 1 * r;
              ctx.setLineDash([]);
              ctx.beginPath();
              ctx.moveTo(x, top);
              ctx.lineTo(x, bottom);
              ctx.stroke();
              ctx.fillStyle = muted;
              const w = ctx.measureText(m.text).width;
              const tx = x + 4 * r + w > u.bbox.left + u.bbox.width ? x - 4 * r - w : x + 4 * r;
              ctx.fillText(m.text, tx, top + 2 * r);
            }
            ctx.restore();
          },
        ],
      },
    };
    const data = [xs, ...cfg.series.map((s) => s.values)];
    const u = new window.uPlot(opts, data, container);
    const ro = new ResizeObserver(() => {
      const w = Math.max(260, container.clientWidth);
      if (Math.abs(w - u.width) > 1) u.setSize({ width: w, height: heightFor() });
    });
    ro.observe(container);
    charts.push({ destroy: () => { ro.disconnect(); u.destroy(); } });
    return u;
  }

  function yRangeAround100(u, min, max) {
    const lo = Math.min(isNum(min) ? min : 100, 100);
    const hi = Math.max(isNum(max) ? max : 100, 100);
    const pad = Math.max((hi - lo) * 0.08, 0.5);
    return [Math.floor((lo - pad) * 2) / 2, Math.ceil((hi + pad) * 2) / 2];
  }

  // ---------------------------------------------------------------------------------------------
  // Shared pieces

  function section(id, title, ...children) {
    return el("section", { class: "section", id }, el("h2", { text: title }), ...children);
  }

  function empty(text) {
    return el("p", { class: "empty", text });
  }

  function tableScroll(table, label) {
    return el("div", { class: "table-scroll", role: "region", "aria-label": label, tabindex: "0" }, table);
  }

  function statusMark(kind, label) {
    return el("span", { class: `status status-${kind}` }, el("span", { class: "status-icon", "aria-hidden": "true" }), label);
  }

  function renderBanner() {
    const box = document.getElementById("banner");
    box.replaceChildren();
    const h = state.meta && state.meta.health;
    if (!h || !h.stale) return;
    const newest = h.newest_session;
    const expected = h.last_expected_session;
    const text = newest
      ? `The newest agent session is from ${fmtDate(newest)}, and one was due on ${fmtDate(expected)}. ` +
        "Until a new session runs, the agents place no orders."
      : `No agent session has run yet, and the first was due on ${fmtDate(expected)}.`;
    box.append(el("div", { class: "banner", role: "alert" },
      el("span", { class: "banner-icon", "aria-hidden": "true" }),
      el("div", null, el("strong", { text: "Sessions are behind. " }), text)));
  }

  function renderNav(active) {
    const nav = document.getElementById("nav");
    nav.replaceChildren();
    const link = (href, text, on, name) => el("a", { href, class: on ? "active" : null, "aria-current": on ? "page" : null },
      name ? swatch(name) : null, text);
    nav.append(link("#", "Overview", active === "overview"));
    for (const a of agentsList()) nav.append(link(`#agent/${encodeURIComponent(a.name)}`, a.label || a.name, active === a.name, a.name));
    nav.append(link("#how", "How this works", active === "how"));
  }

  function renderFooter() {
    const p = document.getElementById("generated");
    p.replaceChildren();
    if (state.meta && state.meta.generated_at) {
      p.append(`Data built ${fmtStamp(state.meta.generated_at)}. Data files: `,
        el("a", { href: BASE, rel: "noopener noreferrer", text: BASE.replace(/^https?:\/\//, "") }), ".");
    }
  }

  // ---------------------------------------------------------------------------------------------
  // Overview

  function healthStrip() {
    const m = state.meta;
    const h = m.health || {};
    const items = [];

    // Sessions
    const sess = el("div", { class: "health-item" }, el("h3", { text: "Sessions" }));
    if (!m.start_date) sess.append(el("p", { text: "The experiment has not started. Day one is the first trading day after the schedule is turned on." }));
    else if (!h.last_expected_session) sess.append(el("p", { text: `Started ${fmtDate(m.start_date)}. No session was due yet.` }));
    else {
      sess.append(el("p", null, h.stale ? statusMark("critical", "Behind") : statusMark("good", "Up to date"),
        ` Newest ${h.newest_session ? fmtDate(h.newest_session) : "none"}, last due ${fmtDate(h.last_expected_session)}.`));
    }
    if (m.last_marked) sess.append(el("p", { class: "muted", text: `Portfolios marked to the close of ${fmtDate(m.last_marked)}.` }));
    items.push(sess);

    // Missing and failed
    const mf = el("div", { class: "health-item" }, el("h3", { text: "Missing and failed sessions" }));
    const missing = Array.isArray(h.missing) ? h.missing : [];
    const failed = Array.isArray(h.failed) ? h.failed : [];
    if (!missing.length && !failed.length) mf.append(el("p", { text: m.start_date ? "None." : "None yet." }));
    if (missing.length) {
      const byDate = new Map();
      for (const x of missing) {
        if (!byDate.has(x.date)) byDate.set(x.date, []);
        byDate.get(x.date).push(labelOf(x.agent));
      }
      mf.append(el("p", { class: "list-label", text: `Missing (${missing.length})` }),
        el("ul", { class: "plain-list" }, [...byDate.entries()].sort((a, b) => (a[0] < b[0] ? 1 : -1)).map(([d, names]) =>
          el("li", null, el("span", { class: "nowrap", text: fmtDate(d) }), ": ", names.join(", ")))));
    }
    if (failed.length) {
      mf.append(el("p", { class: "list-label", text: `Failed (${failed.length})` }),
        el("ul", { class: "plain-list" }, failed.slice().sort((a, b) => (a.date < b.date ? 1 : -1)).map((x) =>
          el("li", null, el("span", { class: "nowrap", text: fmtDate(x.date) }), `: ${labelOf(x.agent)}`,
            x.reason ? el("span", { class: "muted", text: ` (${x.reason})` }) : null))));
    }
    items.push(mf);

    // Spend
    const b = m.budget || {};
    const sp = el("div", { class: "health-item" }, el("h3", { text: `API spend, ${fmtMonth(b.month)}` }));
    if (isNum(b.cap) && b.cap > 0) {
      const spent = isNum(b.spent) ? b.spent : 0;
      const proj = isNum(b.projection) ? b.projection : spent;
      sp.append(el("p", null, el("strong", { class: "big", text: money(spent, 2) }), ` of the ${money(b.cap, 0)} monthly cap`));
      const meter = el("div", { class: "meter", role: "img",
        "aria-label": `${money(spent, 2)} spent, ${money(proj, 2)} projected, cap ${money(b.cap, 0)}` });
      const fill = el("span", { class: "meter-fill" + (spent >= b.cap ? " over" : "") });
      fill.style.width = `${Math.min(100, (spent / b.cap) * 100)}%`;
      const tick = el("span", { class: "meter-proj" + (proj > b.cap ? " over" : "") });
      tick.style.left = `${Math.min(100, (proj / b.cap) * 100)}%`;
      meter.append(fill, tick);
      sp.append(meter);
      sp.append(el("p", null, proj > b.cap ? statusMark("warning", "Above the cap") : null,
        `${proj > b.cap ? " " : ""}Projected for the month at this pace: ${money(proj, 2)}.`));
      sp.append(el("p", { class: "muted", text: "Sessions, dry runs and digest summaries, from the harness's own records. At the cap, sessions stop until the next month." }));
    } else sp.append(el("p", { text: "No budget recorded." }));
    items.push(sp);

    return el("div", { class: "health" }, items);
  }

  function evidenceNote() {
    const stats = state.stats || {};
    const agents = agentsList();
    const n = (stats["bench:spy"] && stats["bench:spy"].days) || Math.max(0, ...agents.map((a) => (stats[a.name] || {}).days || 0));
    const box = el("aside", { class: "note" }, el("h3", { text: "What this much data can show" }));
    if (!n) {
      box.append(el("p", { text: "No trading day has been marked yet. The numbers start after the first close." }));
      return box;
    }
    const ses = agents.map((a) => (stats[a.name] || {}).excess_vs_spy_se).filter(isNum).map((x) => 2 * x * 100).sort((a, b) => a - b);
    if (!ses.length) {
      box.append(el("p", { text: `${plural(n, "trading day")} so far. A range needs at least two days of returns, so nothing here can be told apart from luck yet.` }));
    } else {
      const mid = ses.length % 2 ? ses[(ses.length - 1) / 2] : (ses[ses.length / 2 - 1] + ses[ses.length / 2]) / 2;
      box.append(el("p", { text:
        `${plural(n, "trading day")} so far. Over that stretch, an excess return within about ±${mid.toFixed(1)} points of zero ` +
        "cannot be told apart from luck. That figure is two standard errors of the daily excess returns, the median across the agents." }));
      const clear = agents.filter((a) => {
        const s = stats[a.name] || {};
        return isNum(s.excess_vs_spy) && isNum(s.excess_vs_spy_se) && s.excess_vs_spy_se > 0 &&
          Math.abs(s.excess_vs_spy) > 2 * s.excess_vs_spy_se;
      });
      if (!clear.length) box.append(el("p", { text: "Every agent's range against SPY still includes zero." }));
      else {
        box.append(el("p", { text:
          `The range against SPY excludes zero for ${clear.map((a) => a.label || a.name).join(" and ")}. ` +
          `With ${plural(n, "day")} and one run, that is a lead to keep watching; it would need to hold for months before it means much.` }));
      }
    }
    box.append(el("p", { text:
      "Each agent is a single run. A gap between two agents can come from the particular trades one run happened to make, " +
      "and the same prompt run again could land somewhere else. The range also treats days as independent, which flatters an " +
      "agent that holds the same few stocks for weeks." }));
    box.append(el("p", { class: "muted", text: "The range shrinks with the square root of the number of days: four times as many days halves it." }));
    return box;
  }

  function cellRange(x, se) {
    const r = range2se(x, se);
    return el("td", { class: "num" }, el("span", { class: "v", text: pts(x) }),
      el("span", { class: "sub", text: r ? `±2 SE: ${r}` : isNum(x) ? "range needs 2+ days" : "" }));
  }

  function resultsTable() {
    const stats = state.stats || {};
    const head = ["", "Total return", "Excess over SPY", "Excess over exposure-matched SPY", "Max drawdown",
      "Average invested", "Trades closed / open", "Turnover", "Slippage paid", "Sessions decided", "API spend"];
    const thead = el("thead", null, el("tr", null, head.map((h, i) => el("th", { scope: "col", class: i ? "num" : null, text: h }))));
    const tbody = el("tbody");
    for (const a of agentsList()) {
      const s = stats[a.name] || {};
      const has = (s.days || 0) > 0;
      tbody.append(el("tr", null,
        el("th", { scope: "row" }, el("a", { href: `#agent/${encodeURIComponent(a.name)}` }, swatch(a.name), a.label || a.name)),
        el("td", { class: "num", text: has ? pct(s.total_return) : DASH }),
        has ? cellRange(s.excess_vs_spy, s.excess_vs_spy_se) : el("td", { class: "num", text: DASH }),
        has ? cellRange(s.excess_vs_matched, s.excess_vs_matched_se) : el("td", { class: "num", text: DASH }),
        el("td", { class: "num", text: has ? pct(s.max_drawdown) : DASH }),
        el("td", { class: "num", text: has ? pctPlain(s.avg_invested) : DASH }),
        el("td", { class: "num", text: has ? `${s.trades_closed ?? 0} / ${s.trades_open ?? 0}` : DASH }),
        el("td", { class: "num", text: has && isNum(s.turnover) ? `${s.turnover.toFixed(2)}×` : DASH }),
        el("td", { class: "num", text: has ? money(s.slippage_paid) : DASH }),
        el("td", { class: "num", text: isNum(s.days_run) ? `${s.days_run} of ${plural(s.days || 0, "day")}` : DASH }),
        el("td", { class: "num", text: isNum(s.api_spend) ? money(s.api_spend, 2) : DASH })));
    }
    for (const b of benchList()) {
      const s = stats[b.name] || {};
      const has = (s.days || 0) > 0;
      const isSpy = b.name === "bench:spy";
      tbody.append(el("tr", { class: "bench" },
        el("th", { scope: "row" }, swatch(b.name), b.label || b.name),
        el("td", { class: "num", text: has ? pct(s.total_return) : DASH }),
        has && !isSpy ? cellRange(s.excess_vs_spy, s.excess_vs_spy_se) : el("td", { class: "num", text: DASH }),
        el("td", { class: "num", text: DASH }),
        el("td", { class: "num", text: has ? pct(s.max_drawdown) : DASH }),
        el("td", { class: "num", text: has ? pctPlain(s.avg_invested) : DASH }),
        el("td", { class: "num", text: DASH }),
        el("td", { class: "num", text: has && isNum(s.turnover) ? `${s.turnover.toFixed(2)}×` : DASH }),
        el("td", { class: "num", text: has ? money(s.slippage_paid) : DASH }),
        el("td", { class: "num", text: DASH }),
        el("td", { class: "num", text: DASH })));
    }
    return tableScroll(el("table", { class: "data results" }, thead, tbody), "Results per agent");
  }

  function resultsFootnotes() {
    return el("dl", { class: "footnotes" },
      el("dt", { text: "Excess" }), el("dd", { text: "The portfolio's cumulative return minus the comparison's over the same days, in percentage points. The range under it is plus or minus two standard errors, from the spread of the daily differences." }),
      el("dt", { text: "Exposure-matched SPY" }), el("dd", { text: "Each day, the agent's invested fraction from the day before times SPY's return, the rest in cash. Beating it means the stock picks did better than simply being that much in the market." }),
      el("dt", { text: "Max drawdown" }), el("dd", { text: "The largest fall from a previous high, starting from $100,000." }),
      el("dt", { text: "Turnover" }), el("dd", { text: "Value bought and sold, divided by average equity." }),
      el("dt", { text: "Slippage paid" }), el("dd", { text: "What the fill rule cost against the reference price, in dollars, stops and targets included." }),
      el("dt", { text: "Sessions decided" }), el("dd", { text: "Sessions that ended with a decision, against trading days marked. Holds and failures are listed on each agent's page." }));
  }

  function equityChart(container) {
    const eq = state.equity || {};
    const names = agentsList().map((a) => a.name).concat(benchList().map((b) => b.name));
    const d = chartData(names, (n) => rebased((eq.series || {})[n]));
    if (!d) {
      container.append(empty("Nothing to draw yet. The first point appears once the first trading day has closed and been marked."));
      return;
    }
    const dates = d.labels;
    const markers = [];
    const changes = eq.prompt_changes || {};
    for (const a of agentsList()) {
      for (const day of changes[a.name] || []) {
        const idx = dates.indexOf(day);
        if (idx > 0) markers.push({ idx, color: agentColor(a.name), text: "prompt edit" });
      }
    }
    const wrapper = el("div", { class: "chart" });
    container.append(wrapper);
    lineChart(wrapper, {
      labels: dates,
      height: [280, 360],
      series: d.series.map((s) => ({ label: labelOf(s.name), values: s.values, ...seriesStyle(s.name) })),
      fmt: (v) => v.toFixed(1),
      axisFmt: (v) => (Number.isInteger(v) ? String(v) : v.toFixed(1)),
      yRange: yRangeAround100,
      markers,
    });
    const listed = agentsList().filter((a) => (changes[a.name] || []).length);
    container.append(el("p", { class: "caption" },
      "Value of each $100,000 portfolio, with 100 as the starting cash. Benchmarks are the dashed grey lines. Hover or tap for values on a day.",
      listed.length ? " Prompt edits, marked with a thin vertical line: " +
        listed.map((a) => `${a.label || a.name} on ${changes[a.name].map(fmtDate).join(", ")}`).join("; ") +
        ". Numbers before and after an edit come from different prompts." : ""));
  }

  function comparisonTable() {
    const pairs = (state.comparison && Array.isArray(state.comparison.pairs)) ? state.comparison.pairs : [];
    if (!pairs.length) return empty("No pairs to compare yet.");
    const tbody = el("tbody");
    for (const p of pairs) {
      tbody.append(el("tr", null,
        el("th", { scope: "row" }, el("span", { class: "pair" }, swatch(p.a), labelOf(p.a)), el("span", { class: "pair-and", text: " and " }),
          el("span", { class: "pair" }, swatch(p.b), labelOf(p.b))),
        el("td", { class: "num", text: isNum(p.overlap) ? pctPlain(p.overlap) : DASH }),
        el("td", { class: "num", text: isNum(p.correlation) ? signed(p.correlation, 2) : DASH })));
    }
    return el("div", null,
      tableScroll(el("table", { class: "data compare" },
        el("thead", null, el("tr", null, el("th", { scope: "col", text: "Pair" }),
          el("th", { scope: "col", class: "num", text: "Holdings in common" }),
          el("th", { scope: "col", class: "num", text: "Correlation of daily returns" }))), tbody), "Agents side by side"),
      el("p", { class: "caption", text:
        "Holdings in common: the share of equity both hold in the same stocks today, counting the smaller weight of each stock. " +
        "Correlation: of the two daily return series, from 1 (move together) to −1 (move opposite). " +
        "A dash means it is not defined yet: correlation needs five days of returns from both and a book that moves; overlap needs at least one of the two to hold something." }));
  }

  function benchmarksSection() {
    return section("benchmarks", "Benchmarks",
      el("ul", { class: "defs" },
        el("li", null, el("strong", { text: "SPY buy and hold. " }), "The S&P 500 ETF, bought at the opening auction of day one with 0.10% slippage and held, dividends credited."),
        el("li", null, el("strong", { text: "QQQ buy and hold. " }), "The Nasdaq-100 ETF, bought and held the same way."),
        el("li", null, el("strong", { text: "Tech ten, equal weight. " }), "The ten stocks the Tech ten agent may trade, 10% each on day one, then held without rebalancing."),
        el("li", null, el("strong", { text: "Exposure-matched SPY. " }), "One per agent: SPY's daily return times the agent's invested fraction from the day before, the rest in cash. It shows what being that much in the market would have done without picking stocks.")));
  }

  function howSection() {
    const tt = Array.isArray(state.meta && state.meta.tech_ten) ? state.meta.tech_ten : [];
    return section("how", "How this works",
      el("ul", { class: "defs" },
        el("li", { text: "Four Claude agents each start with $100,000 of paper money. Prices are real (Alpaca market data); the money and the fills are simulated by the project's own ledger." }),
        el("li", { text: "Once a day, before the US open (from 13:30 Amsterdam time), each agent reads its own notes and a daily digest of market moves and headlines, researches, and submits orders. All agents use the same model, so the comparison is between strategies." }),
        el("li", { text: "Orders fill at that day's opening auction price. Slippage per side by company size: 0.10% above $10B market cap, 0.25% from $2B to $10B, 0.50% from $300M to $2B. No commission." }),
        el("li", { text: "Long only: no shorting, no leverage, no negative cash. The open-universe agents may buy US-listed stocks and ADRs priced at $5 or more with a market cap of at least $300M." }),
        el("li", { text: "Every buy carries a stop, a target and a horizon. Code checks stops and targets against each day's low and high and exits there, or at the open if the price gapped through. When a horizon passes, the agent has to close the position or extend it with a fresh thesis." }),
        el("li", { text: "The numbers on this page are rebuilt after each US close." + (tt.length ? ` The tech ten are ${tt.join(", ")}.` : "") })),
      el("h3", { text: "The agents" }),
      el("ul", { class: "defs" }, agentsList().map((a) =>
        el("li", null, el("a", { href: `#agent/${encodeURIComponent(a.name)}` }, swatch(a.name), el("strong", { text: a.label || a.name })), `. ${a.description || ""}`))),
      el("p", null, "Code, prompts, ledgers and every session log are public: ",
        el("a", { href: repoUrl(""), rel: "noopener noreferrer", text: "the GitHub repository" }), ", and the full design with every decision behind it is in ",
        el("a", { href: repoUrl("/blob/main/docs/PLAN.md"), rel: "noopener noreferrer", text: "docs/PLAN.md" }), "."));
  }

  function renderOverview(main) {
    const m = state.meta;
    const n = (state.stats && state.stats["bench:spy"] && state.stats["bench:spy"].days) || 0;
    const intro = m.start_date
      ? `Day one was ${fmtDate(m.start_date)}. ${n ? `${plural(n, "trading day")} marked so far, the latest ${fmtDate(m.last_marked)}.` : "No trading day has closed yet."}`
      : "The experiment has not started yet.";
    main.append(
      el("div", { class: "page-head" },
        el("h1", { text: "Four Claude agents trading paper money" }),
        el("p", { class: "lede", text: "Each agent has $100,000 of fake money and trades once a day before the US open, against real prices and a few plain benchmarks. " + intro })),
      healthStrip());

    const chartSec = section("equity", "Equity, rebased to 100");
    main.append(chartSec);
    equityChart(chartSec);

    main.append(section("results", "Results per agent",
      el("div", { class: "results-layout" }, el("div", { class: "results-main" }, resultsTable(), resultsFootnotes()), evidenceNote())));
    main.append(section("comparison", "Agents side by side", comparisonTable()));
    main.append(benchmarksSection());
    main.append(howSection());
  }

  // ---------------------------------------------------------------------------------------------
  // Agent page

  function tile(label, value, sub) {
    return el("div", { class: "tile" }, el("div", { class: "tile-label", text: label }), el("div", { class: "tile-value", text: value }),
      sub ? el("div", { class: "tile-sub", text: sub }) : null);
  }

  function sourceList(sources) {
    const list = (Array.isArray(sources) ? sources : []).map((s) => (typeof s === "string" ? { url: s } : s || {}));
    if (!list.length) return null;
    return el("ul", { class: "sources" }, list.map((s) => {
      const raw = String(s.url || "");
      const safe = httpsHref(raw);
      let item;
      if (safe) {
        const u = new URL(safe);
        const host = u.hostname.replace(/^www\./, "");
        const rest = (u.pathname + u.search).replace(/\/$/, "");
        item = el("li", null, extLink(safe, el("span", { class: "src-domain", text: host }), el("span", { class: "src-path", text: rest.length > 64 ? rest.slice(0, 63) + "…" : rest })));
      } else {
        item = el("li", null, el("span", { class: "src-domain", text: raw.slice(0, 120) || "(empty)" }), el("span", { class: "muted", text: " not linked: only https addresses are" }));
      }
      if (s.read) item.append(el("span", { class: "muted", text: " · read in the session" }));
      if (s.answer) item.append(el("div", { class: "src-answer", text: String(s.answer) }));
      return item;
    }));
  }

  function chainList(chain) {
    const steps = Array.isArray(chain) ? chain.filter((c) => c && String(c.step || "").trim()) : [];
    if (!steps.length) return null;
    return el("ol", { class: "chain" }, steps.map((c) => el("li", null, String(c.step),
      c.source_url ? el("div", { class: "chain-src" }, sourceList([c.source_url])) : null)));
  }

  function positionsBlock(a) {
    const pos = Array.isArray(a.positions) ? a.positions : [];
    if (!pos.length) return empty(state.meta.last_marked ? "No open positions. Everything is in cash." : "No positions yet.");
    return el("div", { class: "cards" }, pos.map((p) => {
      const last = p.last_close;
      const stopDist = isNum(p.stop_price) && isNum(last) && last ? p.stop_price / last - 1 : null;
      const tgtDist = isNum(p.target_price) && isNum(last) && last ? p.target_price / last - 1 : null;
      const passed = p.horizon_end && state.meta.last_marked && p.horizon_end <= state.meta.last_marked;
      const kv = (k, v, sub) => el("div", { class: "kv" }, el("dt", { text: k }), el("dd", null, v, sub ? el("span", { class: "sub", text: sub }) : null));
      const card = el("article", { class: "card" },
        el("header", { class: "card-head" }, el("h3", { text: String(p.ticker) }), el("span", { class: "muted", text: `${pctPlain(p.weight, 1)} of equity` })),
        el("dl", { class: "kv-grid" },
          kv("P&L", pct(p.pnl_pct), `${money(p.value)} now`),
          kv("Stop", isNum(p.stop_price) ? money(p.stop_price, 2) : DASH, stopDist != null ? `${pct(stopDist)} from last close` : null),
          kv("Target", isNum(p.target_price) ? money(p.target_price, 2) : DASH, tgtDist != null ? `${pct(tgtDist)} from last close` : null),
          kv("Horizon ends", p.horizon_end ? fmtDate(p.horizon_end) : DASH, passed ? "passed, needs an answer" : null),
          kv("Opened", fmtDate(p.opened), isNum(p.avg_cost) ? `average cost ${money(p.avg_cost, 2)}` : null)),
        el("p", { class: "thesis", text: p.thesis ? String(p.thesis) : "No thesis recorded." }));
      if (p.extensions && p.original_thesis && p.original_thesis !== p.thesis) {
        card.append(el("div", { class: "original" },
          el("p", { class: "list-label", text: `Extended ${plural(Number(p.extensions), "time")}. Original thesis, ${fmtDate(p.opened)}:` }),
          el("p", { class: "thesis", text: String(p.original_thesis) })));
      }
      return card;
    }));
  }

  const EXIT = {
    close: "closed by the agent",
    set_weight: "sold down by the agent",
  };

  function tradesBlock(a) {
    const trades = Array.isArray(a.trades) ? a.trades : [];
    if (!trades.length) {
      const days = (state.stats[a.name] || {}).days || 0;
      return empty(days ? `No trades in ${plural(days, "trading day")}.` : "No trades yet.");
    }
    const head = ["Ticker", "Opened", "Closed", "Return", "SPY", "Excess", "Exit", "Probability"];
    const tbody = el("tbody");
    for (const t of trades) {
      const open = !t.closed;
      tbody.append(el("tr", { class: "trade" },
        el("th", { scope: "row", text: String(t.ticker) }),
        el("td", { text: fmtDate(t.opened) }),
        el("td", { text: open ? "still open" : fmtDate(t.closed) }),
        el("td", { class: "num", text: open ? DASH : pct(t.return) }),
        el("td", { class: "num", text: open ? DASH : pct(t.spy_return) }),
        el("td", { class: "num", text: open ? DASH : pts(t.excess) }),
        el("td", { text: open ? DASH : EXIT[t.exit_reason] || String(t.exit_reason || DASH) }),
        el("td", { class: "num", text: isNum(t.probability) ? t.probability.toFixed(2) : DASH })));
      const details = el("details", { class: "detail-body" }, el("summary", { text: "Thesis, sources" + (Array.isArray(t.causal_chain) && t.causal_chain.length ? ", causal chain" : "") }));
      details.append(el("p", { class: "thesis", text: t.thesis ? String(t.thesis) : "No thesis recorded." }));
      const facts = [];
      if (isNum(t.horizon_days)) facts.push(`Horizon ${plural(t.horizon_days, "trading day")}${t.horizon_end ? `, ending ${fmtDate(t.horizon_end)}` : ""}`);
      if (isNum(t.stop_pct) || isNum(t.target_pct)) facts.push(`stop ${isNum(t.stop_pct) ? t.stop_pct + "%" : DASH} below and target ${isNum(t.target_pct) ? t.target_pct + "%" : DASH} above the fill`);
      if (isNum(t.dividends) && t.dividends > 0) facts.push(`dividends ${money(t.dividends, 2)}`);
      if (facts.length) details.append(el("p", { class: "muted", text: facts.join("; ") + "." }));
      if (Array.isArray(t.extensions) && t.extensions.length) {
        details.append(el("p", { class: "list-label", text: "Extensions" }),
          el("ul", { class: "plain-list" }, t.extensions.map((x) => el("li", null, el("span", { class: "nowrap", text: fmtDate(x.date) }), `: ${x.thesis || ""}`,
            x.horizon_end ? el("span", { class: "muted", text: ` (new horizon ${fmtDate(x.horizon_end)})` }) : null))));
      }
      const src = sourceList(t.sources);
      details.append(el("p", { class: "list-label", text: "Sources" }), src || el("p", { class: "muted", text: "None cited." }));
      const ch = chainList(t.causal_chain);
      if (ch) details.append(el("p", { class: "list-label", text: "Causal chain" }), ch);
      tbody.append(el("tr", { class: "detail" }, el("td", { colspan: String(head.length) }, details)));
    }
    return tableScroll(el("table", { class: "data trades" },
      el("thead", null, el("tr", null, head.map((h, i) => el("th", { scope: "col", class: i >= 3 && i !== 6 ? "num" : null, text: h })))), tbody), "Trade log");
  }

  const ACTION = { set_weight: "set weight", close: "close", extend: "extend" };

  function ordersBlock(a) {
    const orders = Array.isArray(a.orders) ? a.orders : [];
    if (!orders.length) return empty("No orders yet.");
    const head = ["Session", "Ticker", "Action", "Target weight", "Stop", "Target", "Horizon", "Probability"];
    const row = (o) => {
      const close = o.action === "close";
      return el("tr", null,
        el("td", { text: fmtDate(o.session_date) }),
        el("th", { scope: "row", text: String(o.ticker) }),
        el("td", { text: ACTION[o.action] || String(o.action || DASH) }),
        el("td", { class: "num", text: o.action === "set_weight" ? pctPlain(o.target_weight, 1) : DASH }),
        el("td", { class: "num", text: !close && isNum(o.stop_pct) ? `${MINUS}${o.stop_pct}%` : DASH }),
        el("td", { class: "num", text: !close && isNum(o.target_pct) ? `+${o.target_pct}%` : DASH }),
        el("td", { class: "num", text: !close && isNum(o.horizon_days) ? `${o.horizon_days} d` : DASH }),
        el("td", { class: "num", text: !close && isNum(o.probability) ? o.probability.toFixed(2) : DASH }));
    };
    const table = (rows) => tableScroll(el("table", { class: "data orders" },
      el("thead", null, el("tr", null, head.map((h, i) => el("th", { scope: "col", class: i >= 3 ? "num" : null, text: h })))),
      el("tbody", null, rows.map(row))), "Recent orders");
    const out = el("div", null, table(orders.slice(0, 12)));
    if (orders.length > 12) out.append(el("details", { class: "more" }, el("summary", { text: `Show ${orders.length - 12} older orders` }), table(orders.slice(12))));
    out.append(el("p", { class: "caption", text: "Orders fill at the opening auction of the session's day. Stop and target are percentages from the fill price; horizon is in trading days; probability is the agent's stated chance of beating SPY over the horizon." }));
    return out;
  }

  function sessionsBlock(a) {
    const sess = Array.isArray(a.sessions) ? a.sessions : [];
    if (!sess.length) return empty("No sessions have run yet.");
    const kind = { decided: "good", hold: "warning", failed: "critical" };
    const row = (s) => {
      const notes = [];
      if (s.reason) notes.push(String(s.reason));
      const rej = Array.isArray(s.rejected) ? s.rejected : [];
      return el("tr", null,
        el("th", { scope: "row", text: fmtDate(s.date) }),
        el("td", null, statusMark(kind[s.status] || "neutral", String(s.status || "unknown"))),
        el("td", { class: "num", text: isNum(s.orders) ? String(s.orders) : DASH }),
        el("td", { class: "num", text: isNum(s.cost) ? money(s.cost, 2) : DASH }),
        el("td", { class: "wrap-cell" }, notes.join(" "), rej.length ? el("details", { class: "rejected" },
          el("summary", { text: `${plural(rej.length, "order")} rejected` }), el("ul", { class: "plain-list" }, rej.map((r) => el("li", { text: String(r) })))) : null),
        el("td", null, httpsHref(s.url) ? extLink(s.url, "files") : DASH));
    };
    const table = (rows) => tableScroll(el("table", { class: "data sessions" },
      el("thead", null, el("tr", null, ["Date", "Status", "Orders", "Cost", "Note", "On GitHub"].map((h, i) =>
        el("th", { scope: "col", class: i === 2 || i === 3 ? "num" : null, text: h })))),
      el("tbody", null, rows.map(row))), "Sessions");
    const out = el("div", null, table(sess.slice(0, 10)));
    if (sess.length > 10) out.append(el("details", { class: "more" }, el("summary", { text: `Show ${sess.length - 10} older sessions` }), table(sess.slice(10))));
    out.append(el("p", { class: "caption", text: "Decided: the agent submitted a decision, possibly with no orders. Hold: the session ended without one and nothing traded. Failed: an error stopped it. Each session folder holds the transcript, the decision and the token costs." }));
    return out;
  }

  function mdBlock(src, emptyText) {
    const box = markdown(src);
    return box.childNodes.length ? box : empty(emptyText);
  }

  function agentCharts(container, name) {
    const eq = state.equity || {};
    const labels = chartData([name], () => [])?.labels;
    if (!labels) {
      container.append(empty("Nothing to draw yet. The first point appears once the first trading day has closed and been marked."));
      return;
    }
    const ser = [];
    const own = rebased((eq.series || {})[name]);
    if (own) ser.push({ label: labelOf(name), values: own, ...seriesStyle(name) });
    const spy = rebased((eq.series || {})["bench:spy"]);
    if (spy) ser.push({ label: labelOf("bench:spy"), values: spy, ...seriesStyle("bench:spy") });
    const matched = rebased((eq.exposure_matched || {})[name]);
    if (matched) ser.push({ label: "Exposure-matched SPY", values: matched, ...seriesStyle("bench:tech-ten-ew"), color: cssVar("--bench-2") });
    const markers = ((eq.prompt_changes || {})[name] || []).map((d) => ({ idx: labels.indexOf(d), color: agentColor(name), text: "prompt edit" })).filter((m) => m.idx > 0);
    const w1 = el("div", { class: "chart" });
    container.append(w1);
    lineChart(w1, { labels, height: [240, 300], series: ser, fmt: (v) => v.toFixed(1),
      axisFmt: (v) => (Number.isInteger(v) ? String(v) : v.toFixed(1)), yRange: yRangeAround100, markers });
    container.append(el("p", { class: "caption", text: "Rebased to 100 at the starting cash. The exposure-matched line holds SPY in the same proportion the agent was invested the day before, and cash for the rest." +
      (markers.length ? ` The thin vertical line marks a prompt edit on ${((eq.prompt_changes || {})[name] || []).map(fmtDate).join(", ")}.` : "") }));

    const inv = (eq.invested_fraction || {})[name];
    if (Array.isArray(inv) && inv.length) {
      const vals = [0].concat(inv.map((v) => (isNum(v) ? v * 100 : null)));
      container.append(el("h3", { text: "Share of equity invested, at each close" }));
      const w2 = el("div", { class: "chart chart-small" });
      container.append(w2);
      const c = agentColor(name);
      lineChart(w2, { labels, height: [140, 160], series: [{ label: "Invested", values: vals, color: c, width: 2, fill: hexA(c, 0.12) }],
        fmt: (v) => `${v.toFixed(0)}%`, yRange: () => [0, 100], markers: [] });
    }
  }

  function renderAgent(main, name, a) {
    const s = state.stats[name] || {};
    const has = (s.days || 0) > 0;
    const rs = range2se(s.excess_vs_spy, s.excess_vs_spy_se);
    const rm = range2se(s.excess_vs_matched, s.excess_vs_matched_se);
    main.append(el("div", { class: "page-head" },
      el("p", { class: "crumb" }, el("a", { href: "#", text: "Overview" })),
      el("h1", { class: "agent-title" }, swatch(name), String(a.label || name)),
      el("p", { class: "lede", text: String(a.description || "") })));
    main.append(el("div", { class: "tiles" },
      tile("Equity", money(a.equity), `${money(a.cash)} in cash`),
      tile("Total return", has ? pct(s.total_return) : DASH, has ? `SPY ${pct(s.spy_return)} over the same days` : "after the first close"),
      tile("Excess over SPY", has ? pts(s.excess_vs_spy) : DASH, rs ? `±2 SE: ${rs}` : null),
      tile("Over exposure-matched SPY", has ? pts(s.excess_vs_matched) : DASH, rm ? `±2 SE: ${rm}` : null),
      tile("Sessions decided", isNum(s.days_run) ? String(s.days_run) : DASH, `of ${plural(s.days || 0, "trading day")} marked`),
      tile("API spend", isNum(s.api_spend) ? money(s.api_spend, 2) : DASH, "all sessions so far")));
    main.append(el("p", { class: "brier" }, isNum(s.brier) && s.brier_n
      ? `Brier score of the stated probabilities: ${s.brier.toFixed(3)}, over ${plural(s.brier_n, "settled trade")}. 0 is perfect; saying 0.5 every time scores 0.250.`
      : "A Brier score for the stated probabilities appears once a trade has settled."));

    const chartSec = section("agent-equity", "Equity against SPY");
    main.append(chartSec);
    agentCharts(chartSec, name);

    main.append(section("positions", "Current positions", positionsBlock(a)));
    main.append(section("trades", "Trade log", tradesBlock(a)));
    main.append(section("orders", "Recent orders", ordersBlock(a)));
    main.append(section("sessions", "Sessions", sessionsBlock(a)));
    main.append(el("div", { class: "prose-grid" },
      section("summary", "Latest session summary", mdBlock(a.summary, "No session summary yet.")),
      section("notes", "General notes", mdBlock(a.notes, "The agent has not written general notes yet."))));
    const tickers = a.tickers && typeof a.tickers === "object" ? Object.entries(a.tickers) : [];
    main.append(section("ticker-notes", "Ticker notes", tickers.length
      ? el("div", { class: "ticker-notes" }, tickers.map(([t, src]) => el("details", { class: "note-file" },
        el("summary", { text: String(t) }), mdBlock(src, "Empty file."))))
      : empty("No ticker notes yet.")));
    main.append(section("prompt", "Prompt",
      el("details", { class: "note-file" }, el("summary", { text: "The agent's own prompt, on top of the shared system prompt" }), mdBlock(a.prompt, "No prompt file."))));
    main.append(el("p", { class: "caption" }, "Notes, summaries and theses are written by the model and shown as written. ",
      el("a", { href: repoUrl(`/tree/main/agents/${encodeURIComponent(name)}`), rel: "noopener noreferrer", text: "This agent's folder on GitHub" }), "."));
  }

  // ---------------------------------------------------------------------------------------------
  // Router

  function errorView(main, e) {
    main.append(el("div", { class: "page-head" }, el("h1", { text: "Four Claude agents trading paper money" })),
      el("div", { class: "notice" },
        el("p", null, el("strong", { text: e && e.status === 404 ? "The data files are not published yet. " : "The data could not be loaded. " }),
          e && e.status === 404
            ? "They appear after the first marking job runs, after a US close."
            : "The data host may be unreachable; reloading in a minute usually helps."),
        el("p", { class: "muted", text: `Looked in ${BASE}${e && e.message ? ` (${e.message})` : ""}.` })));
  }

  async function render() {
    const main = document.getElementById("main");
    const route = decodeURIComponent(location.hash.replace(/^#\/?/, ""));
    charts.forEach((c) => c.destroy());
    charts = [];
    try {
      await loadCore();
    } catch (e) {
      main.replaceChildren();
      renderNav("overview");
      errorView(main, e);
      return;
    }
    renderBanner();
    renderFooter();
    const agentMatch = /^agent\/(.+)$/.exec(route);
    if (agentMatch) {
      const name = agentMatch[1];
      const known = agentsList().find((a) => a.name === name);
      renderNav(name);
      main.replaceChildren(el("p", { class: "muted loading", text: "Loading agent." }));
      let a = null;
      let err = null;
      if (known) {
        try { a = await loadAgent(name); } catch (e) { err = e; }
      }
      main.replaceChildren();
      if (!known || !a) {
        main.append(el("div", { class: "page-head" }, el("p", { class: "crumb" }, el("a", { href: "#", text: "Overview" })),
          el("h1", { text: known ? String(known.label || name) : "No such agent" }),
          el("p", { class: "empty", text: known ? `This agent's data file could not be loaded${err ? ` (${err.message})` : ""}.` : "There is no agent by that name." })));
        return;
      }
      document.title = `${a.label || name} · Trading agents`;
      renderAgent(main, name, a);
      window.scrollTo(0, 0);
      return;
    }
    document.title = "Trading agents";
    renderNav(route === "how" ? "how" : "overview");
    main.replaceChildren();
    renderOverview(main);
    if (route && route !== "how" && document.getElementById(route) == null) history.replaceState(null, "", "#");
    const target = route && document.getElementById(route);
    if (target) target.scrollIntoView();
    else window.scrollTo(0, 0);
  }

  window.addEventListener("hashchange", render);
  const scheme = window.matchMedia("(prefers-color-scheme: dark)");
  if (scheme.addEventListener) scheme.addEventListener("change", render);
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", render);
  else render();
})();
