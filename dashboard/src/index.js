// The trading-agents dashboard Worker. Everything it serves is bundled into the script as text:
// the page, the app script and stylesheet, and the vendored libraries. Two small JSON endpoints,
// /api/live and /api/intraday, read prices from Alpaca with the ALPACA_KEY / ALPACA_SECRET secrets
// for the symbols in holdings.json only. No storage.
import { isTradingDay, sessionBounds } from "./calendar.js";
import page from "../app/index.html";
import appJs from "../app/app.js";
import appCss from "../app/app.css";
import favicon from "../app/favicon.svg";
import uplotJs from "../vendor/uPlot.iife.min.js";
import uplotCss from "../vendor/uPlot.min.css";
import markedJs from "../vendor/marked.umd.js";
import purifyJs from "../vendor/purify.min.js";
import monoRegular from "../vendor/jetbrains-mono-400.woff2";
import monoMedium from "../vendor/jetbrains-mono-500.woff2";
import monoBold from "../vendor/jetbrains-mono-700.woff2";
import interTight from "../vendor/inter-tight-800.woff2";

const DEFAULT_DATA_BASE = "https://raw.githubusercontent.com/Stasieniec/trading-agents/main/site-data/";

const JS = "text/javascript; charset=utf-8";
const CSS = "text/css; charset=utf-8";
const FONT = "font/woff2";
const FILES = {
  "/app.js": [appJs, JS],
  "/favicon.svg": [favicon, "image/svg+xml"],
  "/vendor/uPlot.iife.min.js": [uplotJs, JS],
  "/vendor/uPlot.min.css": [uplotCss, CSS],
  "/vendor/marked.umd.js": [markedJs, JS],
  "/vendor/purify.min.js": [purifyJs, JS],
  "/vendor/jetbrains-mono-400.woff2": [monoRegular, FONT],
  "/vendor/jetbrains-mono-500.woff2": [monoMedium, FONT],
  "/vendor/jetbrains-mono-700.woff2": [monoBold, FONT],
  "/vendor/inter-tight-800.woff2": [interTight, FONT],
};

// A short content hash per file. The page links each file as ?v=<hash>, so a file can be cached for
// a year and a deploy still reaches every browser within the page's own cache time.
function hash(body) {
  let h = 0x811c9dc5;
  if (typeof body === "string") {
    for (let i = 0; i < body.length; i++) {
      h ^= body.charCodeAt(i);
      h = Math.imul(h, 0x01000193);
    }
  } else {
    const bytes = new Uint8Array(body);
    for (let i = 0; i < bytes.length; i++) {
      h ^= bytes[i];
      h = Math.imul(h, 0x01000193);
    }
  }
  return (h >>> 0).toString(36);
}
const VERSIONS = Object.fromEntries(Object.entries(FILES).map(([path, [body]]) => [path, hash(body)]));
// The stylesheet links the fonts by version too, so its own version is taken after filling those in.
const APP_CSS = appCss.replace(/\{\{v:([^}]+)\}\}/g, (_, path) => VERSIONS[path] || "0");
const APP_CSS_VERSION = hash(APP_CSS);
VERSIONS["/app.css"] = APP_CSS_VERSION;

