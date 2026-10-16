"use client";

import { Button } from "../button/button";
import { CloseIcon } from "../../lib/icons";

export type FilterChipItem = {
  id: string;
  label: string;
};

export type FilterChipsProps = {
  chips: readonly FilterChipItem[];
  onRemove: (id: string) => void;
  onClearAll?: () => void;
  label?: string;
};

export function FilterChips({ chips, onRemove, onClearAll, label = "Active filters" }: FilterChipsProps) {
  if (chips.length === 0) {
    return null;
  }

  return (
    <section aria-label={label}>
      <ul className="flex list-none flex-wrap items-center gap-2 p-0">
        {chips.map((chip) => (
          <li key={chip.id}>
            <button
              type="button"
              aria-label={`Remove filter: ${chip.label}`}
              onClick={() => {
                onRemove(chip.id);
              }}
              className="inline-flex min-h-11 items-center gap-2 rounded-full border border-border-strong bg-surface px-4 text-sm font-medium text-primary hover:bg-surface-2"
            >
              {chip.label}
              <CloseIcon />
            </button>
          </li>
        ))}
        {onClearAll ? (
          <li>
            <Button variant="secondary" onClick={onClearAll}>
              Clear all filters
            </Button>
          </li>
        ) : null}
      </ul>
    </section>
  );
}
