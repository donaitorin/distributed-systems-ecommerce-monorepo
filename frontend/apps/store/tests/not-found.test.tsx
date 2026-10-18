import { render, screen } from "@testing-library/react";
import { axe } from "jest-axe";
import NotFound, { metadata } from "../src/app/not-found";

describe("not found page", () => {
  it("explains the problem with one heading and a way back, and has no accessibility violations", async () => {
    const { container } = render(<NotFound />);

    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
    expect(screen.getByRole("heading", { level: 1, name: "Page not found" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Back to products" })).toHaveAttribute("href", "/products");
    expect(metadata.title).toBe("Page not found");
    expect(await axe(container)).toHaveNoViolations();
  });

  it("renders no style element and no inline script, which the nonce policy would block", () => {
    const { container } = render(<NotFound />);

    expect(container.querySelector("style")).toBeNull();
    expect(container.querySelector("script")).toBeNull();
  });
});
