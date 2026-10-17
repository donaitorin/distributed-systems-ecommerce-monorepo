import { statusView, type Order, type StatusTone } from "../../lib/orders";

export type OrderStatusBannerProps = { order: Pick<Order, "status" | "cancel_reason" | "refunded_at"> };

const TONE_CLASSES: Record<StatusTone, string> = {
  progress: "border-border-strong bg-surface-2 text-primary",
  success: "border-success-strong bg-success-soft text-primary",
  failure: "border-danger-strong bg-danger-soft text-primary",
};

function StatusIcon({ tone }: { tone: StatusTone }) {
  const common = {
    xmlns: "http://www.w3.org/2000/svg",
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 2,
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
    "aria-hidden": true,
    focusable: false,
    className: "size-6 shrink-0",
  };
  if (tone === "success") {
    return (
      <svg {...common}>
        <path d="M20 6 9 17l-5-5" />
      </svg>
    );
  }
  if (tone === "failure") {
    return (
      <svg {...common}>
        <path d="M18 6 6 18M6 6l12 12" />
      </svg>
    );
  }
  return (
    <svg {...common}>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 7v5l3 2" />
    </svg>
  );
}

export function OrderStatusBanner({ order }: OrderStatusBannerProps) {
  const view = statusView(order);
  return (
    <div
      role="status"
      aria-live="polite"
      aria-atomic="true"
      className={`flex items-start gap-3 rounded-lg border-2 p-4 ${TONE_CLASSES[view.tone]}`}
    >
      <StatusIcon tone={view.tone} />
      <div className="flex flex-col gap-1">
        <p className="text-lg font-semibold">{view.label}</p>
        <p className="text-base">{view.description}</p>
      </div>
    </div>
  );
}
