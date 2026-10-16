import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";
import { FilterChips } from "./filter-chips";

const CHIPS = [
  { id: "category", label: "Category: Footwear" },
  { id: "in_stock", label: "In stock only" },
];

describe("FilterChips", () => {
  it("has no accessibility violations", async () => {
    const { container } = render(<FilterChips chips={CHIPS} onRemove={jest.fn()} onClearAll={jest.fn()} />);

    expect(await axe(container)).toHaveNoViolations();
  });

  it("renders nothing without chips", () => {
    const { container } = render(<FilterChips chips={[]} onRemove={jest.fn()} onClearAll={jest.fn()} />);

    expect(container).toBeEmptyDOMElement();
  });

  it("names each remove button after the filter it removes, keeping the visible text in the name", () => {
    render(<FilterChips chips={CHIPS} onRemove={jest.fn()} />);

    expect(screen.getByRole("button", { name: "Remove filter: Category: Footwear" })).toHaveTextContent(
      "Category: Footwear",
    );
    expect(screen.queryByRole("button", { name: "Clear all filters" })).not.toBeInTheDocument();
  });

  it("removes one chip or all of them from the keyboard", async () => {
    const onRemove = jest.fn();
    const onClearAll = jest.fn();
    render(<FilterChips chips={CHIPS} onRemove={onRemove} onClearAll={onClearAll} label="Search filters" />);

    expect(screen.getByRole("region", { name: "Search filters" })).toBeInTheDocument();
    await userEvent.tab();
    await userEvent.keyboard("{Enter}");
    await userEvent.click(screen.getByRole("button", { name: "Clear all filters" }));

    expect(onRemove).toHaveBeenCalledWith("category");
    expect(onClearAll).toHaveBeenCalledTimes(1);
  });
});
