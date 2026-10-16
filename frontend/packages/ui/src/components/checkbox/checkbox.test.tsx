import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";
import { Checkbox } from "./checkbox";

describe("Checkbox", () => {
  it("has no accessibility violations", async () => {
    const { container } = render(
      <>
        <Checkbox label="In stock only" />
        <Checkbox label="Gift wrap" hint="Adds a small fee" defaultChecked />
        <Checkbox label="Disabled" disabled />
      </>,
    );

    expect(await axe(container)).toHaveNoViolations();
  });

  it("is named by its label and toggles with the label and the keyboard", async () => {
    const onChange = jest.fn();
    render(<Checkbox label="In stock only" onChange={onChange} />);
    const box = screen.getByRole("checkbox", { name: "In stock only" });

    await userEvent.click(screen.getByText("In stock only"));
    expect(box).toBeChecked();

    box.focus();
    await userEvent.keyboard(" ");
    expect(box).not.toBeChecked();
    expect(onChange).toHaveBeenCalledTimes(2);
  });

  it("describes the checkbox with its hint", () => {
    render(<Checkbox label="Gift wrap" hint="Adds a small fee" />);

    expect(screen.getByRole("checkbox")).toHaveAccessibleDescription("Adds a small fee");
  });
});
