"use client";

import { useState } from "react";
import { Button } from "@ecommerce/ui";
import type { Failure } from "@ecommerce/web-core";
import { MAX_ADDRESSES, type Address, type AddressFormValues } from "../../lib/addresses";
import { useFocusTarget } from "../../lib/use-focus-target";
import type { AddressSaved } from "../../server/addresses";
import { AddressForm } from "../account/address-form";
import { AddressText } from "../account/address-text";

export type AddressPickerProps = {
  addresses: Address[];
  selectedId: string | null;
  error?: string;
  disabled: boolean;
  onSelect: (addressId: string) => void;
  onAdded: (address: Address) => void;
  addAddress: (values: AddressFormValues) => Promise<AddressSaved | Failure>;
};

const ERROR_ID = "shipping-address-error";
const ADD_BUTTON_ID = "add-address-button";

export function AddressPicker({ addresses, selectedId, error, disabled, onSelect, onAdded, addAddress }: AddressPickerProps) {
  const [adding, setAdding] = useState(addresses.length === 0);
  const focus = useFocusTarget();
  const full = addresses.length >= MAX_ADDRESSES;

  return (
    <div className="flex flex-col gap-4">
      {addresses.length > 0 ? (
        <fieldset className="flex flex-col gap-3" aria-describedby={error ? ERROR_ID : undefined}>
          <legend className="sr-only">Choose a shipping address</legend>
          {addresses.map((address) => {
            const inputId = `address-${address.id}`;
            return (
              <label
                key={address.id}
                htmlFor={inputId}
                className="flex min-h-11 cursor-pointer items-start gap-3 rounded-lg border border-border bg-surface p-4 has-checked:border-2 has-checked:border-accent-strong"
              >
                <input
                  id={inputId}
                  type="radio"
                  name="shipping-address"
                  value={address.id}
                  checked={selectedId === address.id}
                  disabled={disabled}
                  className="mt-1 size-5 shrink-0"
                  onChange={() => {
                    onSelect(address.id);
                  }}
                />
                <AddressText address={address} />
              </label>
            );
          })}
        </fieldset>
      ) : null}
      {error ? (
        <p id={ERROR_ID} className="text-sm font-medium text-danger-strong">
          {error}
        </p>
      ) : null}
      {adding ? (
        <div className="flex flex-col gap-3">
          <h3 className="text-lg font-semibold">New shipping address</h3>
          <AddressForm
            submit={addAddress}
            {...(addresses.length > 0
              ? {
                  onCancel: () => {
                    setAdding(false);
                    focus(ADD_BUTTON_ID);
                  },
                }
              : {})}
            onSaved={(address) => {
              onAdded(address);
              setAdding(false);
              focus(`address-${address.id}`);
            }}
          />
        </div>
      ) : (
        <div className="flex flex-col items-start gap-2">
          <Button
            id={ADD_BUTTON_ID}
            variant="secondary"
            disabled={disabled || full}
            onClick={() => {
              setAdding(true);
            }}
          >
            Add a new address
          </Button>
          {full ? <p className="text-sm text-secondary">You have {MAX_ADDRESSES} saved addresses. Delete one from your account to add another.</p> : null}
        </div>
      )}
    </div>
  );
}
