import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";
import type { Failure } from "@ecommerce/web-core";
import { AddressForm } from "../src/components/account/address-form";
import type { AddressFormValues } from "../src/lib/addresses";
import type { AddressSaved } from "../src/server/addresses";
import { address } from "./support/addresses";

type Submit = (values: AddressFormValues) => Promise<AddressSaved | Failure>;

function setup(result: AddressSaved | Failure = { ok: true, address: address() }, withCancel = false) {
  const submit = jest.fn<ReturnType<Submit>, Parameters<Submit>>(() => Promise.resolve(result));
  const onSaved = jest.fn();
  const onCancel = jest.fn();
  const view = render(<AddressForm submit={submit} onSaved={onSaved} {...(withCancel ? { onCancel } : {})} />);
  return { submit, onSaved, onCancel, ...view, user: userEvent.setup() };
}

const failure = (status: number | null, fieldErrors: Record<string, string> = {}): Failure => ({ ok: false, status, title: "Problem", fieldErrors });

async function fillRequired(user: ReturnType<typeof userEvent.setup>) {
  await user.type(screen.getByLabelText("Full name"), "Ada Lovelace");
  await user.type(screen.getByLabelText("Address line 1"), "12 Analytical St");
  await user.type(screen.getByLabelText("City"), "London");
  await user.type(screen.getByLabelText("Postal code"), "N1 9GU");
  await user.type(screen.getByLabelText("Country"), "GB");
}

describe("AddressForm", () => {
  it("labels every field, marks the required ones and has no accessibility violations", async () => {
    const { container } = setup();

    for (const label of ["Full name", "Address line 1", "Address line 2", "City", "State or region", "Postal code", "Country", "Phone"]) {
      expect(screen.getByLabelText(label)).toBeInTheDocument();
    }
    expect(screen.getByLabelText("Full name")).toBeRequired();
    expect(screen.getByLabelText("Address line 2")).not.toBeRequired();
    expect(screen.getByLabelText("Country")).toHaveAccessibleDescription(/two-letter country code/);
    expect(screen.getByLabelText("Postal code")).toHaveAttribute("autocomplete", "postal-code");
    expect(await axe(container)).toHaveNoViolations();
  });

  it("focuses the first invalid field and ties each message to its field", async () => {
    const { submit, user } = setup();

    await user.type(screen.getByLabelText("City"), "London");
    await user.click(screen.getByRole("button", { name: "Save address" }));

    await waitFor(() => {
      expect(screen.getByLabelText("Full name")).toHaveFocus();
    });
    expect(screen.getByLabelText("Full name")).toBeInvalid();
    expect(screen.getByLabelText("Full name")).toHaveAccessibleDescription(/Enter the name/);
    expect(screen.getByLabelText("Postal code")).toBeInvalid();
    expect(submit).not.toHaveBeenCalled();
  });

  it("saves and hands the saved address on", async () => {
    const { submit, onSaved, user } = setup();

    await fillRequired(user);
    await user.click(screen.getByRole("button", { name: "Save address" }));

    await waitFor(() => {
      expect(onSaved).toHaveBeenCalledWith(address());
    });
    expect(submit).toHaveBeenCalledWith(expect.objectContaining({ recipient_name: "Ada Lovelace", country: "GB", line2: "", phone: "" }));
  });

  it("shows field errors from the server on the fields and focuses the first", async () => {
    const { user } = setup(failure(422, { postal_code: "Too long", city: "Bad city" }));

    await fillRequired(user);
    await user.click(screen.getByRole("button", { name: "Save address" }));

    await waitFor(() => {
      expect(screen.getByLabelText("City")).toHaveFocus();
    });
    expect(screen.getByLabelText("City")).toBeInvalid();
    expect(screen.getByLabelText("Postal code")).toHaveAccessibleDescription("Too long");
    expect(screen.getByRole("alert")).toHaveTextContent("highlighted fields");
  });

  it.each([
    [409, /10 saved addresses/],
    [503, /could not be saved right now/],
  ])("explains a %s and moves focus to the alert", async (status, expected) => {
    const { user } = setup(failure(status));

    await fillRequired(user);
    await user.click(screen.getByRole("button", { name: "Save address" }));

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(expected);
    await waitFor(() => {
      expect(alert).toHaveFocus();
    });
  });

  it("offers Cancel only when asked to", async () => {
    const first = setup();
    expect(screen.queryByRole("button", { name: "Cancel" })).not.toBeInTheDocument();
    first.unmount();

    const { onCancel, user } = setup(undefined, true);
    await user.click(screen.getByRole("button", { name: "Cancel" }));
    expect(onCancel).toHaveBeenCalledTimes(1);
  });
});
