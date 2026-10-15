import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import { readFile } from "node:fs/promises";
import { createServer } from "node:http";
import { connect } from "node:net";
import { extname, join, normalize, resolve, sep } from "node:path";

const ROOT = resolve("storybook-static");
const PORT = Number(process.env.STORYBOOK_TEST_PORT ?? 6107);
const HOST = "127.0.0.1";
const PROBE_TIMEOUT_MS = 500;

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

function fail(message) {
  process.stderr.write(`test-storybook: ${message}\n`);
  process.exit(1);
}

function somethingListens(host) {
  return new Promise((done) => {
    const socket = connect({ port: PORT, host });
    const finish = (listening) => {
      socket.destroy();
      done(listening);
    };
    socket.setTimeout(PROBE_TIMEOUT_MS, () => finish(false));
    socket.once("connect", () => finish(true));
    socket.once("error", () => finish(false));
  });
}

if (process.argv.includes("--url")) {
  fail("--url is not accepted: this command always tests its own static build");
}
if (!existsSync(ROOT)) {
  fail("storybook-static not found: run 'pnpm build-storybook' first");
}
for (const host of [HOST, "::1"]) {
  if (await somethingListens(host)) {
    fail(
      `port ${PORT} is already in use on ${host}; stop that process or set STORYBOOK_TEST_PORT to a free port`,
    );
  }
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
      "cache-control": "no-store",
    });
    response.end(body);
  } catch {
    response.writeHead(404).end();
  }
});

server.once("error", (error) => {
  fail(`could not listen on ${HOST}:${PORT}: ${error.message}`);
});

server.listen(PORT, HOST, () => {
  const url = `http://${HOST}:${PORT}`;
  process.stdout.write(`test-storybook: serving storybook-static at ${url}\n`);
  const runner = spawn(
    "pnpm",
    ["exec", "test-storybook", "--disable-telemetry", "--url", url, ...process.argv.slice(2)],
    { stdio: "inherit" },
  );
  for (const signal of ["SIGINT", "SIGTERM"]) {
    process.on(signal, () => runner.kill(signal));
  }
  runner.on("exit", (code) => {
    server.close();
    process.exit(code ?? 1);
  });
});
