import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import { useState } from "react";
import { expect, within } from "storybook/test";
import { Button } from "../button/button";
import { ImportReport, type ImportReportProps, type ReportProblem, type SeverityFilter } from "./import-report";

const PROBLEMS: ReportProblem[] = [
  { id: "1", severity: "error", row: 7, column: "price", value: "free", reason: "price must be a number" },
  { id: "2", severity: "error", row: 16, column: "stock", value: "-3", reason: "stock must not be negative" },
  { id: "3", severity: "warning", row: 2, column: "sku", value: "RS-001", reason: "superseded by row 36" },
  { id: "4", severity: "warning", row: 4, column: "price", value: "$29.99", reason: "price normalized from $29.99" },
];

function Stateful(props: Omit<ImportReportProps, "severityFilter" | "onSeverityFilterChange">) {
  const [filter, setFilter] = useState<SeverityFilter>("all");
  const visible = props.problems.filter((problem) => filter === "all" || problem.severity === filter);
  return <ImportReport {...props} problems={visible} severityFilter={filter} onSeverityFilterChange={setFilter} />;
}

const meta = {
  title: "Components/ImportReport",
  component: Stateful,
  parameters: { layout: "padded" },
  args: {
    counts: { rowsRead: 97, importable: 88, toCreate: 88, toUpdate: 0, toRestore: 0, unchanged: 0, errors: 4, warnings: 3 },
    unknownCategories: [],
    problems: PROBLEMS,
    hasMoreProblems: false,
    onLoadMoreProblems: () => undefined,
    problemsDownloadHref: "/admin/api/imports/example/problems.csv",
  },
} satisfies Meta<typeof Stateful>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  play: async ({ canvasElement }) => {
    await expect(within(canvasElement).getByRole("table", { name: "Problems found in the file" })).toBeVisible();
  },
};

export const UnknownCategories: Story = {
  args: {
    unknownCategories: [
      { value: "Electornics", rows: 2, suggestion: "Electronics" },
      { value: "Gardening", rows: 5, suggestion: null },
    ],
    renderCategoryAction: (category) => <Button variant="secondary">Create category {category.value}</Button>,
  },
};

export const MoreProblems: Story = { args: { hasMoreProblems: true } };

export const LoadingProblems: Story = { args: { problems: [], loadingProblems: true } };

export const NoProblems: Story = { args: { problems: [], counts: { rowsRead: 10, importable: 10, toCreate: 10, toUpdate: 0, toRestore: 0, unchanged: 0, errors: 0, warnings: 0 } } };

export const ProblemsFailedToLoad: Story = { args: { problems: [], problemsError: "The problems could not be loaded. Try again." } };

export const Truncated: Story = { args: { truncated: true } };

export const Mobile: Story = {
  args: { unknownCategories: [{ value: "Gardening", rows: 5, suggestion: "Garden" }], renderCategoryAction: () => <Button variant="secondary">Create category</Button> },
  globals: { viewport: { value: "mobile", isRotated: false } },
};
