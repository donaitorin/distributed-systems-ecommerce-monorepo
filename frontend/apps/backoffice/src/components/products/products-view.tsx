"use client";

import { useState, useTransition } from "react";
import { useQueryStates } from "nuqs";
import { ButtonLink, Button, Pagination, PriceTag, ProductImage, StockBadge, Table, type TableColumn } from "@ecommerce/ui";
import type { Failure } from "../../lib/failure";
import { sameOriginMedia } from "../../lib/media";
import { PRODUCTS_PATH, ZONE_PATH } from "../../lib/paths";
import { productSearchParsers, type ProductSearchState } from "../../lib/product-search";
import type { Category, Product, ProductPage } from "../../lib/types";
import type { DeleteResult } from "../../server/product-actions";
import { DeleteProductDialog } from "../delete-product-dialog";
import { ProductFilters } from "./product-filters";
import { useNavigation } from "../navigation";

export type ProductsViewProps = {
  categories: readonly Category[];
  page: ProductPage | null;
  failure: Failure | null;
  deleteProduct: (sku: string, etag: string) => Promise<DeleteResult>;
};

const EMPTY_FILTERS: Partial<ProductSearchState> = {
  q: null,
  category: null,
  min_price: null,
  max_price: null,
  in_stock: false,
  sort: null,
  cursor: null,
};

function editHref(product: Product): string {
  return `${ZONE_PATH}${PRODUCTS_PATH}/${encodeURIComponent(product.sku)}`;
}

function Thumbnail({ product }: { product: Product }) {
  return (
    <div className="size-12 shrink-0 overflow-hidden rounded-md">
      <ProductImage
        thumbnailUrl={sameOriginMedia(product.thumbnail_url)}
        imageUrl={sameOriginMedia(product.image_url)}
        alt={product.image_url ? `Image of ${product.name}` : `${product.name} has no image`}
        sizes="48px"
      />
    </div>
  );
}

function failureText(failure: Failure): string {
  if (failure.status === 422) {
    return failure.fieldErrors.cursor !== undefined
      ? "This page link no longer matches the current filters."
      : "Some filters are not valid. Adjust them and try again.";
  }
  if (failure.status === 503 || failure.status === null) {
    return "The product search is not available right now. Try again in a moment.";
  }
  return failure.detail ?? failure.title;
}

export function ProductsView({ categories, page, failure, deleteProduct }: ProductsViewProps) {
  const router = useNavigation();
  const [pending, startTransition] = useTransition();
  const [state, setState] = useQueryStates(productSearchParsers, {
    history: "push",
    shallow: false,
    startTransition,
  });
  const [toDelete, setToDelete] = useState<Product | null>(null);

  const change = (patch: Partial<ProductSearchState>) => {
    void setState({ ...patch, cursor: null });
  };

  const columns: readonly TableColumn<Product>[] = [
    { key: "image", header: "Image", cell: (product) => <Thumbnail product={product} /> },
    { key: "sku", header: "SKU", cell: (product) => product.sku },
    {
      key: "name",
      header: "Name",
      cell: (product) => (
        <a href={editHref(product)} className="font-medium text-accent-strong underline">
          {product.name}
        </a>
      ),
    },
    { key: "category", header: "Category", cell: (product) => product.category?.name ?? "None" },
    { key: "price", header: "Price", cell: (product) => <PriceTag amount={product.price} />, align: "right" },
    { key: "stock", header: "Stock", cell: (product) => <StockBadge stock={product.stock} /> },
    {
      key: "actions",
      header: "Actions",
      cell: (product) => (
        <div className="flex gap-2">
          <ButtonLink
            variant="secondary"
            href={editHref(product)}
            aria-label={`Edit ${product.name}`}
          >
            Edit
          </ButtonLink>
          <Button
            variant="secondary"
            aria-label={`Delete ${product.name}`}
            onClick={() => {
              setToDelete(product);
            }}
          >
            Delete
          </Button>
        </div>
      ),
    },
  ];

  const renderCard = (product: Product) => (
    <div className="flex flex-col gap-3">
      <div className="flex items-start gap-3">
        <Thumbnail product={product} />
        <div className="flex min-w-0 flex-col gap-1">
          <a
            href={editHref(product)}
            className="font-medium break-words text-accent-strong underline"
          >
            {product.name}
          </a>
          <span className="text-sm text-secondary">{product.sku}</span>
          <span className="text-sm text-secondary">{product.category?.name ?? "No category"}</span>
        </div>
      </div>
      <div className="flex items-center justify-between gap-2">
        <PriceTag amount={product.price} />
        <StockBadge stock={product.stock} />
      </div>
      <div className="flex gap-2">
        <ButtonLink
          variant="secondary"
          href={editHref(product)}
          aria-label={`Edit ${product.name}`}
        >
          Edit
        </ButtonLink>
        <Button
          variant="secondary"
          aria-label={`Delete ${product.name}`}
          onClick={() => {
            setToDelete(product);
          }}
        >
          Delete
        </Button>
      </div>
    </div>
  );

  const filterErrors = failure?.status === 422 ? failure.fieldErrors : {};
  const staleCursor = Boolean(failure?.fieldErrors.cursor);

  return (
    <div className="flex flex-col gap-6">
      <ProductFilters
        state={state}
        categories={categories}
        fieldErrors={filterErrors}
        onChange={change}
        onClear={() => {
          void setState(EMPTY_FILTERS);
        }}
      />
      <div aria-busy={pending} className={pending ? "flex flex-col gap-4 opacity-60" : "flex flex-col gap-4"}>
        <Table
          caption="Product list"
          columns={columns}
          rows={page?.items ?? []}
          getRowKey={(product) => product.sku}
          error={failure ? failureText(failure) : undefined}
          emptyMessage="No products match these filters."
          renderCard={renderCard}
        />
        {staleCursor ? (
          <div>
            <Button
              variant="secondary"
              onClick={() => {
                void setState({ cursor: null });
              }}
            >
              Back to the first page
            </Button>
          </div>
        ) : null}
        {page ? (
          <Pagination
            label="Product pages"
            hasPrevious={page.prev_cursor !== null && page.prev_cursor !== undefined}
            hasNext={page.next_cursor !== null && page.next_cursor !== undefined}
            onPrevious={() => {
              void setState({ cursor: page.prev_cursor ?? null });
            }}
            onNext={() => {
              void setState({ cursor: page.next_cursor ?? null });
            }}
            total={page.total}
            totalExact={page.total_exact}
            loading={pending}
          />
        ) : null}
      </div>
      <DeleteProductDialog
        product={toDelete}
        deleteProduct={deleteProduct}
        onClose={() => {
          setToDelete(null);
        }}
        onDeleted={() => {
          setToDelete(null);
          router.refresh();
        }}
      />
    </div>
  );
}
