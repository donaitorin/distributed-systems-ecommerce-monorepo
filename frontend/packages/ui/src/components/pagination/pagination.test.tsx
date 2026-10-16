import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";
import { Pagination } from "./pagination";

function renderPagination(props: Partial<Parameters<typeof Pagination>[0]> = {}) {
  const handlers = { onPrevious: jest.fn(), onNext: jest.fn() };
  render(<Pagination hasPrevious hasNext {...handlers} {...props} />);
  return handlers;
}

describe("Pagination", () => {
  it("has no accessibility violations", async () => {
    const { container } = render(
      <>
        <Pagination hasPrevious hasNext onPrevious={jest.fn()} onNext={jest.fn()} total={120} />
        <Pagination
          hasPrevious={false}
          hasNext={false}
          onPrevious={jest.fn()}
          onNext={jest.fn()}
          label="Order pages"
        />
      </>,
    );

    expect(await axe(container)).toHaveNoViolations();
  });

  it("is a labelled navigation landmark", () => {
    renderPagination({ label: "Product pages" });

    expect(screen.getByRole("navigation", { name: "Product pages" })).toBeInTheDocument();
  });

  it("calls the handlers", async () => {
    const { onPrevious, onNext } = renderPagination();

    await userEvent.click(screen.getByRole("button", { name: "Previous" }));
    await userEvent.click(screen.getByRole("button", { name: "Next" }));

    expect(onPrevious).toHaveBeenCalledTimes(1);
    expect(onNext).toHaveBeenCalledTimes(1);
  });

  it("disables the buttons that have nowhere to go", () => {
    renderPagination({ hasPrevious: false, hasNext: false });

    expect(screen.getByRole("button", { name: "Previous" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Next" })).toBeDisabled();
  });

  it("disables both buttons while loading", () => {
    renderPagination({ loading: true });

    expect(screen.getByRole("button", { name: "Previous" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Next" })).toBeDisabled();
  });

  it("announces an exact total", () => {
    renderPagination({ total: 1234, totalExact: true });

    expect(screen.getByRole("status")).toHaveTextContent("1,234 results");
  });

  it("announces an approximate total", () => {
    renderPagination({ total: 200500, totalExact: false });

    expect(screen.getByRole("status")).toHaveTextContent("About 200,500 results");
  });

  it("uses the singular for one result", () => {
    renderPagination({ total: 1 });

    expect(screen.getByRole("status")).toHaveTextContent("1 result");
  });

  it("keeps an empty live region when the total is unknown", () => {
    renderPagination();

    expect(screen.getByRole("status")).toBeEmptyDOMElement();
  });
});
