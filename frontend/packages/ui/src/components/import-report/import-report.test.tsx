import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";
import { ImportReport, type ImportReportProps, type ReportProblem } from "./import-report";

const COUNTS = { rowsRead: 97, importable: 88, toCreate: 80, toUpdate: 5, toRestore: 2, unchanged: 1, errors: 4, warnings: 3 };

const PROBLEMS: ReportProblem[] = [
  { id: "1", severity: "error", row: 7, column: "price", value: "free", reason: "price must be a number" },
  { id: "2", severity: "warning", row: 2, column: null, value: null, reason: "superseded by row 36" },
  { id: "3", severity: "error", row: null, column: null, value: null, reason: "the file has no rows" },
];

function setup(props: Partial<ImportReportProps> = {}) {
  const onSeverityFilterChange = jest.fn();
  const onLoadMoreProblems = jest.fn();
  const view = render(
    <ImportReport
      counts={COUNTS}
      unknownCategories={[]}
      problems={PROBLEMS}
      severityFilter="all"
      onSeverityFilterChange={onSeverityFilterChange}
      hasMoreProblems={false}
      onLoadMoreProblems={onLoadMoreProblems}
      {...props}
    />,
  );
  return { ...view, onSeverityFilterChange, onLoadMoreProblems };
}

describe("ImportReport", () => {
  it("has no accessibility violations with every section shown", async () => {
    const { container } = setup({
      truncated: true,
      problemsDownloadHref: "/problems.csv",
      hasMoreProblems: true,
      unknownCategories: [{ value: "Electornics", rows: 2, suggestion: "Electronics" }],
      renderCategoryAction: () => <button type="button">Create category</button>,
    });

    expect(await axe(container)).toHaveNoViolations();
  });

  it("shows every count with its label", () => {
    setup();
    const summary = screen.getByRole("region", { name: "Summary" });

    expect(within(summary).getByText("97 rows read, 88 can be imported.")).toBeInTheDocument();
    const expected: [string, string][] = [
      ["To create", "80"],
      ["To update", "5"],
      ["To restore", "2"],
      ["Unchanged", "1"],
      ["Errors", "4"],
      ["Warnings", "3"],
    ];
    for (const [label, value] of expected) {
      expect(within(summary).getByText(label).nextElementSibling).toHaveTextContent(value);
    }
  });

  it("formats large counts and says when the problem list is capped", () => {
    setup({ counts: { ...COUNTS, rowsRead: 123456 }, truncated: true });

    expect(screen.getByText(/123,456 rows read/)).toBeInTheDocument();
    expect(screen.getByText(/more problems than the report lists/)).toBeInTheDocument();
  });

  it("omits the unknown categories section when there are none", () => {
    setup();

    expect(screen.queryByRole("heading", { name: "Unknown categories" })).not.toBeInTheDocument();
  });

  it("groups unknown categories with the row count, the suggestion and an action slot", () => {
    setup({
      unknownCategories: [
        { value: "Electornics", rows: 2, suggestion: "Electronics" },
        { value: "Gardening", rows: 1, suggestion: null },
      ],
      renderCategoryAction: (category) => <button type="button">Create {category.value}</button>,
    });
    const items = within(screen.getByRole("region", { name: "Unknown categories" })).getAllByRole("listitem");

    expect(items).toHaveLength(2);
    expect(items[0]).toHaveTextContent("Electornics");
    expect(items[0]).toHaveTextContent("2 rows. Closest existing category: Electronics");
    expect(within(items[0] as HTMLElement).getByRole("button", { name: "Create Electornics" })).toBeInTheDocument();
    expect(items[1]).toHaveTextContent("1 row");
    expect(items[1]).not.toHaveTextContent("Closest");
  });

  it("shows no action button without a slot", () => {
    setup({ unknownCategories: [{ value: "Gardening", rows: 1, suggestion: null }] });

    expect(within(screen.getByRole("region", { name: "Unknown categories" })).queryByRole("button")).not.toBeInTheDocument();
  });

  it("lists the problems with a text severity, in a table and as cards", () => {
    setup();
    const table = within(screen.getByRole("table", { name: "Problems found in the file" }));

    expect(table.getAllByRole("row")).toHaveLength(4);
    expect(table.getByText("price must be a number")).toBeInTheDocument();
    expect(table.getAllByText("Error")).toHaveLength(2);
    expect(table.getByText("Warning")).toBeInTheDocument();
    expect(table.getByText("File")).toBeInTheDocument();
    expect(within(screen.getByRole("list", { name: "Problems found in the file" })).getAllByRole("listitem")).toHaveLength(3);
  });

  it("offers the filter and reports the chosen severity", async () => {
    const { onSeverityFilterChange } = setup();

    await userEvent.click(screen.getByRole("combobox", { name: "Show" }));
    await userEvent.click(await screen.findByRole("option", { name: "Warnings only" }));

    expect(onSeverityFilterChange).toHaveBeenCalledWith("warning");
  });

  it("shows the empty message, a loading skeleton and an error", () => {
    const { unmount } = setup({ problems: [] });
    expect(within(screen.getByRole("table")).getByText("No problems to show.")).toBeInTheDocument();
    unmount();

    const loading = setup({ problems: [], loadingProblems: true });
    expect(screen.getByRole("status")).toHaveTextContent("Loading");
    loading.unmount();

    setup({ problems: [], problemsError: "Could not load the problems" });
    expect(within(screen.getByRole("table")).getByRole("alert")).toHaveTextContent("Could not load");
  });

  it("loads more problems only when there are more", async () => {
    const { onLoadMoreProblems, unmount } = setup({ hasMoreProblems: true });

    await userEvent.click(screen.getByRole("button", { name: "Show more problems" }));
    expect(onLoadMoreProblems).toHaveBeenCalledTimes(1);
    unmount();

    setup();
    expect(screen.queryByRole("button", { name: "Show more problems" })).not.toBeInTheDocument();
  });

  it("links the problems.csv download", () => {
    setup({ problemsDownloadHref: "/admin/api/imports/abc/problems.csv" });

    const link = screen.getByRole("link", { name: "Download problems.csv" });
    expect(link).toHaveAttribute("href", "/admin/api/imports/abc/problems.csv");
    expect(link).toHaveAttribute("download");
  });

  it("has no download link without an address", () => {
    setup();

    expect(screen.queryByRole("link", { name: "Download problems.csv" })).not.toBeInTheDocument();
  });
});
