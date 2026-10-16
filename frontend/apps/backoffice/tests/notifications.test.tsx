import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";
import { NotificationsProvider, useNotify } from "../src/components/notifications";

function Trigger({ variant }: { variant?: "success" | "error" | "info" }) {
  const notify = useNotify();
  return (
    <button
      type="button"
      onClick={() => {
        notify({ title: "Saved", description: "All good", ...(variant ? { variant } : {}) });
      }}
    >
      Notify
    </button>
  );
}

describe("NotificationsProvider", () => {
  it("shows a toast with its description, and has no accessibility violations", async () => {
    const { baseElement } = render(
      <NotificationsProvider>
        <Trigger variant="success" />
      </NotificationsProvider>,
    );

    await userEvent.click(screen.getByRole("button", { name: "Notify" }));

    expect(await screen.findByText("All good")).toBeInTheDocument();
    expect(screen.getByText("Saved")).toBeInTheDocument();
    expect(await axe(baseElement)).toHaveNoViolations();
  });

  it("defaults to the info variant and stacks several toasts", async () => {
    render(
      <NotificationsProvider>
        <Trigger />
      </NotificationsProvider>,
    );

    await userEvent.click(screen.getByRole("button", { name: "Notify" }));
    await userEvent.click(screen.getByRole("button", { name: "Notify" }));

    expect(await screen.findAllByText("Saved")).toHaveLength(2);
    expect(screen.getAllByText(/Notice:/).length).toBeGreaterThan(0);
  });

  it("removes a toast when it is dismissed", async () => {
    render(
      <NotificationsProvider>
        <Trigger variant="error" />
      </NotificationsProvider>,
    );

    await userEvent.click(screen.getByRole("button", { name: "Notify" }));
    await userEvent.click(await screen.findByRole("button", { name: "Dismiss" }));

    await waitFor(() => {
      expect(screen.queryByText("All good")).not.toBeInTheDocument();
    });
  });

  it("does nothing outside the provider", async () => {
    render(<Trigger />);

    await act(async () => {
      await userEvent.click(screen.getByRole("button", { name: "Notify" }));
    });

    expect(screen.queryByText("Saved")).not.toBeInTheDocument();
  });
});
