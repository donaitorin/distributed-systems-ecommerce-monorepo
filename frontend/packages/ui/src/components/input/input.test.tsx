import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";
import { Input } from "./input";

describe("Input", () => {
  it("has no accessibility violations in any state", async () => {
    const { container } = render(
      <>
        <Input label="Name" />
        <Input label="Email" hint="We never share it" />
        <Input label="SKU" error="SKU is required" />
        <Input label="Locked" disabled />
      </>,
    );

    expect(await axe(container)).toHaveNoViolations();
  });

  it("associates the label with the input", async () => {
    render(<Input label="Name" />);

    await userEvent.type(screen.getByLabelText("Name"), "Ada");

    expect(screen.getByLabelText("Name")).toHaveValue("Ada");
  });

  it("links the hint and the error with aria-describedby and marks the input invalid", () => {
    render(<Input label="Email" hint="Work address" error="Email is invalid" />);
    const input = screen.getByLabelText("Email");

    expect(input).toHaveAttribute("aria-invalid", "true");
    expect(input).toHaveAccessibleDescription("Work address Email is invalid");
  });

  it("omits aria-invalid and aria-describedby when there is no hint or error", () => {
    render(<Input label="Name" />);
    const input = screen.getByLabelText("Name");

    expect(input).not.toHaveAttribute("aria-invalid");
    expect(input).not.toHaveAttribute("aria-describedby");
  });

  it("uses the id it is given", () => {
    render(<Input label="Name" id="custom-id" />);

    expect(screen.getByLabelText("Name")).toHaveAttribute("id", "custom-id");
  });
});
