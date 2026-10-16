import { render, screen } from "@testing-library/react";
import { axe } from "jest-axe";
import { EmptyState } from "./empty-state";

describe("EmptyState", () => {
  it("has no accessibility violations", async () => {
    const { container } = render(
      <main>
        <EmptyState title="No products found" description="Try fewer filters." action={<button type="button">Clear</button>} />
      </main>,
    );

    expect(await axe(container)).toHaveNoViolations();
  });

  it("shows the title as a heading of the requested level, the description and the action", () => {
    render(<EmptyState title="Nothing here" description="Try again" action={<button type="button">Retry</button>} headingLevel={3} />);

    expect(screen.getByRole("heading", { level: 3, name: "Nothing here" })).toBeInTheDocument();
    expect(screen.getByText("Try again")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
  });

  it("works with only a title", () => {
    render(<EmptyState title="Nothing here" />);

    expect(screen.getByRole("heading", { level: 2 })).toBeInTheDocument();
  });
});
