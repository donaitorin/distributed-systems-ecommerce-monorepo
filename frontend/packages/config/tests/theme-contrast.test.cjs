const { readFileSync } = require("node:fs");
const { join } = require("node:path");

const themeSource = readFileSync(join(__dirname, "..", "styles", "theme.css"), "utf8");

function parseColor(value) {
  const hex = /^#([0-9a-f]{6})$/i.exec(value);
  if (hex) {
    const digits = hex[1];
    return {
      rgb: [0, 2, 4].map((start) => parseInt(digits.slice(start, start + 2), 16)),
      alpha: 1,
    };
  }
  const functional = /^rgb\((\d+) (\d+) (\d+) \/ ([\d.]+)\)$/.exec(value);
  if (functional) {
    return { rgb: functional.slice(1, 4).map(Number), alpha: Number(functional[4]) };
  }
  throw new Error(`Unsupported color value: ${value}`);
}

const tokens = Object.fromEntries(
  [...themeSource.matchAll(/--color-([a-z0-9-]+):\s*([^;]+);/g)].map(([, name, value]) => [
    name,
    parseColor(value.trim()),
  ]),
);

function composite(foreground, background) {
  const alpha = foreground.alpha;
  return {
    alpha: 1,
    rgb: foreground.rgb.map((channel, index) => channel * alpha + background.rgb[index] * (1 - alpha)),
  };
}

function resolve(spec) {
  if (typeof spec === "string") {
    return tokens[spec];
  }
  return composite(tokens[spec.soft], resolve(spec.over));
}

function label(spec) {
  return typeof spec === "string" ? spec : `${spec.soft} over ${label(spec.over)}`;
}

function channel(value) {
  const scaled = value / 255;
  return scaled <= 0.03928 ? scaled / 12.92 : ((scaled + 0.055) / 1.055) ** 2.4;
}

function luminance({ rgb }) {
  const [r, g, b] = rgb.map(channel);
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

function contrast(foreground, background) {
  const [lighter, darker] = [luminance(foreground), luminance(background)].sort((a, b) => b - a);
  return (lighter + 0.05) / (darker + 0.05);
}

const TEXT_MINIMUM = 4.5;
const CONTROL_MINIMUM = 3;

const PAGE_SURFACES = ["background", "surface", "surface-2"];
const withSoft = (soft) => [
  ...PAGE_SURFACES,
  ...PAGE_SURFACES.map((over) => ({ soft, over })),
];

const textPairs = [
  ...["background", "surface", "surface-2"].map((surface) => ["primary", surface]),
  ...["accent-soft", "success-soft", "danger-soft", "warning-soft"].flatMap((soft) =>
    PAGE_SURFACES.map((over) => ["primary", { soft, over }]),
  ),
  ...PAGE_SURFACES.map((surface) => ["secondary", surface]),
  ...withSoft("accent-soft").map((surface) => ["accent-strong", surface]),
  ...withSoft("success-soft").map((surface) => ["success-strong", surface]),
  ...withSoft("danger-soft").map((surface) => ["danger-strong", surface]),
  ...withSoft("warning-soft").map((surface) => ["warning-strong", surface]),
  ["on-accent", "accent-strong"],
  ["on-accent", "accent-hover"],
  ["on-accent", "danger-strong"],
  ["on-accent", "danger-hover"],
];

const controlPairs = ["border-strong", "accent-strong", "danger-strong", "success-strong"].flatMap(
  (control) => PAGE_SURFACES.map((surface) => [control, surface]),
);

const BRAND_FILLS = {
  background: "#f4ede4",
  surface: "#ffffff",
  "surface-2": "#f6efe6",
  border: "#e7dccf",
  primary: "#2d2823",
  tertiary: "#b7ab9b",
  accent: "#be6a4e",
  "on-accent": "#ffffff",
  success: "#4f8a6b",
  danger: "#c0584f",
  warning: "#cc9a4d",
};

const BRAND_SOFTS = {
  "accent-soft": [190, 106, 78, 0.13],
  "success-soft": [79, 138, 107, 0.13],
  "danger-soft": [192, 88, 79, 0.12],
  "warning-soft": [204, 154, 77, 0.14],
  overlay: [45, 40, 35, 0.45],
};

const toHex = ({ rgb }) => `#${rgb.map((value) => value.toString(16).padStart(2, "0")).join("")}`;

describe("brand values", () => {
  it.each(Object.entries(BRAND_FILLS))("keeps the original fill %s", (name, hex) => {
    expect(toHex(tokens[name])).toBe(hex);
  });

  it.each(Object.entries(BRAND_SOFTS))("keeps the original translucent color %s", (name, values) => {
    expect([...tokens[name].rgb, tokens[name].alpha]).toEqual(values);
  });

  it("never uses pure black or pure white for the page background", () => {
    expect(["#000000", "#ffffff"]).not.toContain(toHex(tokens.background));
  });

  it("keeps the modal overlay translucent and not pure black", () => {
    expect(tokens.overlay.rgb).not.toEqual([0, 0, 0]);
    expect(tokens.overlay.alpha).toBeCloseTo(0.45, 2);
  });
});

describe("theme colors", () => {
  it("defines every token used by the pairs", () => {
    const names = [...textPairs, ...controlPairs]
      .flat()
      .flatMap((spec) => (typeof spec === "string" ? [spec] : [spec.soft, spec.over]));

    expect([...new Set(names)].filter((name) => !(name in tokens))).toEqual([]);
  });

  it.each(textPairs.map(([foreground, background]) => [foreground, label(background), background]))(
    "text %s on %s meets 4.5:1",
    (foreground, _description, background) => {
      expect(contrast(tokens[foreground], resolve(background))).toBeGreaterThanOrEqual(TEXT_MINIMUM);
    },
  );

  it.each(controlPairs.map(([control, surface]) => [control, label(surface), surface]))(
    "control %s against %s meets 3:1",
    (control, _description, surface) => {
      expect(contrast(tokens[control], resolve(surface))).toBeGreaterThanOrEqual(CONTROL_MINIMUM);
    },
  );

  it("composites translucent colors before measuring", () => {
    const flat = resolve({ soft: "danger-soft", over: "surface" });

    expect(flat.alpha).toBe(1);
    expect(flat.rgb).not.toEqual(tokens["danger-soft"].rgb);
  });

  it("computes the reference ratio for black on white", () => {
    expect(contrast(parseColor("#000000"), parseColor("#ffffff"))).toBeCloseTo(21, 5);
  });

  it("detects a failing pair", () => {
    expect(contrast(tokens.accent, tokens["on-accent"])).toBeLessThan(TEXT_MINIMUM);
    expect(contrast(tokens.warning, tokens.surface)).toBeLessThan(TEXT_MINIMUM);
  });

  it("keeps the strong tokens in the hue of their brand fill", () => {
    const hue = ({ rgb: [r, g, b] }) => {
      const max = Math.max(r, g, b);
      const delta = max - Math.min(r, g, b);
      const segment = max === r ? ((g - b) / delta) % 6 : max === g ? (b - r) / delta + 2 : (r - g) / delta + 4;
      return (segment * 60 + 360) % 360;
    };

    for (const name of ["accent", "success", "danger", "warning"]) {
      expect(Math.abs(hue(tokens[`${name}-strong`]) - hue(tokens[name]))).toBeLessThan(3);
    }
  });
});
