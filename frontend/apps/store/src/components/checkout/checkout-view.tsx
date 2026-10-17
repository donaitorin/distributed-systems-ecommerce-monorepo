"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { Button, ButtonLink, Input, ProductImage } from "@ecommerce/ui";
import type { Failure } from "@ecommerce/web-core";
import type { Address, AddressFormValues } from "../../lib/addresses";
import { describeFlag, money, pluralItems, type Cart } from "../../lib/cart";
import {
  attemptSignature,
  blockedLines,
  cardDigits,
  cartFingerprint,
  checkoutFormSchema,
  groupCardNumber,
  nextAttempt,
  placeOrderFailureMessage,
  type Attempt,
  type CheckoutFormValues,
  type PlaceOrderFailure,
  type PlaceOrderInput,
  type PlaceOrderResult,
} from "../../lib/checkout";
import { CART_PATH, CHECKOUT_PATH, productHref } from "../../lib/paths";
import type { AddressSaved } from "../../server/addresses";
import { AddressPicker } from "./address-picker";
import { PaymentNote } from "./payment-note";

export type CheckoutActions = {
  placeOrder: (input: PlaceOrderInput) => Promise<PlaceOrderResult>;
  newAttemptKey: () => Promise<string>;
  addAddress: (values: AddressFormValues) => Promise<AddressSaved | Failure>;
};

export type CheckoutViewProps = {
  cart: Cart;
  addresses: Address[];
  attemptKey: string;
  actions: CheckoutActions;
  onPlaced: (orderId: string) => void;
};

const IMAGE_SIZES = "64px";
const CARD_INPUT_MAX_LENGTH = 23;
const ADDRESS_REQUIRED = "Choose a shipping address, or add a new one, to continue.";

function failureLinks(kind: PlaceOrderFailure["kind"]) {
  if (kind === "cart_flagged" || kind === "empty_cart") {
    return { href: CART_PATH, label: "Back to your cart" };
  }
  if (kind === "cart_changed") {
    return { href: CHECKOUT_PATH, label: "Reload checkout" };
  }
  return null;
}

