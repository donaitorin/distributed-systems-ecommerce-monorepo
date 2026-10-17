"use client";

import { useId, useState } from "react";
import { MAX_QUANTITY, MIN_QUANTITY, parseQuantity, QUANTITY_ERROR } from "../../lib/cart";

export type QuantityControlProps = {
  name: string;
  value: number;
  onChange: (next: number) => void;
  min?: number;
  max?: number;
  disabled?: boolean;
};

const STEP_BUTTON =
  "inline-flex size-11 items-center justify-center rounded-md border border-border-strong bg-surface text-lg font-medium text-primary hover:bg-surface-2 disabled:cursor-not-allowed disabled:border-border disabled:bg-surface-2 disabled:text-tertiary";

export function QuantityControl({
  name,
  value,
  onChange,
  min = MIN_QUANTITY,
  max = MAX_QUANTITY,
  disabled = false,
}: QuantityControlProps) {
  const errorId = useId();
  const [draft, setDraft] = useState({ shownFor: value, text: String(value) });
  const [error, setError] = useState<string>();
  if (draft.shownFor !== value) {
    setDraft({ shownFor: value, text: String(value) });
    setError(undefined);
  }

  const commit = () => {
    const parsed = parseQuantity(draft.text);
    if (parsed === null || parsed < min || parsed > max) {
      setError(max < MAX_QUANTITY ? `Enter a whole number from ${min} to ${max}.` : QUANTITY_ERROR);
      return;
    }
    setError(undefined);
    setDraft({ shownFor: value, text: String(parsed) });
    if (parsed !== value) {
      onChange(parsed);
    }
  };

  return (
    <div role="group" aria-label={`Quantity of ${name}`} className="flex flex-col gap-1">
      <div className="flex items-center gap-1">
        <button
          type="button"
          className={STEP_BUTTON}
          aria-label={`Decrease quantity of ${name}`}
          disabled={disabled || value <= min}
          onClick={() => {
            onChange(value - 1);
          }}
        >
          <span aria-hidden="true">&minus;</span>
        </button>
        <input
          type="text"
          inputMode="numeric"
          autoComplete="off"
          aria-label={`Quantity of ${name}`}
          aria-invalid={error ? true : undefined}
          aria-describedby={error ? errorId : undefined}
          disabled={disabled}
          value={draft.text}
          onChange={(event) => {
            setDraft({ shownFor: value, text: event.target.value });
            setError(undefined);
          }}
          onBlur={commit}
          onKeyDown={(event) => {
            if (event.key === "Enter") {
              event.preventDefault();
              commit();
            }
          }}
          className="min-h-11 w-16 rounded-md border border-border-strong bg-surface px-2 text-center text-base text-primary disabled:cursor-not-allowed disabled:border-border disabled:bg-surface-2 disabled:text-tertiary aria-invalid:border-danger-strong"
        />
        <button
          type="button"
          className={STEP_BUTTON}
          aria-label={`Increase quantity of ${name}`}
          disabled={disabled || value >= max}
          onClick={() => {
            onChange(value + 1);
          }}
        >
          <span aria-hidden="true">+</span>
        </button>
      </div>
      {error ? (
        <p id={errorId} role="alert" className="max-w-52 text-sm font-medium text-danger-strong">
          {error}
        </p>
      ) : null}
    </div>
  );
}
