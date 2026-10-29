// The trading-agents dashboard Worker. Everything it serves is bundled into the script as text:
// the page, the app script and stylesheet, and the vendored libraries. No storage, no secrets.
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

function renderPage(base) {
  return page
    .replaceAll("{{DATA_BASE}}", escapeAttr(base.href))
    .replace(/\{\{v:([^}]+)\}\}/g, (_, path) => VERSIONS[path] || "0");
}

export default {
  async fetch(request, env) {
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
const MARK = { workflow: "mark.yml", inputs: {} };
const SCHEDULE = {
  "32 12 * * 1-5": SESSION,
  "44 12 * * 1-5": SESSION,
  "50 21 * * 1-5": MARK,
  "20 23 * * 1-5": MARK,
};
