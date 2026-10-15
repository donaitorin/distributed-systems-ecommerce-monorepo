const { readFileSync, readdirSync, existsSync } = require("node:fs");
const { join, relative } = require("node:path");

const FRONTEND = join(__dirname, "..", "..", "..");
const theme = readFileSync(join(__dirname, "..", "styles", "theme.css"), "utf8");

const TOKEN_NAMES = new Set(
  [...theme.matchAll(/--color-([a-z0-9-]+):/g)].map(([, name]) => name),
);

const REMOVED_NAMES = new Set([
  "foreground",
  "muted",
  "muted-foreground",
  "control-border",
  "primary-foreground",
  "secondary-foreground",
  "danger-foreground",
  "focus-ring",
  "info-soft",
  "info-soft-foreground",
  "success-soft-foreground",
  "warning-soft-foreground",
  "danger-soft-foreground",
  "primary-hover",
  "secondary-hover",
  "white",
  "black",
]);

const TEXT_TOKENS = new Set([
  "primary",
  "secondary",
  "tertiary",
  "on-accent",
  "accent-strong",
  "success-strong",
  "danger-strong",
  "warning-strong",
]);
const NOT_FILLS = new Set(["primary", "secondary", "tertiary", "on-accent"]);
const NOT_BOUNDARIES = new Set(["accent", "success", "danger", "warning", "tertiary"]);

const UTILITY = new RegExp(
  "(?<![\\w-])(?:[a-z0-9-]+:)*(bg|text|border|ring|outline|fill|stroke|divide|placeholder|decoration|caret|shadow)-([a-z0-9-]+)(?:/\\d+)?(?![\\w-])",
  "g",
);

function sourceFiles(directory) {
  if (!existsSync(directory)) {
    return [];
  }
  return readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const path = join(directory, entry.name);
    if (entry.isDirectory()) {
      return sourceFiles(path);
    }
    return /\.tsx?$/.test(entry.name) && !/\.test\.tsx?$/.test(entry.name) ? [path] : [];
  });
}

function scannedFiles() {
  const apps = existsSync(join(FRONTEND, "apps")) ? readdirSync(join(FRONTEND, "apps")) : [];
  return [
    ...sourceFiles(join(FRONTEND, "packages", "ui", "src")),
    ...apps.flatMap((app) => sourceFiles(join(FRONTEND, "apps", app, "src"))),
  ];
}

function violations(source) {
  const found = [];
  source.split("\n").forEach((line, index) => {
    const disabledContext = /disabled|cursor-not-allowed/.test(line);
    for (const [utility, prefix, name] of line.matchAll(UTILITY)) {
      if (REMOVED_NAMES.has(name)) {
        found.push(`${index + 1}: ${utility} uses a removed token`);
      } else if (prefix === "text" && (TOKEN_NAMES.has(name) || name === "transparent")) {
        if (!TEXT_TOKENS.has(name)) {
          found.push(`${index + 1}: ${utility} is not a text token`);
        } else if (name === "tertiary" && !disabledContext) {
          found.push(`${index + 1}: ${utility} is only for disabled text`);
        }
      } else if (prefix === "bg" && NOT_FILLS.has(name)) {
        found.push(`${index + 1}: ${utility} is a text token, not a fill`);
      } else if (["border", "ring", "outline"].includes(prefix) && NOT_BOUNDARIES.has(name)) {
        if (!(name === "tertiary" && disabledContext)) {
          found.push(`${index + 1}: ${utility} cannot be used for a control boundary`);
        }
      }
    }
  });
  return found;
}

describe("token usage in component sources", () => {
  const files = scannedFiles();

  it("scans the ui package", () => {
    expect(files.length).toBeGreaterThan(10);
  });

  it.each(files.map((file) => [relative(FRONTEND, file), file]))("%s uses only valid tokens", (_name, file) => {
    expect(violations(readFileSync(file, "utf8"))).toEqual([]);
  });
});

describe("token usage rules", () => {
  it.each([
    ["text-foreground", "removed token"],
    ["bg-muted", "removed token"],
    ["text-white", "removed token"],
    ["text-danger", "not a text token"],
    ["text-accent", "not a text token"],
    ["text-warning", "not a text token"],
    ["bg-primary", "text token"],
    ["border-danger", "control boundary"],
    ["border-accent", "control boundary"],
    ["hover:text-success", "not a text token"],
    ["text-tertiary", "only for disabled"],
  ])("rejects %s", (classes, reason) => {
    expect(violations(`className="${classes}"`).join()).toContain(reason);
  });

  it.each([
    "text-primary text-secondary text-on-accent",
    "text-danger-strong border-danger-strong bg-danger-soft",
    "bg-accent-strong hover:bg-accent-hover border-border-strong",
    "bg-surface bg-surface-2 bg-background bg-overlay",
    "text-sm text-xs text-center border-t border-collapse border-2 border-transparent",
    "disabled:text-tertiary",
    "cursor-not-allowed text-tertiary",
    "data-placeholder:text-secondary after:inset-0",
  ])("accepts %s", (classes) => {
    expect(violations(`className="${classes}"`)).toEqual([]);
  });
});
