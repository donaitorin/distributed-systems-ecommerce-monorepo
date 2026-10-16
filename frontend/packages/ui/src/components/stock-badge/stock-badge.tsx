import type { ReactNode } from "react";
import { cn } from "../../lib/cn";
import { AlertIcon, CheckIcon, CloseIcon } from "../../lib/icons";

export type StockBadgeProps = {
  stock: number;
  lowStockThreshold?: number;
  className?: string;
};

type StockStatus = { label: string; icon: ReactNode; classes: string };

function statusFor(stock: number, lowStockThreshold: number): StockStatus {
  if (stock <= 0) {
    return {
      label: "Out of stock",
      icon: <CloseIcon />,
      classes: "bg-danger-soft text-danger-strong",
    };
  }
  if (stock <= lowStockThreshold) {
    return {
      label: `Only ${stock} left`,
      icon: <AlertIcon />,
      classes: "bg-warning-soft text-warning-strong",
    };
  }
  return {
    label: "In stock",
    icon: <CheckIcon />,
    classes: "bg-success-soft text-success-strong",
  };
}

export function StockBadge({ stock, lowStockThreshold = 5, className }: StockBadgeProps) {
  const { label, icon, classes } = statusFor(stock, lowStockThreshold);

  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full px-2 py-1 text-xs font-medium",
        classes,
        className,
      )}
    >
      {icon}
      {label}
    </span>
  );
}
