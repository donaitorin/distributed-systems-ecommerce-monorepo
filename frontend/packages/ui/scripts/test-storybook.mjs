import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import { readFile } from "node:fs/promises";
import { createServer } from "node:http";
import { extname, join, normalize, resolve, sep } from "node:path";

const ROOT = resolve("storybook-static");
const PORT = Number(process.env.STORYBOOK_PORT ?? 6006);

const CONTENT_TYPES = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".mjs": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".svg": "image/svg+xml",
  ".png": "image/png",
  ".woff2": "font/woff2",
  ".map": "application/json",
};

if (!existsSync(ROOT)) {
  process.stderr.write("storybook-static not found: run 'pnpm build-storybook' first\n");
  process.exit(1);
}

const server = createServer(async (request, response) => {
  const pathname = decodeURIComponent(new URL(request.url ?? "/", "http://localhost").pathname);
  const relative = pathname.endsWith("/") ? `${pathname}index.html` : pathname;
  const file = normalize(join(ROOT, relative));
  if (file !== ROOT && !file.startsWith(ROOT + sep)) {
    response.writeHead(403).end();
    return;
  }
  try {
    const body = await readFile(file);
    response.writeHead(200, {
      "content-type": CONTENT_TYPES[extname(file)] ?? "application/octet-stream",
    });
    response.end(body);
  } catch {
    response.writeHead(404).end();
  }
});

server.listen(PORT, "127.0.0.1", () => {
  const runner = spawn(
    "pnpm",
    ["exec", "test-storybook", "--disable-telemetry", "--url", `http://127.0.0.1:${PORT}`, ...process.argv.slice(2)],
    { stdio: "inherit" },
  );
  runner.on("exit", (code) => {
    server.close();
    process.exit(code ?? 1);
  });
});
