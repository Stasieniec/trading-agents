// Loads the dashboard in Chromium at desktop and phone widths, light and dark, and checks for
// console errors, CSP violations, dialogs, page-level horizontal scroll and unsafe markup.
//   node dev/browser-check.cjs <page-url> <screenshot-dir> [prefix] [route ...]
// Example: node dev/browser-check.cjs http://localhost:8787/ /tmp/shots dashboard "" agent/weird-links
const { chromium } = require("playwright");
const path = require("path");

const [url, outDir, prefix = "dashboard", ...routesArg] = process.argv.slice(2);
const routes = routesArg.length ? routesArg : ["", "agent/weird-links"];
const viewports = [{ name: "desktop", width: 1280, height: 900 }, { name: "phone", width: 390, height: 844 }];
const schemes = ["light", "dark"];

(async () => {
  const browser = await chromium.launch();
  const problems = [];
  for (const route of routes) {
    for (const vp of viewports) {
      for (const scheme of schemes) {
        const ctx = await browser.newContext({ viewport: { width: vp.width, height: vp.height }, colorScheme: scheme,
          deviceScaleFactor: vp.name === "phone" ? 2 : 1 });
        const page = await ctx.newPage();
        const tag = `${route || "overview"} ${vp.name} ${scheme}`;
        const log = [];
        page.on("console", (m) => { if (["error", "warning"].includes(m.type())) log.push(`console.${m.type()}: ${m.text()}`); });
        page.on("pageerror", (e) => log.push(`pageerror: ${e.message}`));
        page.on("dialog", async (d) => { log.push(`dialog: ${d.message()}`); await d.dismiss(); });
        await page.addInitScript(() => {
          window.__csp = [];
          document.addEventListener("securitypolicyviolation", (e) => window.__csp.push(`${e.violatedDirective} ${e.blockedURI}`));
        });
        await page.goto(url + (route ? `#${route}` : ""), { waitUntil: "networkidle" });
        await page.waitForSelector(".section, .notice, .empty", { timeout: 10000 });
        await page.waitForTimeout(300);
        if (route.startsWith("agent/")) {
          await page.evaluate(() => {
            const d = document.querySelector("tr.detail details");
            if (d) d.open = true;
            for (const n of document.querySelectorAll(".note-file")) n.open = true;
          });
        }
        const report = await page.evaluate(() => {
          const main = document.querySelector("main");
          const bad = [];
          for (const sel of ["script", "img", "iframe", "form", "input", "style", "object", "embed", "svg"]) {
            const n = main.querySelectorAll(sel).length;
            if (n) bad.push(`${n} <${sel}> in main`);
          }
          for (const a of document.querySelectorAll("a[href]")) {
            const h = a.getAttribute("href");
            if (!(h.startsWith("https://") || h.startsWith("#") || h.startsWith("/"))) bad.push(`link with href ${h}`);
          }
          for (const a of main.querySelectorAll(".prose a")) {
            if (a.getAttribute("rel") !== "nofollow noopener noreferrer ugc" || a.getAttribute("target") !== "_blank") bad.push(`prose link without rel/target: ${a.href}`);
          }
          for (const n of main.querySelectorAll("[style]")) {
            if (!n.closest(".uplot") && !n.classList.contains("swatch") && !n.classList.contains("meter-fill") && !n.classList.contains("meter-proj")) bad.push(`style attribute on ${n.tagName}.${n.className}`);
          }
          for (const n of main.querySelectorAll("*")) {
            for (const at of n.attributes) if (/^on/i.test(at.name)) bad.push(`${at.name} on ${n.tagName}`);
          }
          return {
            pwned: window.__pwned || null,
            csp: window.__csp,
            hscroll: document.documentElement.scrollWidth - document.documentElement.clientWidth,
            bad,
            textHasScript: main.textContent.includes("<script>"),
          };
        });
        if (report.pwned) log.push(`script ran: ${report.pwned}`);
        if (report.csp.length) log.push(...report.csp.map((c) => `CSP violation: ${c}`));
        if (report.hscroll > 0) log.push(`page scrolls horizontally by ${report.hscroll}px`);
        log.push(...report.bad);
        const file = path.join(outDir, `${prefix}-${(route || "overview").replace(/\//g, "-")}-${vp.name}-${scheme}.png`);
        await page.screenshot({ path: file, fullPage: true });
        console.log(`${log.length ? "PROBLEMS" : "ok      "} ${tag}  -> ${file}${route.startsWith("agent/weird-links") ? `  (hostile text shown as text: ${report.textHasScript})` : ""}`);
        for (const l of log) console.log("    " + l);
        problems.push(...log);
        await ctx.close();
      }
    }
  }
  await browser.close();
  process.exitCode = problems.length ? 1 : 0;
})();
