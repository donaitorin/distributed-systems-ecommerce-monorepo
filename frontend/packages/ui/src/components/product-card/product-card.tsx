import { cn } from "../../lib/cn";
import { PriceTag } from "../price-tag/price-tag";
import { ProductImage } from "../product-image/product-image";
import { StockBadge } from "../stock-badge/stock-badge";

export type ProductCardProps = {
  name: string;
  href: string;
  price: string;
  stock: number;
  thumbnailUrl: string | null;
  imageUrl: string | null;
  currency?: string;
  headingLevel?: 2 | 3 | 4;
  priority?: boolean;
  className?: string;
};

export function ProductCard({
  name,
  href,
  price,
  stock,
  thumbnailUrl,
  imageUrl,
  currency,
  headingLevel = 2,
  priority,
  className,
}: ProductCardProps) {
  const Heading = `h${headingLevel}` as const;

  return (
    <article
      className={cn(
        "relative flex flex-col overflow-hidden rounded-lg border border-border bg-background",
        className,
      )}
    >
      <ProductImage thumbnailUrl={thumbnailUrl} imageUrl={imageUrl} alt={name} priority={priority} />
      <div className="flex flex-1 flex-col gap-2 p-4">
        <Heading className="text-base font-semibold">
          <a href={href} className="after:absolute after:inset-0">
            {name}
          </a>
        </Heading>
        <PriceTag amount={price} currency={currency} />
        <StockBadge stock={stock} className="self-start" />
      </div>
    </article>
  );
}

export function ProductCardSkeleton({ className }: { className?: string }) {
  return (
    <div
      role="status"
      className={cn("flex flex-col overflow-hidden rounded-lg border border-border", className)}
    >
      <span className="sr-only">Loading product</span>
      <div className="aspect-square w-full animate-pulse bg-muted" aria-hidden="true" />
      <div className="flex flex-col gap-2 p-4" aria-hidden="true">
        <div className="h-5 w-3/4 animate-pulse rounded-sm bg-muted" />
        <div className="h-5 w-1/4 animate-pulse rounded-sm bg-muted" />
        <div className="h-6 w-1/3 animate-pulse rounded-full bg-muted" />
      </div>
    </div>
  );
}
