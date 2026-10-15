import { useState } from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";
import { Toast, ToastProvider, type ToastProps } from "./toast";

function Harness(props: Partial<ToastProps>) {
  const [open, setOpen] = useState(true);
  return (
    <ToastProvider>
      <Toast open={open} onOpenChange={setOpen} title="Product saved" {...props} />
    </ToastProvider>
  );
}

describe("Toast", () => {
  it.each(["success", "error", "info"] as const)(
    "has no accessibility violations for the %s variant",
    async (variant) => {
      render(<Harness variant={variant} description="Details" />);

      expect(await axe(document.body)).toHaveNoViolations();
    },
  );

  it("shows the title and the description", () => {
    render(<Harness description="Changes are live." />);

    expect(screen.getByText("Product saved")).toBeInTheDocument();
    expect(screen.getByText("Changes are live.")).toBeInTheDocument();
  });

  it("states the variant in text, not only in color", () => {
    render(<Harness variant="error" />);

    expect(screen.getByText("Error:")).toBeInTheDocument();
  });

  it.each([
    ["success", "Success:"],
    ["info", "Notice:"],
  ] as const)("labels the %s variant", (variant, label) => {
    render(<Harness variant={variant} />);

    expect(screen.getByText(label)).toBeInTheDocument();
  });

  it("can be dismissed", async () => {
    render(<Harness />);

    await userEvent.click(screen.getByRole("button", { name: "Dismiss" }));

    expect(screen.queryByText("Product saved")).not.toBeInTheDocument();
  });

  it("renders nothing when closed", () => {
    render(<Toast open={false} onOpenChange={jest.fn()} title="Hidden" />, {
      wrapper: ToastProvider,
    });

    expect(screen.queryByText("Hidden")).not.toBeInTheDocument();
  });

  it("exposes the notification region with its label", () => {
    render(<Harness />);

    expect(screen.getByRole("region", { name: /Notifications/ })).toBeInTheDocument();
  });
});
