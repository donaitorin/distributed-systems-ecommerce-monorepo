import type { ReactNode } from "react";

export type EmptyStateProps = {
  title: string;
  description?: string;
  action?: ReactNode;
  headingLevel?: 2 | 3;
};

export function EmptyState({ title, description, action, headingLevel = 2 }: EmptyStateProps) {
  const Heading = `h${headingLevel}` as const;

  return (
    <div className="flex flex-col items-start gap-3 rounded-lg border border-dashed border-border-strong bg-surface p-6">
      <Heading className="text-xl font-semibold text-primary">{title}</Heading>
      {description ? <p className="max-w-prose text-base text-secondary">{description}</p> : null}
      {action}
    </div>
  );
}
