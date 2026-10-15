import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";
import { Select } from "./select";

const OPTIONS = [
  { value: "footwear", label: "Footwear" },
  { value: "toys", label: "Toys" },
  { value: "books", label: "Books", disabled: true },
];

describe("Select", () => {
  it("has no accessibility violations in any state", async () => {
    const { container } = render(
      <>
        <Select label="Category" options={OPTIONS} />
        <Select label="Chosen" options={OPTIONS} defaultValue="toys" hint="Pick one" />
        <Select label="Broken" options={OPTIONS} error="Category is required" />
        <Select label="Locked" options={OPTIONS} disabled />
      </>,
    );

    expect(await axe(container)).toHaveNoViolations();
  });

  it("shows the placeholder and the label", () => {
    render(<Select label="Category" options={OPTIONS} placeholder="Choose a category" />);

    expect(screen.getByRole("combobox", { name: "Category" })).toHaveTextContent(
      "Choose a category",
    );
  });

  it("opens with the keyboard and reports the chosen value", async () => {
    const onValueChange = jest.fn();
    render(<Select label="Category" options={OPTIONS} onValueChange={onValueChange} />);

    screen.getByRole("combobox", { name: "Category" }).focus();
    await userEvent.keyboard("{Enter}");
    await userEvent.click(await screen.findByRole("option", { name: "Toys" }));

    expect(onValueChange).toHaveBeenCalledWith("toys");
    expect(screen.getByRole("combobox", { name: "Category" })).toHaveTextContent("Toys");
  });

  it("does not offer disabled options for selection", async () => {
    render(<Select label="Category" options={OPTIONS} />);

    await userEvent.click(screen.getByRole("combobox", { name: "Category" }));

    expect(await screen.findByRole("option", { name: "Books" })).toHaveAttribute(
      "aria-disabled",
      "true",
    );
  });

  it("links hint and error and marks the trigger invalid", () => {
    render(<Select label="Category" options={OPTIONS} hint="Pick one" error="Required" />);
    const trigger = screen.getByRole("combobox", { name: "Category" });

    expect(trigger).toHaveAttribute("aria-invalid", "true");
    expect(trigger).toHaveAccessibleDescription("Pick one Required");
  });

  it("is not interactive when disabled", () => {
    render(<Select label="Category" options={OPTIONS} disabled />);

    expect(screen.getByRole("combobox", { name: "Category" })).toBeDisabled();
  });
});
