import { setPostVisit, setPreVisit } from "@storybook/test-runner";
import { getViolations, injectAxe } from "axe-playwright";

const AXE_OPTIONS = {
  runOnly: {
    type: "tag",
    values: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"],
  },
};

const watched = new WeakSet();
const unexpected = new WeakMap();

function describeViolation(violation) {
  const targets = violation.nodes.map((node) => node.target.join(" ")).join(", ");
  return `${violation.id} (${violation.impact}): ${violation.help}\n  ${targets}`;
}

function watch(page) {
  if (watched.has(page)) {
    return;
  }
  watched.add(page);
  unexpected.set(page, []);
  const record = (message) => {
    process.stderr.write(`test-storybook: ${message}\n`);
    unexpected.get(page)?.push(message);
  };
  page.on("pageerror", (error) => {
    record(`uncaught error in the page: ${error.message}`);
  });
}

const MOBILE = { width: 375, height: 812 };
const DESKTOP = { width: 1280, height: 720 };

setPreVisit(async (page, context) => {
  await page.setViewportSize(context.name === "Mobile" ? MOBILE : DESKTOP);
  watch(page);
  unexpected.set(page, []);
  await injectAxe(page);
});

setPostVisit(async (page, context) => {
  const problems = unexpected.get(page) ?? [];
  if (problems.length > 0) {
    throw new Error(`${context.id}: ${problems.join("\n")}`);
  }
  const violations = await getViolations(page, "body", AXE_OPTIONS);
  if (violations.length > 0) {
    throw new Error(`Accessibility violations:\n${violations.map(describeViolation).join("\n")}`);
  }
});