export function CheckoutView({ cart, addresses: initialAddresses, attemptKey, actions, onPlaced }: CheckoutViewProps) {
  const addressSection = useRef<HTMLElement>(null);
  const alertRef = useRef<HTMLParagraphElement>(null);
  const attempt = useRef<Attempt>({ key: attemptKey, signature: null });
  const inFlight = useRef(false);
  const [addresses, setAddresses] = useState(initialAddresses);
  const [selectedId, setSelectedId] = useState<string | null>(initialAddresses.length === 1 ? (initialAddresses[0]?.id ?? null) : null);
  const [addressError, setAddressError] = useState<string>();
  const [failure, setFailure] = useState<PlaceOrderFailure>();
  const [placed, setPlaced] = useState(false);
  const {
    register,
    handleSubmit,
    resetField,
    setError,
    setFocus,
    formState: { errors, isSubmitting },
  } = useForm<CheckoutFormValues>({
    resolver: zodResolver(checkoutFormSchema),
    defaultValues: { card_number: "" },
  });

  const blocked = blockedLines(cart);
  const fingerprint = cartFingerprint(cart);
  const busy = isSubmitting || placed;
  const cardRegistration = register("card_number");

  const showFailure = (result: PlaceOrderFailure) => {
    setFailure(result);
    if (result.kind === "invalid_card") {
      setError("card_number", { type: "server", message: placeOrderFailureMessage(result) });
      setFocus("card_number");
    }
  };

  useEffect(() => {
    if (failure && failure.kind !== "invalid_card") {
      alertRef.current?.focus();
    }
  }, [failure]);

  const place = async (values: CheckoutFormValues) => {
    if (inFlight.current || selectedId === null) {
      return;
    }
    inFlight.current = true;
    setFailure(undefined);
    let succeeded = false;
    try {
      attempt.current = await nextAttempt(
        attempt.current,
        attemptSignature({ cartFingerprint: fingerprint, addressId: selectedId, cardDigits: cardDigits(values.card_number) }),
        actions.newAttemptKey,
      );
      const result = await actions.placeOrder({
        attemptKey: attempt.current.key,
        addressId: selectedId,
        cardNumber: values.card_number,
        cartFingerprint: fingerprint,
      });
      resetField("card_number", { defaultValue: "" });
      if (result.ok) {
        succeeded = true;
        setPlaced(true);
        onPlaced(result.orderId);
        return;
      }
      if (result.kind === "attempt_changed") {
        attempt.current = { key: await actions.newAttemptKey(), signature: null };
      }
      showFailure(result);
    } finally {
      if (!succeeded) {
        inFlight.current = false;
      }
    }
  };

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (selectedId === null) {
      setAddressError(ADDRESS_REQUIRED);
      addressSection.current?.querySelector<HTMLElement>("input, button")?.focus();
      return;
    }
    setAddressError(undefined);
    void handleSubmit(place)(event);
  };

  const link = failure ? failureLinks(failure.kind) : null;

  return (
    <section aria-labelledby="checkout-heading" className="flex flex-col gap-8" aria-busy={busy || undefined}>
      <h1 id="checkout-heading" className="text-3xl font-semibold">
        Checkout
      </h1>
      {blocked.length > 0 ? (
        <div role="alert" className="flex flex-col items-start gap-3 rounded-md border-2 border-warning-strong bg-warning-soft p-4 text-sm text-primary">
          <p className="font-semibold">You cannot place this order yet. Some items in your cart need your attention:</p>
          <ul className="flex list-disc flex-col gap-1 pl-5">
            {blocked.map((line) => (
              <li key={line.sku}>
                {line.name}: {line.flags.map((flag) => describeFlag(flag).label).join(", ")}
              </li>
            ))}
          </ul>
          <ButtonLink href={CART_PATH} variant="secondary">
            Back to your cart to resolve them
          </ButtonLink>
        </div>
      ) : null}
      <section aria-labelledby="items-heading" className="flex flex-col gap-4">
        <h2 id="items-heading" className="text-xl font-semibold">
          Your items
        </h2>
        <ul aria-label="Items in your order" className="flex flex-col gap-3">
          {cart.items.map((line) => (
            <li key={line.sku} className="flex gap-4 rounded-lg border border-border bg-surface p-3">
              <div className="size-16 shrink-0 overflow-hidden rounded-md border border-border">
                <ProductImage thumbnailUrl={line.thumbnail_url} imageUrl={null} alt={line.name} sizes={IMAGE_SIZES} className="size-full object-cover" />
              </div>
              <div className="flex min-w-0 flex-1 flex-col gap-1">
                <p className="text-base font-semibold break-words">
                  <a href={productHref(line.sku)} className="text-primary underline">
                    {line.name}
                  </a>
                </p>
                <p className="text-sm text-secondary">
                  {line.quantity} × {money(line.price)}
                </p>
              </div>
              <p className="text-base font-semibold">
                <span className="sr-only">Line total: </span>
                {money(line.line_total)}
              </p>
            </li>
          ))}
        </ul>
        <dl className="flex max-w-md items-baseline justify-between gap-4 border-t border-border pt-4">
          <dt className="text-base font-medium">Subtotal ({pluralItems(cart.item_count)})</dt>
          <dd className="text-xl font-semibold">{money(cart.subtotal)}</dd>
        </dl>
      </section>
      <section ref={addressSection} aria-labelledby="address-heading" className="flex flex-col gap-4">
        <h2 id="address-heading" className="text-xl font-semibold">
          Shipping address
        </h2>
        <AddressPicker
          addresses={addresses}
          selectedId={selectedId}
          disabled={busy}
          {...(addressError ? { error: addressError } : {})}
          addAddress={actions.addAddress}
          onSelect={(addressId) => {
            setSelectedId(addressId);
            setAddressError(undefined);
          }}
          onAdded={(address) => {
            setAddresses((current) => [...current, address]);
            setSelectedId(address.id);
            setAddressError(undefined);
          }}
        />
      </section>
      <form onSubmit={submit} method="post" noValidate aria-labelledby="payment-heading" className="flex max-w-md flex-col gap-4">
        <h2 id="payment-heading" className="text-xl font-semibold">
          Payment
        </h2>
        <PaymentNote />
        {failure && !errors.card_number ? (
          <div role="alert" className="flex flex-col items-start gap-3 rounded-md border-2 border-danger-strong p-3 text-sm font-medium text-danger-strong">
            <p ref={alertRef} tabIndex={-1}>
              {placeOrderFailureMessage(failure)}
            </p>
            {link ? <ButtonLink href={link.href} variant="secondary">{link.label}</ButtonLink> : null}
          </div>
        ) : null}
        <Input
          label="Card number"
          type="text"
          inputMode="numeric"
          autoComplete="cc-number"
          autoCorrect="off"
          autoCapitalize="off"
          spellCheck={false}
          maxLength={CARD_INPUT_MAX_LENGTH}
          hint="Digits only. Spaces are added for you."
          error={errors.card_number?.message}
          required
          {...cardRegistration}
          onChange={(event) => {
            event.target.value = groupCardNumber(event.target.value);
            void cardRegistration.onChange(event);
          }}
        />
        <Button type="submit" loading={busy} disabled={blocked.length > 0 || cart.items.length === 0}>
          Place order
        </Button>
      </form>
    </section>
  );
}
