"use client";

import { useId, type ComponentProps } from "react";
import { cn } from "../../lib/cn";

export type CheckboxProps = Omit<ComponentProps<"input">, "type"> & {
  label: string;
  hint?: string;
};

export function Checkbox({ label, hint, id, className, ...props }: CheckboxProps) {
  const generatedId = useId();
  const inputId = id ?? generatedId;
  const hintId = `${inputId}-hint`;

  return (
    <div className="flex flex-col">
      <label htmlFor={inputId} className="flex min-h-11 cursor-pointer items-center gap-3 text-base text-primary">
        <input
          id={inputId}
          type="checkbox"
          aria-describedby={hint ? hintId : undefined}
          className={cn("size-5 shrink-0 accent-accent-strong disabled:cursor-not-allowed", className)}
          {...props}
        />
        {label}
      </label>
      {hint ? (
        <p id={hintId} className="ps-8 text-sm text-secondary">
          {hint}
        </p>
      ) : null}
    </div>
  );
}
