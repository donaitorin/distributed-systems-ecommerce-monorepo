import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";
import { Textarea } from "./textarea";

describe("Textarea", () => {
  it("has no accessibility violations in any state", async () => {
    const { container } = render(
      <>
        <Textarea label="Description" />
        <Textarea label="Notes" hint="Shown to customers" />
        <Textarea label="Summary" error="Summary is too long" />
        <Textarea label="Locked" disabled />
      </>,
    );

    expect(await axe(container)).toHaveNoViolations();
  });

  it("associates the label with the textarea", async () => {
    render(<Textarea label="Description" />);

    await userEvent.type(screen.getByLabelText("Description"), "Soft and light");

    expect(screen.getByLabelText("Description")).toHaveValue("Soft and light");
  });

  it("links the hint and the error with aria-describedby and marks the field invalid", () => {
    render(<Textarea label="Description" hint="Plain text" error="Too long" />);
    const field = screen.getByLabelText("Description");

    expect(field).toHaveAttribute("aria-invalid", "true");
    expect(field).toHaveAccessibleDescription("Plain text Too long");
  });

  it("omits aria attributes without hint or error and honours rows and id", () => {
    render(<Textarea label="Description" rows={8} id="custom" />);
    const field = screen.getByLabelText("Description");

    expect(field).not.toHaveAttribute("aria-invalid");
    expect(field).not.toHaveAttribute("aria-describedby");
    expect(field).toHaveAttribute("rows", "8");
    expect(field).toHaveAttribute("id", "custom");
  });
});
