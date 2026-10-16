"use client";

import { useRef, useState, useTransition } from "react";
import { useQueryStates } from "nuqs";
import {
  Button,
  EmptyState,
  FilterChips,
  Input,
  formatResultCount,
  Modal,
  Pagination,
  ProductCard,
  Select,
} from "@ecommerce/ui";
import {
  activeFilterChips,
  CLEARED_FILTERS,
  displayedSort,
  PAGE_SIZES,
  productSearchParsers,
  searchFailureMessage,
  SORT_CHOICES,
  sortToStore,
  type Category,
  type Failure,
  type ProductPage,
  type ProductSearchState,
  type SortValue,
} from "@ecommerce/web-core";
import { useUrlText } from "@ecommerce/web-core/client";
import { productHref } from "../../lib/paths";
import { FilterFields } from "./filter-fields";

export type ProductSearchProps = {
  categories: readonly Category[];
  page: ProductPage | null;
  failure: Failure | null;
};

const PRIORITY_CARDS = 4;

function countText(page: ProductPage | null): string {
  if (page === null) {
    return "";
  }
  return page.total === 0 ? "No results" : formatResultCount(page.total, page.total_exact);
}

export function ProductSearch({ categories, page, failure }: ProductSearchProps) {
  const [pending, startTransition] = useTransition();
  const [state, setState] = useQueryStates(productSearchParsers, {
    history: "push",
    shallow: false,
    startTransition,
  });
  const [drawerOpen, setDrawerOpen] = useState(false);
  const searchInput = useRef<HTMLInputElement>(null);

  const change = (patch: Partial<ProductSearchState>) => {
    void setState({ ...patch, cursor: null });
  };
  const clearAll = () => {
    void setState(CLEARED_FILTERS);
    searchInput.current?.focus();
  };

  const [queryDraft, setQueryDraft, applyQueryNow] = useUrlText({
    value: state.q,
    commit: (q) => {
      change({ q });
    },
  });

  const chips = activeFilterChips(state, categories);
  const filterErrors = failure?.status === 422 ? failure.fieldErrors : {};
  const staleCursor = Boolean(failure?.fieldErrors.cursor);
  const sortChoices = state.q ? SORT_CHOICES : SORT_CHOICES.filter(({ value }) => value !== "relevance");
  const filtersLabel = chips.length > 0 ? `Filters (${chips.length})` : "Filters";

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-end gap-2">
        <form
          role="search"
          aria-label="Search products"
          className="flex-1"
          onSubmit={(event) => {
            event.preventDefault();
            applyQueryNow();
          }}
        >
          <Input
            ref={searchInput}
            label="Search products"
            type="search"
            name="q"
            autoComplete="off"
            value={queryDraft}
            onChange={(event) => {
              setQueryDraft(event.target.value);
            }}
            hint="Name, description or SKU. Results update as you type or when you press Enter; small typos are tolerated."
          />
        </form>
        <Button
          variant="secondary"
          className="lg:hidden"
          aria-haspopup="dialog"
          onClick={() => {
            setDrawerOpen(true);
          }}
        >
          {filtersLabel}
        </Button>
      </div>
      <FilterChips
        chips={chips}
        onRemove={(id) => {
          change(chips.find((chip) => chip.id === id)?.patch ?? {});
          searchInput.current?.focus();
        }}
        onClearAll={clearAll}
      />
      <div className="flex flex-col gap-8 lg:flex-row">
        <aside aria-labelledby="filters-heading" className="hidden lg:block lg:w-64 lg:shrink-0">
          <h2 id="filters-heading" className="mb-4 text-lg font-semibold">
            Filters
          </h2>
          <FilterFields state={state} categories={categories} fieldErrors={filterErrors} onChange={change} />
        </aside>
        <Modal
          variant="drawer"
          open={drawerOpen}
          onOpenChange={setDrawerOpen}
          title="Filters"
          footer={
            <Button
              onClick={() => {
                setDrawerOpen(false);
              }}
            >
              Show results
            </Button>
          }
        >
          <FilterFields state={state} categories={categories} fieldErrors={filterErrors} onChange={change} />
        </Modal>
        <section
          aria-labelledby="results-heading"
          aria-busy={pending}
          className={pending ? "flex min-w-0 flex-1 flex-col gap-4 opacity-60" : "flex min-w-0 flex-1 flex-col gap-4"}
        >
          <h2 id="results-heading" className="sr-only">
            Results
          </h2>
          <div className="flex flex-wrap items-end justify-between gap-4">
            <p className="text-sm text-secondary">{countText(page)}</p>
            <div className="grid grid-cols-2 gap-2">
              <Select
                label="Sort by"
                options={sortChoices}
                value={displayedSort(state)}
                onValueChange={(value) => {
                  change({ sort: sortToStore(value as SortValue, state.q) });
                }}
              />
              <Select
                label="Results per page"
                options={PAGE_SIZES.map((size) => ({ value: String(size), label: `${size} per page` }))}
                value={String(state.limit)}
                onValueChange={(value) => {
                  change({ limit: Number(value) });
                }}
              />
            </div>
          </div>
          {failure ? (
            <div role="alert" className="flex flex-col items-start gap-3 text-base font-medium text-danger-strong">
              <p>{searchFailureMessage(failure)}</p>
              {staleCursor ? (
                <Button
                  variant="secondary"
                  onClick={() => {
                    void setState({ cursor: null });
                  }}
                >
                  Back to the first page
                </Button>
              ) : null}
            </div>
          ) : null}
          {page && page.items.length === 0 ? (
            <EmptyState
              title="No products found"
              description={
                chips.length > 0
                  ? "Nothing matches these filters. Remove a filter or try different words."
                  : "There are no products yet. Check back soon."
              }
              action={
                chips.length > 0 ? (
                  <Button variant="secondary" onClick={clearAll}>
                    Clear all filters
                  </Button>
                ) : undefined
              }
            />
          ) : null}
          {page && page.items.length > 0 ? (
            <ul className="grid list-none grid-cols-1 gap-4 p-0 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
              {page.items.map((product, index) => (
                <li key={product.sku}>
                  <ProductCard
                    name={product.name}
                    href={productHref(product.sku)}
                    price={product.price}
                    stock={product.stock}
                    thumbnailUrl={product.thumbnail_url ?? null}
                    imageUrl={product.image_url ?? null}
                    priority={index < PRIORITY_CARDS}
                  />
                </li>
              ))}
            </ul>
          ) : null}
          {page ? (
            <Pagination
              label="Product pages"
              hasPrevious={page.prev_cursor !== null && page.prev_cursor !== undefined}
              hasNext={page.next_cursor !== null && page.next_cursor !== undefined}
              onPrevious={() => {
                void setState({ cursor: page.prev_cursor ?? null }, { scroll: true });
              }}
              onNext={() => {
                void setState({ cursor: page.next_cursor ?? null }, { scroll: true });
              }}
              total={page.total}
              totalExact={page.total_exact}
              loading={pending}
            />
          ) : null}
        </section>
      </div>
    </div>
  );
}
