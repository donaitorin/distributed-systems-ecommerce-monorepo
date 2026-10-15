import { Button } from "../button/button";

export type PaginationProps = {
  hasPrevious: boolean;
  hasNext: boolean;
  onPrevious: () => void;
  onNext: () => void;
  total?: number;
  totalExact?: boolean;
  loading?: boolean;
  label?: string;
};

const NUMBER_FORMAT = new Intl.NumberFormat("en-US");

function totalMessage(total: number | undefined, totalExact: boolean): string {
  if (total === undefined) {
    return "";
  }
  const formatted = NUMBER_FORMAT.format(total);
  const noun = total === 1 ? "result" : "results";
  return totalExact ? `${formatted} ${noun}` : `About ${formatted} ${noun}`;
}

export function Pagination({
  hasPrevious,
  hasNext,
  onPrevious,
  onNext,
  total,
  totalExact = true,
  loading = false,
  label = "Pagination",
}: PaginationProps) {
  return (
    <nav aria-label={label} className="flex flex-wrap items-center justify-between gap-4">
      <p role="status" className="text-sm text-muted-foreground">
        {totalMessage(total, totalExact)}
      </p>
      <div className="flex gap-2">
        <Button variant="secondary" onClick={onPrevious} disabled={!hasPrevious || loading}>
          Previous
        </Button>
        <Button variant="secondary" onClick={onNext} disabled={!hasNext || loading}>
          Next
        </Button>
      </div>
    </nav>
  );
}
