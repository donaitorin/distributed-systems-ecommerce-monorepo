"use client";

import { Button, ProductImage } from "@ecommerce/ui";
import { describeFlag, money, type CartLine } from "../../lib/cart";
import { productHref } from "../../lib/paths";
import { QuantityControl } from "./quantity-control";

export type CartLineItemProps = {
  line: CartLine;
  disabled: boolean;
  priceOverride?: string;
  onQuantity: (quantity: number) => void;
  onRemove: () => void;
  onAcceptPrice: (price: string) => void;
};

const IMAGE_SIZES = "96px";

function warningIcon() {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
      className="mt-0.5 size-4 shrink-0"
    >
      <path d="M12 9v4m0 4h.01M10.3 3.9 2.4 17.5A2 2 0 0 0 4.1 20.5h15.8a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z" />
    </svg>
  );
}

export function CartLineItem({
  line,
  disabled,
  priceOverride,
  onQuantity,
  onRemove,
  onAcceptPrice,
}: CartLineItemProps) {
  const notices = line.flags.map((flag) => ({ flag, notice: describeFlag(flag, priceOverride) }));
  const unavailable = line.flags.some((flag) => flag.type === "unavailable");

  return (
    <li className="flex flex-col gap-3 rounded-lg border border-border bg-surface p-4">
      <div className="flex gap-4">
        <div className="size-24 shrink-0 overflow-hidden rounded-md border border-border">
          <ProductImage
            thumbnailUrl={line.thumbnail_url}
            imageUrl={null}
            alt={line.name}
            sizes={IMAGE_SIZES}
            className="size-full object-cover"
          />
        </div>
        <div className="flex min-w-0 flex-1 flex-col gap-1">
          <h2 className="text-base font-semibold break-words">
            {unavailable ? (
              line.name
            ) : (
              <a href={productHref(line.sku)} className="text-primary underline">
                {line.name}
              </a>
            )}
          </h2>
          <p className="text-sm text-secondary">SKU {line.sku}</p>
          <p className="text-sm text-secondary">
            <span className="sr-only">Price each: </span>
            {money(line.price)} each
          </p>
        </div>
      </div>
      {notices.length > 0 ? (
        <ul className="flex flex-col gap-2" aria-label={`Notices for ${line.name}`}>
          {notices.map(({ flag, notice }) => (
            <li
              key={flag.type}
              className="flex flex-col gap-2 rounded-md border-2 border-warning-strong bg-warning-soft p-3 text-sm text-primary"
            >
              <p className="flex items-start gap-2">
                {warningIcon()}
                <span>
                  <strong className="font-semibold">{notice.label}.</strong> {notice.text}
                </span>
              </p>
              {notice.acceptablePrice ? (
                <div>
                  <Button
                    variant="secondary"
                    disabled={disabled}
                    aria-label={`Accept new price of ${money(notice.acceptablePrice)} for ${line.name}`}
                    onClick={() => {
                      onAcceptPrice(notice.acceptablePrice ?? "");
                    }}
                  >
                    Accept new price
                  </Button>
                </div>
              ) : null}
            </li>
          ))}
        </ul>
      ) : null}
      <div className="flex flex-wrap items-start justify-between gap-3">
        <QuantityControl name={line.name} value={line.quantity} onChange={onQuantity} disabled={disabled} />
        <div className="flex flex-col items-end gap-2">
          <p className="text-base font-semibold">
            <span className="sr-only">Line total: </span>
            {money(line.line_total)}
          </p>
          <Button
            variant="secondary"
            disabled={disabled}
            aria-label={`Remove ${line.name} from your cart`}
            onClick={onRemove}
          >
            Remove
          </Button>
        </div>
      </div>
    </li>
  );
}
