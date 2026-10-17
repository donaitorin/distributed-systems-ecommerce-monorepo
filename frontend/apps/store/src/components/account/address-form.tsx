"use client";

import { useEffect, useRef, useState } from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { Button, Input } from "@ecommerce/ui";
import type { Failure } from "@ecommerce/web-core";
import {
  ADDRESS_FIELDS,
  addressFailureMessage,
  addressFormSchema,
  COUNTRY_MESSAGE,
  EMPTY_ADDRESS,
  type Address,
  type AddressFormValues,
} from "../../lib/addresses";
import type { AddressSaved } from "../../server/addresses";

export type AddressFormProps = {
  submit: (values: AddressFormValues) => Promise<AddressSaved | Failure>;
  onSaved: (address: Address) => void;
  onCancel?: () => void;
};

export function AddressForm({ submit, onSaved, onCancel }: AddressFormProps) {
  const alertRef = useRef<HTMLParagraphElement>(null);
  const [formError, setFormError] = useState<{ message: string; focus: boolean }>();
  const {
    register,
    handleSubmit,
    setError,
    setFocus,
    formState: { errors, isSubmitting },
  } = useForm<AddressFormValues>({ resolver: zodResolver(addressFormSchema), defaultValues: EMPTY_ADDRESS });

  useEffect(() => {
    if (formError?.focus) {
      alertRef.current?.focus();
    }
  }, [formError]);

  const save = async (values: AddressFormValues) => {
    setFormError(undefined);
    const result = await submit(values);
    if (result.ok) {
      onSaved(result.address);
      return;
    }
    const firstInvalid = ADDRESS_FIELDS.find((field) => result.fieldErrors[field] !== undefined);
    for (const field of ADDRESS_FIELDS) {
      const message = result.fieldErrors[field];
      if (message !== undefined) {
        setError(field, { type: "server", message });
      }
    }
    setFormError({ message: addressFailureMessage(result.status), focus: !firstInvalid });
    if (firstInvalid) {
      setFocus(firstInvalid);
    }
  };

  return (
    <form
      onSubmit={(event) => {
        void handleSubmit(save)(event);
      }}
      noValidate
      aria-busy={isSubmitting || undefined}
      className="flex max-w-md flex-col gap-4"
    >
      {formError ? (
        <p
          ref={alertRef}
          role="alert"
          tabIndex={-1}
          className="rounded-md border-2 border-danger-strong p-3 text-sm font-medium text-danger-strong"
        >
          {formError.message}
        </p>
      ) : null}
      <Input
        label="Full name"
        autoComplete="name"
        error={errors.recipient_name?.message}
        required
        {...register("recipient_name")}
      />
      <Input
        label="Address line 1"
        autoComplete="address-line1"
        error={errors.line1?.message}
        required
        {...register("line1")}
      />
      <Input
        label="Address line 2"
        autoComplete="address-line2"
        hint="Optional. Apartment, floor or building."
        error={errors.line2?.message}
        {...register("line2")}
      />
      <Input label="City" autoComplete="address-level2" error={errors.city?.message} required {...register("city")} />
      <Input
        label="State or region"
        autoComplete="address-level1"
        hint="Optional."
        error={errors.region?.message}
        {...register("region")}
      />
      <Input
        label="Postal code"
        autoComplete="postal-code"
        error={errors.postal_code?.message}
        required
        {...register("postal_code")}
      />
      <Input
        label="Country"
        autoComplete="country"
        hint={COUNTRY_MESSAGE}
        maxLength={2}
        error={errors.country?.message}
        required
        {...register("country")}
      />
      <Input
        label="Phone"
        type="tel"
        autoComplete="tel"
        hint="Optional. Include the country code, like +34 600 123 456."
        error={errors.phone?.message}
        {...register("phone")}
      />
      <div className="flex flex-wrap items-center gap-3">
        <Button type="submit" loading={isSubmitting}>
          Save address
        </Button>
        {onCancel ? (
          <Button variant="secondary" disabled={isSubmitting} onClick={onCancel}>
            Cancel
          </Button>
        ) : null}
      </div>
    </form>
  );
}
