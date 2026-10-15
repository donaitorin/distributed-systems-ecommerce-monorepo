import { readFile, writeFile, readdir } from "node:fs/promises";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import openapiTS, { astToString } from "openapi-typescript";

const ROOT = fileURLToPath(new URL("..", import.meta.url));
const SPECS = join(ROOT, "openapi");
const OUTPUT = join(ROOT, "src", "generated");

async function render(file) {
  const document = JSON.parse(await readFile(join(SPECS, file), "utf8"));
  return astToString(await openapiTS(document));
}

async function readIfPresent(path) {
  try {
    return await readFile(path, "utf8");
  } catch {
    return null;
  }
}

const check = process.argv.includes("--check");
const files = (await readdir(SPECS)).filter((name) => name.endsWith(".json")).sort();
const stale = [];

for (const file of files) {
  const target = join(OUTPUT, file.replace(/\.json$/, ".ts"));
  const contents = await render(file);
  if (check) {
    if ((await readIfPresent(target)) !== contents) {
      stale.push(target);
    }
  } else {
    await writeFile(target, contents, "utf8");
  }
}

if (stale.length > 0) {
  process.stderr.write(
    `Generated types are stale: run 'make openapi' and commit the result\n${stale.join("\n")}\n`,
  );
  process.exit(1);
}
