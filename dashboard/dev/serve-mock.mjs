// Serves dev/mock/ with CORS headers, standing in for raw.githubusercontent.com.
//   node dev/serve-mock.mjs [port]      then use DATA_BASE=http://localhost:<port>/full/
import { createServer } from "node:http";
import { readFile } from "node:fs/promises";
import { join, normalize, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "mock");
const port = Number(process.argv[2] || 8790);
createServer(async (req, res) => {
  const path = normalize(decodeURIComponent(new URL(req.url, "http://x").pathname)).replace(/^(\.\.[/\\])+/, "");
  const headers = { "Access-Control-Allow-Origin": "*", "Cache-Control": "max-age=0" };
  try {
    const body = await readFile(join(root, path));
    res.writeHead(200, { ...headers, "Content-Type": "application/json; charset=utf-8" });
    res.end(body);
  } catch {
    res.writeHead(404, { ...headers, "Content-Type": "text/plain" });
    res.end("404: Not Found");
  }
}).listen(port, () => console.log(`mock data on http://localhost:${port}/`));
