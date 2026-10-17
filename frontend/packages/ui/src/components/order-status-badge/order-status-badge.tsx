import type { ReactNode } from "react";
import { cn } from "../../lib/cn";
import { CheckIcon, ClockIcon, CloseIcon } from "../../lib/icons";

export const ORDER_STATUSES = ["PENDING", "STOCK_RESERVED", "PAID", "CONFIRMED", "CANCELLED"] as const;

export type OrderStatusValue = (typeof ORDER_STATUSES)[number];

export type OrderStatusBadgeProps = {
  status: OrderStatusValue;
  className?: string;
};

type Appearance = { label: string; icon: ReactNode; classes: string };

const APPEARANCE: Record<OrderStatusValue, Appearance> = {
  PENDING: { label: "Pending", icon: <ClockIcon />, classes: "bg-surface-2 text-primary" },
  STOCK_RESERVED: { label: "Stock reserved", icon: <ClockIcon />, classes: "bg-surface-2 text-primary" },
  PAID: { label: "Paid", icon: <ClockIcon />, classes: "bg-surface-2 text-primary" },
  CONFIRMED: { label: "Confirmed", icon: <CheckIcon />, classes: "bg-success-soft text-success-strong" },
  CANCELLED: { label: "Cancelled", icon: <CloseIcon />, classes: "bg-danger-soft text-danger-strong" },
};

export function orderStatusLabel(status: OrderStatusValue): string {
  return APPEARANCE[status].label;
}

export function OrderStatusBadge({ status, className }: OrderStatusBadgeProps) {
  const { label, icon, classes } = APPEARANCE[status];

  return (
    <span
      className={cn("inline-flex items-center gap-1 rounded-full px-2 py-1 text-xs font-medium", classes, className)}
    >
      {icon}
      {label}
    </span>
  );
}
