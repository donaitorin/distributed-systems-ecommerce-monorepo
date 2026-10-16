import { render, screen, within } from "@testing-library/react";
import { axe } from "jest-axe";
import { Table, type TableColumn } from "./table";

type Row = { sku: string; name: string; price: string };

const COLUMNS: readonly TableColumn<Row>[] = [
  { key: "sku", header: "SKU", cell: (row) => row.sku },
  { key: "name", header: "Name", cell: (row) => row.name },
  { key: "price", header: "Price", cell: (row) => row.price, align: "right" },
];

const ROWS: readonly Row[] = [
  { sku: "RS-001", name: "Running shoes", price: "$59.00" },
  { sku: "TY-002", name: "Toy robot", price: "$19.50" },
];

function renderTable(props: Partial<Parameters<typeof Table<Row>>[0]> = {}) {
  return render(
    <Table
      caption="Products"
      columns={COLUMNS}
      rows={ROWS}
      getRowKey={(row) => row.sku}
      {...props}
    />,
  );
}

describe("Table", () => {
  it("has no accessibility violations in any state", async () => {
    const { container } = render(
      <>
        <Table caption="Filled" columns={COLUMNS} rows={ROWS} getRowKey={(row) => row.sku} />
        <Table caption="Loading" columns={COLUMNS} rows={[]} getRowKey={(row) => row.sku} loading />
        <Table caption="Empty" columns={COLUMNS} rows={[]} getRowKey={(row) => row.sku} />
        <Table
          caption="Failed"
          columns={COLUMNS}
          rows={[]}
          getRowKey={(row) => row.sku}
          error="Could not load products"
        />
      </>,
    );

    expect(await axe(container)).toHaveNoViolations();
  });

  it("renders a captioned table with column headers and rows", () => {
    renderTable();

    expect(screen.getByRole("table", { name: "Products" })).toBeInTheDocument();
    expect(screen.getAllByRole("columnheader").map((header) => header.textContent)).toEqual([
      "SKU",
      "Name",
      "Price",
    ]);
    expect(screen.getAllByRole("row")).toHaveLength(3);
    expect(screen.getByRole("cell", { name: "Running shoes" })).toBeInTheDocument();
  });

  it("shows skeleton rows and announces loading", () => {
    renderTable({ loading: true, skeletonRowCount: 3 });

    expect(screen.getByRole("table")).toHaveAttribute("aria-busy", "true");
    expect(screen.getAllByRole("row")).toHaveLength(4);
    expect(screen.getByRole("status")).toHaveTextContent("Loading");
    expect(screen.queryByText("Running shoes")).not.toBeInTheDocument();
  });

  it("shows the default empty message", () => {
    renderTable({ rows: [] });

    expect(screen.getByText("No results found.")).toBeInTheDocument();
  });

  it("shows a custom empty message", () => {
    renderTable({ rows: [], emptyMessage: "No products yet." });

    expect(screen.getByText("No products yet.")).toBeInTheDocument();
  });

  it("shows the error as an alert and no rows", () => {
    renderTable({ error: "Could not load products" });

    expect(screen.getByRole("alert")).toHaveTextContent("Could not load products");
    expect(screen.queryByText("Running shoes")).not.toBeInTheDocument();
  });

  it("is a keyboard focusable scroll region", () => {
    renderTable();

    expect(screen.getByRole("region", { name: "Products" })).toHaveAttribute("tabindex", "0");
  });

  it("aligns numeric columns to the right", () => {
    renderTable();
    const row = screen.getByRole("row", { name: /Running shoes/ });

    expect(within(row).getByRole("cell", { name: "$59.00" })).toHaveClass("text-right");
  });

  describe("with cards for narrow screens", () => {
    const renderCard = (row: Row) => <strong>{`${row.name} card`}</strong>;

    it("renders the table and a list of cards, and has no accessibility violations", async () => {
      const { container } = renderTable({ renderCard });

      expect(screen.getByRole("table", { name: "Products" })).toBeInTheDocument();
      const list = screen.getByRole("list", { name: "Products" });
      expect(within(list).getAllByRole("listitem")).toHaveLength(2);
      expect(within(list).getByText("Toy robot card")).toBeInTheDocument();
      expect(screen.getByRole("region", { name: "Products" })).toHaveClass("max-md:hidden");
      expect(list).toHaveClass("md:hidden");
      expect(await axe(container)).toHaveNoViolations();
    });

    it("does not render a list without renderCard", () => {
      renderTable();

      expect(screen.queryByRole("list")).not.toBeInTheDocument();
      expect(screen.getByRole("region", { name: "Products" })).not.toHaveClass("max-md:hidden");
    });

    it("shows skeleton cards while loading", () => {
      renderTable({ renderCard, loading: true, skeletonRowCount: 2 });

      expect(screen.getByRole("list", { hidden: true })).toBeInTheDocument();
      expect(screen.queryByText("Running shoes card")).not.toBeInTheDocument();
    });

    it("shows the empty message and the error in the card list", () => {
      const { rerender } = renderTable({ renderCard, rows: [], emptyMessage: "Nothing here." });
      const list = screen.getByRole("list", { name: "Products" });
      expect(within(list).getByText("Nothing here.")).toBeInTheDocument();
      expect(within(list).queryByRole("alert")).not.toBeInTheDocument();

      rerender(
        <Table
          caption="Products"
          columns={COLUMNS}
          rows={[]}
          getRowKey={(row) => row.sku}
          renderCard={renderCard}
          error="Could not load"
        />,
      );
      expect(within(screen.getByRole("list", { name: "Products" })).getByRole("alert")).toHaveTextContent(
        "Could not load",
      );
    });
  });
});