function escapeAttr(s) {
  return s.replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

// DATA_BASE is configuration, but it still goes through URL parsing before it reaches the page or
// the CSP. Only http(s) is accepted; anything else falls back to the default.
function dataBase(env) {
  try {
    const u = new URL(env.DATA_BASE || DEFAULT_DATA_BASE);
    if (u.protocol !== "https:" && u.protocol !== "http:") throw new Error("bad scheme");
    if (!u.pathname.endsWith("/")) u.pathname += "/";
    u.search = "";
    u.hash = "";
    return u;
  } catch {
    return new URL(DEFAULT_DATA_BASE);
  }
}

function securityHeaders(dataOrigin) {
  return {
    "Content-Security-Policy": [
      "default-src 'none'",
      "script-src 'self'",
      "style-src 'self'",
      "img-src 'self' data:",
      "font-src 'self'",
      `connect-src 'self' ${dataOrigin}`,
      "base-uri 'none'",
      "form-action 'none'",
      "frame-ancestors 'none'",
    ].join("; "),
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
  };
}

// ---------------------------------------------------------------------------------------------
// Live prices. The symbol list comes only from holdings.json, never from the request, so the
// endpoints cannot be used to query Alpaca for anything else. Upstream errors become a status code
// and a fixed message; nothing from Alpaca's error body or our request headers is passed on.

const ALPACA_DEFAULT = "https://data.alpaca.markets";
const SYMBOL = /^[A-Z][A-Z0-9.-]{0,9}$/;
const MAX_SYMBOLS = 300;
const API_TTL = { "/api/live": 15, "/api/intraday": 60 };

class PublicError extends Error {
  constructor(status, message, upstream) {
    super(message);
    this.status = status;
    this.upstream = upstream;
  }
}

// Dev can point this at the mock in dev/serve-mock.mjs; plain http is accepted only for localhost.
function alpacaBase(env) {
  try {
    const u = new URL(env.ALPACA_DATA_BASE || ALPACA_DEFAULT);
    const local = u.hostname === "localhost" || u.hostname === "127.0.0.1";
    if (u.protocol !== "https:" && !(u.protocol === "http:" && local)) throw new Error("bad scheme");
    return u.origin + u.pathname.replace(/\/+$/, "");
  } catch {
    return ALPACA_DEFAULT;
  }
}

let holdingsMemo = null;

async function loadHoldings(base) {
  const now = Date.now();
  if (holdingsMemo && holdingsMemo.base === base.href && now - holdingsMemo.at < 60000) return holdingsMemo.data;
  let j;
  try {
    const r = await fetch(new URL("holdings.json", base).href, { cf: { cacheTtl: 60, cacheEverything: true } });
    if (!r.ok) throw new Error(String(r.status));
    j = await r.json();
  } catch {
    throw new PublicError(502, "holdings unavailable");
  }
  const symbols = [...new Set((Array.isArray(j && j.symbols) ? j.symbols : [])
    .filter((x) => typeof x === "string" && SYMBOL.test(x)))].slice(0, MAX_SYMBOLS);
  const day = j && typeof j.trading_day === "string" && /^\d{4}-\d{2}-\d{2}$/.test(j.trading_day) ? j.trading_day : null;
  const data = { symbols, trading_day: day };
  holdingsMemo = { at: now, base: base.href, data };
  return data;
}

async function alpacaGet(env, path, params) {
  const url = `${alpacaBase(env)}${path}?${new URLSearchParams(params)}`;
  let r;
  try {
    r = await fetch(url, {
      headers: { "APCA-API-KEY-ID": env.ALPACA_KEY, "APCA-API-SECRET-KEY": env.ALPACA_SECRET, Accept: "application/json" },
      signal: AbortSignal.timeout(8000),
    });
  } catch {
    throw new PublicError(502, "price source unreachable");
  }
  if (!r.ok) {
    try { await r.body?.cancel(); } catch { /* ignore */ }
    throw new PublicError(502, "price source error", r.status);
  }
  try {
    return await r.json();
  } catch {
    throw new PublicError(502, "price source error", r.status);
  }
}

const iso = (t) => new Date(t).toISOString();

async function apiLive(env, base) {
  const h = await loadHoldings(base);
  const out = { as_of: iso(Date.now()), trading_day: h.trading_day, prices: {} };
  if (!h.symbols.length) return out;
  const j = await alpacaGet(env, "/v2/stocks/snapshots", { symbols: h.symbols.join(","), feed: "iex" });
  const snaps = j && typeof j === "object" ? (j.snapshots && typeof j.snapshots === "object" ? j.snapshots : j) : {};
  for (const sym of h.symbols) {
    const lt = snaps[sym] && snaps[sym].latestTrade;
    const t = lt && Date.parse(lt.t);
    if (lt && Number.isFinite(Number(lt.p)) && Number(lt.p) > 0 && Number.isFinite(t)) out.prices[sym] = { price: Number(lt.p), time: iso(t) };
  }
  return out;
}

async function apiIntraday(env, base) {
  const h = await loadHoldings(base);
  const day = h.trading_day;
  const out = { as_of: iso(Date.now()), trading_day: day, open: null, bars: {} };
  if (!day || !isTradingDay(day) || !h.symbols.length) return out;
  const { open, close } = sessionBounds(day);
  out.open = iso(open);
  const end = Math.min(Date.now(), close);
  if (end <= open) return out;
  const params = { symbols: h.symbols.join(","), timeframe: "5Min", feed: "iex", start: iso(open), end: iso(end), limit: "10000" };
  for (let page = 0; page < 50; page++) {
    const j = await alpacaGet(env, "/v2/stocks/bars", params);
    const bars = j && typeof j.bars === "object" && j.bars ? j.bars : {};
    for (const sym of h.symbols) {
      for (const b of Array.isArray(bars[sym]) ? bars[sym] : []) {
        const t = Date.parse(b && b.t);
        const c = Number(b && b.c);
        if (Number.isFinite(t) && Number.isFinite(c) && c > 0) (out.bars[sym] = out.bars[sym] || []).push([Math.round(t / 1000), c]);
      }
    }
    if (!j || typeof j.next_page_token !== "string" || !j.next_page_token) break;
    params.page_token = j.next_page_token;
  }
  for (const sym of Object.keys(out.bars)) out.bars[sym].sort((a, b) => a[0] - b[0]);
  return out;
}

function jsonResponse(status, body, headers, cache) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { ...headers, "Content-Type": "application/json; charset=utf-8", "Cache-Control": cache },
  });
}

