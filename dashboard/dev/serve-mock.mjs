// Dev server. Serves dev/mock/ with CORS headers, standing in for raw.githubusercontent.com, and a
// mock of the two Alpaca market-data endpoints the Worker calls, so /api/live and /api/intraday run
// through the real Worker code.
//
//   node dev/serve-mock.mjs [port] [--now 2026-10-28T17:30:00Z]
//   DATA_BASE          = http://localhost:<port>/<scenario>/
//   ALPACA_DATA_BASE   = http://localhost:<port>/alpaca/<scenario>
//
// The mock Alpaca walks each symbol from the day's open to its close (dev/mock/<scenario>/_alpaca.json)
// with a small wiggle, up to --now. It insists on the two APCA headers, answers 403 with the key in
// the body when the key is "bad" (to check the Worker never passes that on), and pages bar results
// 40 at a time so pagination is exercised. GET /__log lists the Alpaca requests it has seen.
import { createServer } from "node:http";
import { readFile } from "node:fs/promises";
import { join, normalize, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "mock");
const args = process.argv.slice(2);
const port = Number(args.find((a) => /^\d+$/.test(a)) || 8790);
const nowArg = args.includes("--now") ? args[args.indexOf("--now") + 1] : null;
const NOW = () => (nowArg ? Date.parse(nowArg) : Date.now());
const log = [];

function seedHash(s) {
  let h = 7;
  for (const c of s) h = (h * 31 + c.charCodeAt(0)) % 1000003;
  return h;
}

function priceAt(seed, sym, t, openMs) {
  const s = seed.symbols[sym];
  const frac = Math.max(0, Math.min(1, (t - openMs) / (6.5 * 3600e3)));
  const base = s.o + (s.c - s.o) * frac;
  return Number((base * (1 + 0.004 * Math.sin(t / 9e5 + seedHash(sym)))).toFixed(4));
}

// 09:30 New York on the seed's day, in ms. New York is UTC-4 until 1 Nov 2026, UTC-5 after.
function openOf(day) {
  const off = day < "2026-11-01" ? 4 : 5;
  return Date.parse(`${day}T${String(9 + off).padStart(2, "0")}:30:00Z`);
}

async function alpaca(req, res, scenario, path, q) {
  log.push({ path, query: Object.fromEntries(q), at: new Date().toISOString() });
  const key = req.headers["apca-api-key-id"], secret = req.headers["apca-api-secret-key"];
  const send = (status, body) => {
    res.writeHead(status, { "Content-Type": "application/json" });
    res.end(JSON.stringify(body));
  };
  if (!key || !secret) return send(401, { message: "unauthorized" });
  if (key === "bad") return send(403, { message: `forbidden for key ${key} secret ${secret}` });
  if (q.get("feed") !== "iex") return send(422, { message: "feed must be iex in this mock" });
  let seed;
  try {
    seed = JSON.parse(await readFile(join(root, scenario, "_alpaca.json"), "utf8"));
  } catch {
    return send(404, { message: "no _alpaca.json for this scenario" });
  }
  const openMs = openOf(seed.day);
  const now = Math.min(NOW(), openMs + 6.5 * 3600e3);
  const syms = String(q.get("symbols") || "").split(",").filter((s) => seed.symbols[s]);
  if (path === "/v2/stocks/snapshots") {
    const out = {};
    for (const s of syms) {
      const t = Math.max(openMs, now - 7000);
      out[s] = { latestTrade: { t: new Date(t).toISOString(), x: "V", p: priceAt(seed, s, t, openMs), s: 100, c: ["@"], i: 1, z: "C" } };
    }
    return send(200, out);
  }
  if (path === "/v2/stocks/bars") {
    if (q.get("timeframe") !== "5Min") return send(422, { message: "timeframe" });
    const start = Date.parse(q.get("start") || "");
    if (!isFinite(start)) return send(422, { message: "start" });
    const rows = [];
    for (const s of syms.sort()) {
      for (let t = Math.max(start, openMs); t + 5 * 60e3 <= now; t += 5 * 60e3) {
        const c = priceAt(seed, s, t + 5 * 60e3, openMs);
        rows.push([s, { t: new Date(t).toISOString(), o: c, h: c, l: c, c, v: 1000, n: 10, vw: c }]);
      }
    }
    const offset = Number(q.get("page_token") || 0);
    const page = rows.slice(offset, offset + 40);
    const bars = {};
    for (const [s, b] of page) (bars[s] = bars[s] || []).push(b);
    return send(200, { bars, next_page_token: offset + 40 < rows.length ? String(offset + 40) : null });
  }
  return send(404, { message: "not mocked" });
}

createServer(async (req, res) => {
  const url = new URL(req.url, "http://x");
  const m = /^\/alpaca\/([a-z0-9-]+)(\/v2\/.*)$/.exec(url.pathname);
  if (m) return alpaca(req, res, m[1], m[2], url.searchParams);
  if (url.pathname === "/__log") {
    res.writeHead(200, { "Content-Type": "application/json" });
    return res.end(JSON.stringify(log));
  }
  const path = normalize(decodeURIComponent(url.pathname)).replace(/^(\.\.[/\\])+/, "");
  const headers = { "Access-Control-Allow-Origin": "*", "Cache-Control": "max-age=0" };
  try {
    if (path.includes("_alpaca")) throw new Error("dev only");
    const body = await readFile(join(root, path));
    res.writeHead(200, { ...headers, "Content-Type": "application/json; charset=utf-8" });
    res.end(body);
  } catch {
    res.writeHead(404, { ...headers, "Content-Type": "text/plain" });
    res.end("404: Not Found");
  }
}).listen(port, () => console.log(`mock data on http://localhost:${port}/${nowArg ? `, now ${nowArg}` : ""}`));
