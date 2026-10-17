"use client";

import { useState, useTransition } from "react";
import { Button, ConfirmDialog } from "@ecommerce/ui";
import type { Failure } from "@ecommerce/web-core";
import { MAX_ADDRESSES, type Address, type AddressFormValues } from "../../lib/addresses";
import { useFocusTarget } from "../../lib/use-focus-target";
import type { AddressRemoved, AddressSaved } from "../../server/addresses";
import { AddressForm } from "./address-form";
import { AddressText } from "./address-text";

const ADD_BUTTON_ID = "account-add-address";

export type AddressBookActions = {
  add: (values: AddressFormValues) => Promise<AddressSaved | Failure>;
  remove: (addressId: string) => Promise<AddressRemoved | Failure>;
};

export type AddressBookProps = {
  addresses: Address[];
  actions: AddressBookActions;
};

export function AddressBook({ addresses: initial, actions }: AddressBookProps) {
  const focus = useFocusTarget();
  const [addresses, setAddresses] = useState(initial);
  const [adding, setAdding] = useState(false);
  const [status, setStatus] = useState("");
  const [toDelete, setToDelete] = useState<Address>();
  const [deleteError, setDeleteError] = useState<string>();
  const [pending, startTransition] = useTransition();

  const full = addresses.length >= MAX_ADDRESSES;

  const confirmDelete = () => {
    if (!toDelete) {
      return;
    }
    const target = toDelete;
    setDeleteError(undefined);
    startTransition(async () => {
      const result = await actions.remove(target.id);
      if (!result.ok) {
        setDeleteError("The address could not be deleted right now. Try again in a moment.");
        return;
      }
      setAddresses((current) => current.filter((address) => address.id !== target.id));
      setToDelete(undefined);
      setStatus("Address deleted.");
      focus(ADD_BUTTON_ID);
    });
  };

  return (
    <div className="flex flex-col gap-4" aria-busy={pending || undefined}>
      <p role="status" className="min-h-5 text-sm font-medium text-success-strong">
        {status}
      </p>
      {addresses.length === 0 ? (
        <p className="text-base text-secondary">You have no saved addresses yet.</p>
      ) : (
        <ul aria-label="Saved addresses" className="grid gap-4 sm:grid-cols-2">
          {addresses.map((address) => (
            <li key={address.id} className="flex flex-col items-start justify-between gap-3 rounded-lg border border-border bg-surface p-4">
              <AddressText address={address} />
              <Button
                variant="secondary"
                disabled={pending}
                aria-label={`Delete address of ${address.recipient_name}, ${address.line1}`}
                onClick={() => {
                  setDeleteError(undefined);
                  setToDelete(address);
                }}
              >
                Delete
              </Button>
            </li>
          ))}
        </ul>
      )}
      {adding ? (
        <div className="flex flex-col gap-3">
          <h3 className="text-lg font-semibold">New address</h3>
          <AddressForm
            submit={actions.add}
            onCancel={() => {
              setAdding(false);
              focus(ADD_BUTTON_ID);
            }}
            onSaved={(address) => {
              setAddresses((current) => [...current, address]);
              setAdding(false);
              setStatus("Address added.");
              focus(ADD_BUTTON_ID);
            }}
          />
        </div>
      ) : (
        <div className="flex flex-col items-start gap-2">
          <Button
            id={ADD_BUTTON_ID}
            variant="secondary"
            disabled={full}
            onClick={() => {
              setStatus("");
              setAdding(true);
            }}
          >
            Add an address
          </Button>
          {full ? (
            <p className="text-sm text-secondary">
              You have {MAX_ADDRESSES} saved addresses, the most we can keep. Delete one to add another.
            </p>
          ) : null}
        </div>
      )}
      <ConfirmDialog
        open={toDelete !== undefined}
        onOpenChange={(open) => {
          if (!open) {
            setToDelete(undefined);
          }
        }}
        title="Delete this address?"
        description={toDelete ? `${toDelete.recipient_name}, ${toDelete.line1}, ${toDelete.city}` : ""}
        confirmLabel="Delete address"
        variant="danger"
        pending={pending}
        {...(deleteError ? { error: deleteError } : {})}
        onConfirm={confirmDelete}
      />
    </div>
  );
}
