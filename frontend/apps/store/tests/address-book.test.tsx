import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";
import { settled } from "@ecommerce/web-core/testing";
import { AddressBook, type AddressBookActions } from "../src/components/account/address-book";
import { MAX_ADDRESSES } from "../src/lib/addresses";
import { address, ADDRESS_ID, OTHER_ADDRESS_ID } from "./support/addresses";

function actions(overrides: Partial<AddressBookActions> = {}): jest.Mocked<AddressBookActions> {
  return {
    add: jest.fn().mockResolvedValue({ ok: true, address: address({ id: OTHER_ADDRESS_ID, recipient_name: "Grace Hopper", line1: "1 Compiler Way" }) }),
    remove: jest.fn().mockResolvedValue({ ok: true }),
    ...overrides,
  } as jest.Mocked<AddressBookActions>;
}

function setup(addresses = [address()], api = actions()) {
  const view = render(<AddressBook addresses={addresses} actions={api} />);
  return { api, user: userEvent.setup(), ...view };
}

describe("AddressBook", () => {
  it("lists the saved addresses with no accessibility violations", async () => {
    const { container } = setup([address(), address({ id: OTHER_ADDRESS_ID, recipient_name: "Grace Hopper" })]);

    expect(within(screen.getByRole("list", { name: "Saved addresses" })).getAllByRole("listitem")).toHaveLength(2);
    expect(screen.getByText("Grace Hopper")).toBeInTheDocument();
    expect(await axe(container)).toHaveNoViolations();
  });

  it("says when there are none", () => {
    setup([]);

    expect(screen.getByText("You have no saved addresses yet.")).toBeInTheDocument();
    expect(screen.queryByRole("list", { name: "Saved addresses" })).not.toBeInTheDocument();
  });

  it("adds an address, shows it, announces it and returns focus to the Add button", async () => {
    const { api, user } = setup();

    await user.click(screen.getByRole("button", { name: "Add an address" }));
    expect(screen.getByRole("heading", { level: 3, name: "New address" })).toBeInTheDocument();
    await user.type(screen.getByLabelText("Full name"), "Grace Hopper");
    await user.type(screen.getByLabelText("Address line 1"), "1 Compiler Way");
    await user.type(screen.getByLabelText("City"), "Arlington");
    await user.type(screen.getByLabelText("Postal code"), "22201");
    await user.type(screen.getByLabelText("Country"), "US");
    await user.click(screen.getByRole("button", { name: "Save address" }));

    expect(await screen.findByText("Grace Hopper")).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("Address added.");
    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Add an address" })).toHaveFocus();
    });
    expect(api.add).toHaveBeenCalledTimes(1);
  });

  it("closes the form on Cancel and returns focus to the Add button", async () => {
    const { user } = setup();

    await user.click(screen.getByRole("button", { name: "Add an address" }));
    await user.click(screen.getByRole("button", { name: "Cancel" }));

    expect(screen.queryByLabelText("Full name")).not.toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Add an address" })).toHaveFocus();
    });
  });

  it("asks before deleting and deletes only after confirmation", async () => {
    const { api, user } = setup();

    await user.click(screen.getByRole("button", { name: "Delete address of Ada Lovelace, 12 Analytical St" }));
    const dialog = await screen.findByRole("dialog", { name: "Delete this address?" });
    expect(dialog).toHaveTextContent("Ada Lovelace, 12 Analytical St, London");
    expect(api.remove).not.toHaveBeenCalled();

    await user.click(within(dialog).getByRole("button", { name: "Delete address" }));

    await waitFor(() => {
      expect(api.remove).toHaveBeenCalledWith(ADDRESS_ID);
    });
    expect(await screen.findByText("You have no saved addresses yet.")).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("Address deleted.");
    await settled();
  });

  it("keeps the address when the dialog is cancelled", async () => {
    const { api, user } = setup();

    await user.click(screen.getByRole("button", { name: /Delete address of Ada/ }));
    await user.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Cancel" }));

    expect(api.remove).not.toHaveBeenCalled();
    await waitFor(() => {
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    });
    expect(screen.getByText("Ada Lovelace")).toBeInTheDocument();
  });

  it("explains a failed deletion in the dialog and keeps the address", async () => {
    const { user } = setup([address()], actions({ remove: jest.fn().mockResolvedValue({ ok: false, status: 503, title: "Down", fieldErrors: {} }) }));

    await user.click(screen.getByRole("button", { name: /Delete address of Ada/ }));
    await user.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Delete address" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("could not be deleted");
    expect(screen.getAllByText("Ada Lovelace").length).toBeGreaterThan(0);
  });

  it("stops offering to add at the limit and says why", () => {
    const many = Array.from({ length: MAX_ADDRESSES }, (_value, index) => address({ id: `00000000-0000-4000-8000-${String(index).padStart(12, "0")}` }));
    setup(many);

    expect(screen.getByRole("button", { name: "Add an address" })).toBeDisabled();
    expect(screen.getByText(/10 saved addresses, the most we can keep/)).toBeInTheDocument();
  });
});
