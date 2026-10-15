import { setPostVisit, setPreVisit } from "@storybook/test-runner";
import { getViolations, injectAxe } from "axe-playwright";

const AXE_OPTIONS = {
  runOnly: {
    type: "tag",
    values: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"],
  },
};

function describeViolation(violation) {
  const targets = violation.nodes.map((node) => node.target.join(" ")).join(", ");
  return `${violation.id} (${violation.impact}): ${violation.help}\n  ${targets}`;
}

setPreVisit(async (page) => {
  await injectAxe(page);
});

setPostVisit(async (page) => {
  const violations = await getViolations(page, "body", AXE_OPTIONS);
  if (violations.length > 0) {
    throw new Error(`Accessibility violations:\n${violations.map(describeViolation).join("\n")}`);
  }
});
