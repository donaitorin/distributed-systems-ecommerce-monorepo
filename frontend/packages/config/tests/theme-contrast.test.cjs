const { readFileSync } = require("node:fs");
const { join } = require("node:path");

const themeSource = readFileSync(join(__dirname, "..", "styles", "theme.css"), "utf8");

const colors = Object.fromEntries(
  [...themeSource.matchAll(/--color-([a-z-]+):\s*(#[0-9a-fA-F]{6});/g)].map(([, name, hex]) => [
    name,
    hex,
  ]),
);

function channel(value) {
  const scaled = value / 255;
  return scaled <= 0.03928 ? scaled / 12.92 : ((scaled + 0.055) / 1.055) ** 2.4;
}

function luminance(hex) {
  const [r, g, b] = [1, 3, 5].map((start) => channel(parseInt(hex.slice(start, start + 2), 16)));
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

function contrast(foreground, background) {
  const [lighter, darker] = [luminance(foreground), luminance(background)].sort((a, b) => b - a);
  return (lighter + 0.05) / (darker + 0.05);
}

const TEXT_MINIMUM = 4.5;
const CONTROL_MINIMUM = 3;

const textPairs = [
  ["foreground", "background"],
  ["foreground", "muted"],
  ["muted-foreground", "background"],
  ["muted-foreground", "muted"],
  ["primary", "background"],
  ["primary-foreground", "primary"],
  ["primary-foreground", "primary-hover"],
  ["secondary-foreground", "secondary"],
  ["secondary-foreground", "secondary-hover"],
  ["danger", "background"],
  ["danger-foreground", "danger"],
  ["danger-foreground", "danger-hover"],
  ["danger-soft-foreground", "danger-soft"],
  ["success-soft-foreground", "success-soft"],
  ["warning-soft-foreground", "warning-soft"],
  ["info-soft-foreground", "info-soft"],
];

const controlPairs = [
  ["control-border", "background"],
  ["control-border", "muted"],
  ["focus-ring", "background"],
  ["focus-ring", "muted"],
  ["primary", "background"],
  ["danger", "background"],
];

describe("theme colors", () => {
  it("defines every color used by the pairs", () => {
    const names = new Set([...textPairs, ...controlPairs].flat());

    expect([...names].filter((name) => !(name in colors))).toEqual([]);
  });

  it.each(textPairs)("text %s on %s meets 4.5:1", (foreground, background) => {
    expect(contrast(colors[foreground], colors[background])).toBeGreaterThanOrEqual(TEXT_MINIMUM);
  });

  it.each(controlPairs)("control %s against %s meets 3:1", (control, background) => {
    expect(contrast(colors[control], colors[background])).toBeGreaterThanOrEqual(CONTROL_MINIMUM);
  });

  it("computes the reference ratio for black on white", () => {
    expect(contrast("#000000", "#ffffff")).toBeCloseTo(21, 5);
  });

  it("detects a failing pair", () => {
    expect(contrast("#aaaaaa", "#ffffff")).toBeLessThan(TEXT_MINIMUM);
  });
});
