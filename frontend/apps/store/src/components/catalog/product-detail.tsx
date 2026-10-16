import { PriceTag, ProductImage, StockBadge } from "@ecommerce/ui";
import type { Product } from "@ecommerce/web-core";
import { categoryHref, PRODUCTS_PATH } from "../../lib/paths";
import { AddToCartSlot } from "./add-to-cart-slot";

export function formatWeight(weightKg: string | null): string | null {
  if (weightKg === null) {
    return null;
  }
  const value = Number(weightKg);
  return Number.isFinite(value) ? `${value} kg` : weightKg;
}

const IMAGE_SIZES = "(min-width: 48rem) 50vw, 100vw";

export function ProductDetail({ product }: { product: Product }) {
  const weight = formatWeight(product.weight_kg);

  return (
    <article aria-labelledby="product-heading" className="flex flex-col gap-6">
      <nav aria-label="Breadcrumb">
        <ol className="flex flex-wrap items-center gap-2 text-sm text-secondary">
          <li>
            <a href={PRODUCTS_PATH} className="text-accent-strong underline">
              Products
            </a>
          </li>
          {product.category ? (
            <li className="flex items-center gap-2">
              <span aria-hidden="true">/</span>
              <a href={categoryHref(product.category.slug)} className="text-accent-strong underline">
                {product.category.name}
              </a>
            </li>
          ) : null}
          <li className="flex items-center gap-2">
            <span aria-hidden="true">/</span>
            <span aria-current="page">{product.name}</span>
          </li>
        </ol>
      </nav>
      <div className="flex flex-col gap-8 md:flex-row">
        <div className="w-full overflow-hidden rounded-lg border border-border md:w-1/2">
          <ProductImage
            thumbnailUrl={null}
            imageUrl={product.image_url ?? null}
            alt={product.name}
            sizes={IMAGE_SIZES}
            priority
          />
        </div>
        <div className="flex min-w-0 flex-1 flex-col gap-4">
          <h1 id="product-heading" className="text-3xl font-semibold break-words">
            {product.name}
          </h1>
          <div className="flex flex-wrap items-center gap-3">
            <PriceTag amount={product.price} className="text-2xl" />
            <StockBadge stock={product.stock} />
          </div>
          {product.description ? (
            <p className="max-w-prose text-base whitespace-pre-line text-primary">{product.description}</p>
          ) : null}
          <AddToCartSlot product={product} />
          <dl className="flex flex-col gap-2 border-t border-border pt-4 text-sm">
            <div className="flex gap-2">
              <dt className="font-medium">SKU</dt>
              <dd className="text-secondary">{product.sku}</dd>
            </div>
            <div className="flex gap-2">
              <dt className="font-medium">Category</dt>
              <dd className="text-secondary">{product.category?.name ?? "Uncategorised"}</dd>
            </div>
            {weight ? (
              <div className="flex gap-2">
                <dt className="font-medium">Weight</dt>
                <dd className="text-secondary">{weight}</dd>
              </div>
            ) : null}
          </dl>
        </div>
      </div>
    </article>
  );
}
