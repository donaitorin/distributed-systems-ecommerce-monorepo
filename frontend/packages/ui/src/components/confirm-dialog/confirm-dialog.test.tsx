import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";
import { ConfirmDialog, type ConfirmDialogProps } from "./confirm-dialog";

function renderDialog(props: Partial<ConfirmDialogProps> = {}) {
  const onOpenChange = jest.fn();
  const onConfirm = jest.fn();
  const view = render(
    <ConfirmDialog
      open
      onOpenChange={onOpenChange}
      onConfirm={onConfirm}
      title="Delete product?"
      description="It will be hidden from the store."
      confirmLabel="Delete"
      {...props}
    />,
  );
  return { ...view, onOpenChange, onConfirm };
}

describe("ConfirmDialog", () => {
  it("has no accessibility violations", async () => {
    renderDialog({ error: "Could not delete" });

    expect(await axe(document.body)).toHaveNoViolations();
  });

  it("is a labelled dialog with the description", () => {
    renderDialog();

    expect(screen.getByRole("dialog", { name: "Delete product?" })).toHaveAccessibleDescription(
      "It will be hidden from the store.",
    );
  });

  it("confirms and cancels", async () => {
    const { onConfirm, onOpenChange } = renderDialog({ cancelLabel: "Keep it" });

    await userEvent.click(screen.getByRole("button", { name: "Delete" }));
    expect(onConfirm).toHaveBeenCalledTimes(1);

    await userEvent.click(screen.getByRole("button", { name: "Keep it" }));
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it("closes with Escape", async () => {
    const { onOpenChange } = renderDialog();

    await userEvent.keyboard("{Escape}");

    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it("cannot be dismissed while pending and shows the busy button", async () => {
    const { onOpenChange } = renderDialog({ pending: true });

    await userEvent.keyboard("{Escape}");

    expect(onOpenChange).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Delete" })).toHaveAttribute("aria-busy", "true");
    expect(screen.getByRole("button", { name: "Cancel" })).toBeDisabled();
  });

  it("shows the error as an alert and extra content", () => {
    renderDialog({ error: "Could not delete", children: <p>Extra</p> });

    expect(screen.getByRole("alert")).toHaveTextContent("Could not delete");
    expect(screen.getByText("Extra")).toBeInTheDocument();
  });

  it("renders nothing when closed", () => {
    renderDialog({ open: false });

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
});
