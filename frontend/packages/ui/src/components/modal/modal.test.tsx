import { useState } from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";
import { Button } from "../button/button";
import { Modal } from "./modal";

function Harness({ description }: { description?: string }) {
  const [open, setOpen] = useState(false);
  return (
    <Modal
      open={open}
      onOpenChange={setOpen}
      trigger={<Button>Open modal</Button>}
      title="Delete product"
      description={description}
      footer={<Button variant="danger">Confirm</Button>}
    >
      <p>This cannot be undone.</p>
    </Modal>
  );
}

describe("Modal", () => {
  it("has no accessibility violations when open", async () => {
    render(<Harness description="Are you sure?" />);
    await userEvent.click(screen.getByRole("button", { name: "Open modal" }));

    expect(await axe(await screen.findByRole("dialog"))).toHaveNoViolations();
  });

  it("is closed until the trigger is pressed", async () => {
    render(<Harness />);

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Open modal" }));

    expect(await screen.findByRole("dialog", { name: "Delete product" })).toBeInTheDocument();
  });

  it("describes the dialog when a description is given", async () => {
    render(<Harness description="Are you sure?" />);
    await userEvent.click(screen.getByRole("button", { name: "Open modal" }));

    expect(await screen.findByRole("dialog")).toHaveAccessibleDescription("Are you sure?");
  });

  it("renders without a description", async () => {
    render(<Harness />);
    await userEvent.click(screen.getByRole("button", { name: "Open modal" }));

    expect(await screen.findByRole("dialog")).not.toHaveAttribute("aria-describedby");
  });

  it("moves focus into the dialog and returns it to the trigger on Escape", async () => {
    render(<Harness />);
    const trigger = screen.getByRole("button", { name: "Open modal" });
    await userEvent.click(trigger);
    const dialog = await screen.findByRole("dialog");

    expect(dialog).toContainElement(document.activeElement as HTMLElement);

    await userEvent.keyboard("{Escape}");

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(trigger).toHaveFocus();
  });

  it("closes with the close button", async () => {
    render(<Harness />);
    await userEvent.click(screen.getByRole("button", { name: "Open modal" }));

    await userEvent.click(await screen.findByRole("button", { name: "Close" }));

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("works as a controlled modal without a trigger", () => {
    render(<Modal open onOpenChange={jest.fn()} title="Controlled" />);

    expect(screen.getByRole("dialog", { name: "Controlled" })).toBeInTheDocument();
  });
});
