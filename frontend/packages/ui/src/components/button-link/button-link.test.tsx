import { render, screen } from "@testing-library/react";
import { axe } from "jest-axe";
import { ButtonLink } from "./button-link";

describe("ButtonLink", () => {
  it("has no accessibility violations", async () => {
    const { container } = render(
      <>
        <ButtonLink href="/products/new">New product</ButtonLink>
        <ButtonLink href="/products" variant="secondary">
          Back
        </ButtonLink>
        <ButtonLink href="/x" variant="danger">
          Danger
        </ButtonLink>
      </>,
    );

    expect(await axe(container)).toHaveNoViolations();
  });

  it("is a link that looks like a button", () => {
    render(<ButtonLink href="/products/new">New product</ButtonLink>);
    const link = screen.getByRole("link", { name: "New product" });

    expect(link).toHaveAttribute("href", "/products/new");
    expect(link).toHaveClass("min-h-11", "bg-accent-strong");
  });

  it("applies the variant and extra classes", () => {
    render(
      <ButtonLink href="/x" variant="secondary" className="w-full">
        Back
      </ButtonLink>,
    );

    expect(screen.getByRole("link", { name: "Back" })).toHaveClass("bg-surface", "w-full");
  });
});
