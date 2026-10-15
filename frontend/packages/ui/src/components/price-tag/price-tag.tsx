import { cn } from "../../lib/cn";

export type PriceTagProps = {
  amount: string;
  currency?: string;
  className?: string;
};

const DECIMAL_AMOUNT = /^\d+(\.\d{1,2})?$/;

export function formatPrice(amount: string, currency: string): string | null {
  if (!DECIMAL_AMOUNT.test(amount)) {
    return null;
  }
  return new Intl.NumberFormat("en-US", { style: "currency", currency }).format(
    amount as `${number}`,
  );
}

export function PriceTag({ amount, currency = "USD", className }: PriceTagProps) {
  const formatted = formatPrice(amount, currency);

  if (formatted === null) {
    return (
      <span className={cn("text-base font-semibold text-muted-foreground", className)}>
        <span aria-hidden="true">&mdash;</span>
        <span className="sr-only">Price unavailable</span>
      </span>
    );
  }

  return <span className={cn("text-base font-semibold text-foreground", className)}>{formatted}</span>;
}