// One Alpaca call per TTL for everyone: the answer, errors included, is kept in the edge cache.
async function api(request, env, ctx, base, headers, path) {
  if (!env.ALPACA_KEY || !env.ALPACA_SECRET) {
    return jsonResponse(503, { error: "live prices not configured" }, headers, "no-store");
  }
  const key = new Request(new URL(path, request.url).href, { method: "GET" });
  const cache = caches.default;
  let resp = await cache.match(key);
  if (!resp) {
    let status = 200, body;
    try {
      body = await (path === "/api/live" ? apiLive : apiIntraday)(env, base);
    } catch (e) {
      status = e instanceof PublicError ? e.status : 502;
      body = { error: e instanceof PublicError ? e.message : "live prices unavailable" };
      if (e instanceof PublicError && e.upstream) body.upstream_status = e.upstream;
    }
    resp = jsonResponse(status, body, headers, `public, max-age=${API_TTL[path]}`);
    ctx.waitUntil(cache.put(key, resp.clone()));
  }
  return request.method === "HEAD" ? new Response(null, resp) : resp;
}

function renderPage(base) {
  return page
    .replaceAll("{{DATA_BASE}}", escapeAttr(base.href))
    .replace(/\{\{v:([^}]+)\}\}/g, (_, path) => VERSIONS[path] || "0");
}

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    const base = dataBase(env);
    const headers = securityHeaders(base.origin);
    const method = request.method;

    if (method !== "GET" && method !== "HEAD") {
      return new Response("Method not allowed\n", {
        status: 405,
        headers: { ...headers, Allow: "GET, HEAD", "Content-Type": "text/plain; charset=utf-8" },
      });
    }

    if (API_TTL[url.pathname]) return api(request, env, ctx, base, headers, url.pathname);

    let body, type, cache, status = 200;
    if (url.pathname === "/" || url.pathname === "/index.html") {
      body = renderPage(base);
      type = "text/html; charset=utf-8";
      cache = "public, max-age=300";
    } else if (url.pathname === "/app.css") {
      body = APP_CSS;
      type = CSS;
      cache = url.searchParams.get("v") === APP_CSS_VERSION ? "public, max-age=31536000, immutable" : "public, max-age=300";
    } else if (FILES[url.pathname]) {
      [body, type] = FILES[url.pathname];
      cache = url.searchParams.get("v") === VERSIONS[url.pathname]
        ? "public, max-age=31536000, immutable"
        : "public, max-age=300";
    } else if (url.pathname === "/robots.txt") {
      body = "User-agent: *\nAllow: /\n";
      type = "text/plain; charset=utf-8";
      cache = "public, max-age=86400";
    } else if (url.pathname === "/favicon.ico") {
      return new Response(null, { status: 301, headers: { ...headers, Location: "/favicon.svg" } });
    } else {
      body = "Not found\n";
      type = "text/plain; charset=utf-8";
      cache = "public, max-age=60";
      status = 404;
    }
    return new Response(method === "HEAD" ? null : body, {
      status,
      headers: { ...headers, "Content-Type": type, "Cache-Control": cache },
    });
  },

  // GitHub's own cron fires hours late or not at all, so these Cloudflare crons start the workflows.
  // The session workflow runs its usual gate (trading day, 13:30 Amsterdam, 30 minutes before the
  // open, not already done), so an extra or early trigger does nothing.
  async scheduled(event, env, ctx) {
    const token = env.GITHUB_DISPATCH_TOKEN;
    if (!token) {
      console.log("GITHUB_DISPATCH_TOKEN not set; skipping", event.cron);
      return;
    }
    const job = SCHEDULE[event.cron];
    if (!job) return;
    // The connection to GitHub sometimes times out (a 522 was seen on 29 Oct), so retry a few times.
    for (const wait of [0, 5000, 20000, 60000]) {
      if (wait) await new Promise((r) => setTimeout(r, wait));
      try {
        const r = await fetch(`https://api.github.com/repos/Stasieniec/trading-agents/actions/workflows/${job.workflow}/dispatches`, {
          method: "POST",
          headers: {
            Authorization: `Bearer ${token}`,
            Accept: "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "trading-agents-scheduler",
          },
          body: JSON.stringify({ ref: "main", inputs: job.inputs }),
        });
        console.log(event.cron, job.workflow, r.status);
        if (r.status === 204) return;
        if (r.status >= 400 && r.status < 500) return; // a bad token or input will not fix itself
      } catch (e) {
        console.log(event.cron, job.workflow, "fetch failed", String(e).slice(0, 120));
      }
    }
  },
};

const SESSION = { workflow: "session.yml", inputs: { dry_run: "false", gated: "true", hard_cap: "2.0" } };
const FILL = { workflow: "mark.yml", inputs: { mode: "fill" } };
const MARK = { workflow: "mark.yml", inputs: { mode: "close" } };
// UTC. Sessions before the open, a late-session safety net (the gate skips it if today already ran),
// fill passes every hour of the session, and the evening marking after the close plus the data delay.
const SCHEDULE = {
  "32,44 12 * * 1-5": SESSION,
  "40 13,15 * * 1-5": SESSION,
  "50 13-19 * * 1-5": FILL,
  "20 22,23 * * 1-5": MARK,
};
