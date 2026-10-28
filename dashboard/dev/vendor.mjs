// Copies the browser builds of the pinned libraries from node_modules into vendor/.
// Run after `npm ci`:  node dev/vendor.mjs
// Source map comments are stripped, since the maps are not served.
import { readFileSync, writeFileSync, mkdirSync, copyFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const pkg = JSON.parse(readFileSync(join(root, "package.json"), "utf8"));
const files = [
  ["uplot", "dist/uPlot.iife.min.js", "uPlot.iife.min.js"],
  ["uplot", "dist/uPlot.min.css", "uPlot.min.css"],
  ["uplot", "LICENSE", "LICENSE-uplot.txt"],
  ["marked", "lib/marked.umd.js", "marked.umd.js"],
  ["marked", "LICENSE", "LICENSE-marked.txt"],
  ["dompurify", "dist/purify.min.js", "purify.min.js"],
  ["dompurify", "LICENSE", "LICENSE-dompurify.txt"],
  ["@fontsource/jetbrains-mono", "files/jetbrains-mono-latin-400-normal.woff2", "jetbrains-mono-400.woff2"],
  ["@fontsource/jetbrains-mono", "files/jetbrains-mono-latin-500-normal.woff2", "jetbrains-mono-500.woff2"],
  ["@fontsource/jetbrains-mono", "files/jetbrains-mono-latin-700-normal.woff2", "jetbrains-mono-700.woff2"],
  ["@fontsource/jetbrains-mono", "LICENSE", "LICENSE-jetbrains-mono.txt"],
  ["@fontsource/inter-tight", "files/inter-tight-latin-800-normal.woff2", "inter-tight-800.woff2"],
  ["@fontsource/inter-tight", "LICENSE", "LICENSE-inter-tight.txt"],
];
mkdirSync(join(root, "vendor"), { recursive: true });
for (const [name, from, to] of files) {
  const want = pkg.dependencies[name];
  const got = JSON.parse(readFileSync(join(root, "node_modules", name, "package.json"), "utf8")).version;
  if (got !== want) throw new Error(`${name}: package.json pins ${want}, node_modules has ${got}`);
  if (to.endsWith(".woff2")) {
    copyFileSync(join(root, "node_modules", name, from), join(root, "vendor", to));
    console.log(`vendor/${to}  ${name}@${got}`);
    continue;
  }
  const text = readFileSync(join(root, "node_modules", name, from), "utf8")
    .replace(/\n?\/[/*][#@] sourceMappingURL=\S+(\s*\*\/)?\s*$/, "\n");
  writeFileSync(join(root, "vendor", to), text);
  console.log(`vendor/${to}  ${name}@${got}`);
}
