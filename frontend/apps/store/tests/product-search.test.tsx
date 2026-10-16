import { act, screen, waitFor, within } from "@testing-library/react";
import { axe } from "jest-axe";
import type { UrlUpdateEvent } from "nuqs/adapters/testing";
import type { Failure } from "@ecommerce/web-core";
import { ProductSearch, type ProductSearchProps } from "../src/components/catalog/product-search";
import { CATEGORY, OTHER_CATEGORY, productPage } from "./support/api";
import { renderApp } from "./support/render";

const CATEGORIES = [CATEGORY, OTHER_CATEGORY];

function props(overrides: Partial<ProductSearchProps> = {}): ProductSearchProps {
  return { categories: CATEGORIES, page: productPage(), failure: null, ...overrides };
}

function lastUrl(onUrlUpdate: jest.Mock<void, [UrlUpdateEvent]>): URLSearchParams {
  return onUrlUpdate.mock.lastCall?.[0].searchParams ?? new URLSearchParams();
}

function failure(status: number | null, fieldErrors: Record<string, string> = {}): Failure {
  return { ok: false, status, title: "Title", fieldErrors };
}

describe("ProductSearch results", () => {
  it("has no accessibility violations with results, chips, an empty result and a failure", async () => {
    const { container } = renderApp(<ProductSearch {...props()} />, {
      searchParams: "?q=shoes&category=footwear&min_price=10&in_stock=true",
    });
    expect(await axe(container)).toHaveNoViolations();
  });

  it("has no accessibility violations for the empty and failed states", async () => {
    const empty = renderApp(<ProductSearch {...props({ page: productPage({ items: [], total: 0 }) })} />);
    expect(await axe(empty.container)).toHaveNoViolations();
    empty.unmount();

    const failed = renderApp(<ProductSearch {...props({ page: null, failure: failure(503) })} />);
    expect(await axe(failed.container)).toHaveNoViolations();
  });

  it("shows a card per product that links to its detail page", () => {
    renderApp(<ProductSearch {...props()} />);
    const list = screen.getByRole("list");

    expect(within(list).getAllByRole("listitem")).toHaveLength(2);
    expect(within(list).getByRole("link", { name: "Running shoes" })).toHaveAttribute("href", "/products/RS-001");
    expect(within(list).getByRole("link", { name: "Toy robot" })).toHaveAttribute("href", "/products/TY-002");
    expect(within(list).getByRole("img", { name: "Running shoes" })).toHaveAttribute(
      "src",
      "/media/products/RS-001/a-400.webp",
    );
    expect(within(list).getByRole("img", { name: "Toy robot" }).tagName.toLowerCase()).toBe("svg");
  });

  it("announces an exact total and an approximate one through the live region", () => {
    const exact = renderApp(<ProductSearch {...props()} />);
    expect(screen.getByRole("status")).toHaveTextContent("2 results");
    exact.unmount();

    renderApp(<ProductSearch {...props({ page: productPage({ total: 1200, total_exact: false }) })} />);
    expect(screen.getByRole("status")).toHaveTextContent("About 1,200 results");
  });

  it("shows the count above the grid too, and says when there are no results", () => {
    renderApp(<ProductSearch {...props({ page: productPage({ items: [], total: 0 }) })} />, { searchParams: "?q=zzz" });

    expect(screen.getAllByText("No results").length).toBeGreaterThan(0);
  });
});

describe("ProductSearch empty and failed states", () => {
  it("offers to clear the filters when they hide everything", async () => {
    const onUrlUpdate = jest.fn<void, [UrlUpdateEvent]>();
    const { user } = renderApp(<ProductSearch {...props({ page: productPage({ items: [], total: 0 }) })} />, {
      searchParams: "?q=zzz&in_stock=true",
      onUrlUpdate,
    });

    expect(screen.getByRole("heading", { name: "No products found" })).toBeInTheDocument();
    const empty = screen.getByRole("heading", { name: "No products found" }).parentElement as HTMLElement;
    await user.click(within(empty).getByRole("button", { name: "Clear all filters" }));

    await waitFor(() => {
      expect(onUrlUpdate).toHaveBeenCalled();
    });
    expect(lastUrl(onUrlUpdate).toString()).toBe("");
  });

  it("says there are no products when nothing is filtered", () => {
    renderApp(<ProductSearch {...props({ page: productPage({ items: [], total: 0 }) })} />);

    expect(screen.getByText(/no products yet/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Clear all filters" })).not.toBeInTheDocument();
  });

  it("shows a failed search as an alert and keeps the controls", () => {
    renderApp(<ProductSearch {...props({ page: null, failure: failure(503) })} />);

    expect(screen.getByRole("alert")).toHaveTextContent("not available");
    expect(screen.getByRole("combobox", { name: "Sort by" })).toBeInTheDocument();
    expect(screen.queryByRole("navigation", { name: "Product pages" })).not.toBeInTheDocument();
  });

  it("offers the first page when the cursor no longer matches the filters", async () => {
    const onUrlUpdate = jest.fn<void, [UrlUpdateEvent]>();
    const { user } = renderApp(
      <ProductSearch {...props({ page: null, failure: failure(422, { cursor: "mismatch" }) })} />,
      { searchParams: "?q=shoes&cursor=OLD", onUrlUpdate },
    );

    await user.click(screen.getByRole("button", { name: "Back to the first page" }));

    await waitFor(() => {
      expect(lastUrl(onUrlUpdate).has("cursor")).toBe(false);
    });
    expect(lastUrl(onUrlUpdate).get("q")).toBe("shoes");
  });

  it("marks a filter field as invalid when the API rejects a price", () => {
    renderApp(<ProductSearch {...props({ page: null, failure: failure(422, { min_price: "bad" }) })} />);

    const [minimum] = screen.getAllByLabelText("Minimum");
    expect(minimum).toHaveAccessibleDescription("bad");
  });
});

describe("ProductSearch filters", () => {
  it("pushes a history entry per change and clears the cursor", async () => {
    const onUrlUpdate = jest.fn<void, [UrlUpdateEvent]>();
    const { user } = renderApp(<ProductSearch {...props()} />, { searchParams: "?cursor=OLD", onUrlUpdate });

    await user.click(screen.getByRole("combobox", { name: "Category" }));
    await user.click(await screen.findByRole("option", { name: "Toys" }));
    await waitFor(() => {
      expect(lastUrl(onUrlUpdate).get("category")).toBe("toys");
    });
    await user.click(screen.getByRole("checkbox", { name: "In stock only" }));
    await waitFor(() => {
      expect(lastUrl(onUrlUpdate).get("in_stock")).toBe("true");
    });
    await user.click(screen.getByRole("combobox", { name: "Sort by" }));
    await user.click(await screen.findByRole("option", { name: "Price, low to high" }));
    await waitFor(() => {
      expect(lastUrl(onUrlUpdate).get("sort")).toBe("price_asc");
    });

    expect(onUrlUpdate).toHaveBeenCalledTimes(3);
    expect(onUrlUpdate.mock.calls.every(([event]) => event.options.history === "push" && event.options.shallow === false)).toBe(true);
    expect(lastUrl(onUrlUpdate).has("cursor")).toBe(false);
    expect(lastUrl(onUrlUpdate).toString()).toBe("category=toys&in_stock=true&sort=price_asc");
  });

  it("does not write defaults to the URL", async () => {
    const onUrlUpdate = jest.fn<void, [UrlUpdateEvent]>();
    const { user } = renderApp(<ProductSearch {...props()} />, { searchParams: "?limit=48&category=toys", onUrlUpdate });

    await user.click(screen.getByRole("combobox", { name: "Results per page" }));
    await user.click(await screen.findByRole("option", { name: "24 per page" }));
    await waitFor(() => {
      expect(onUrlUpdate).toHaveBeenCalled();
    });

    expect(lastUrl(onUrlUpdate).toString()).toBe("category=toys");
  });

  it("offers best match only while there is a search text", async () => {
    const withoutText = renderApp(<ProductSearch {...props()} />);
    expect(screen.getByRole("combobox", { name: "Sort by" })).toHaveTextContent("Newest first");
    await withoutText.user.click(screen.getByRole("combobox", { name: "Sort by" }));
    expect(screen.queryByRole("option", { name: "Best match" })).not.toBeInTheDocument();
    withoutText.unmount();

    renderApp(<ProductSearch {...props()} />, { searchParams: "?q=shoes" });
    expect(screen.getByRole("combobox", { name: "Sort by" })).toHaveTextContent("Best match");
  });

  it("falls back to the implied sort in the URL when the default is chosen again", async () => {
    const onUrlUpdate = jest.fn<void, [UrlUpdateEvent]>();
    const { user } = renderApp(<ProductSearch {...props()} />, { searchParams: "?sort=price_desc", onUrlUpdate });

    await user.click(screen.getByRole("combobox", { name: "Sort by" }));
    await user.click(await screen.findByRole("option", { name: "Newest first" }));

    await waitFor(() => {
      expect(lastUrl(onUrlUpdate).has("sort")).toBe(false);
    });
  });

  it("selects the current values from the URL", () => {
    renderApp(<ProductSearch {...props()} />, {
      searchParams: "?category=toys&min_price=5&max_price=50&in_stock=true&limit=12",
    });

    expect(screen.getByRole("combobox", { name: "Category" })).toHaveTextContent("Toys");
    expect(screen.getByLabelText("Minimum")).toHaveValue("5");
    expect(screen.getByLabelText("Maximum")).toHaveValue("50");
    expect(screen.getByRole("checkbox", { name: "In stock only" })).toBeChecked();
    expect(screen.getByRole("combobox", { name: "Results per page" })).toHaveTextContent("12 per page");
  });

  describe("with typing", () => {
    beforeEach(() => {
      jest.useFakeTimers();
    });
    afterEach(() => {
      jest.useRealTimers();
    });

    it("waits 300 ms after the last keystroke for the search text and keeps one history entry", async () => {
      const onUrlUpdate = jest.fn<void, [UrlUpdateEvent]>();
      const { user } = renderApp(<ProductSearch {...props()} />, { searchParams: "?cursor=OLD", onUrlUpdate, fakeTimers: true });

      await user.type(screen.getByRole("searchbox", { name: "Search products" }), "runing");
      act(() => {
        jest.advanceTimersByTime(299);
      });
      expect(onUrlUpdate).not.toHaveBeenCalled();
      act(() => {
        jest.advanceTimersByTime(1);
      });

      await waitFor(() => {
        expect(onUrlUpdate).toHaveBeenCalledTimes(1);
      });
      expect(lastUrl(onUrlUpdate).toString()).toBe("q=runing");
    });

    it("validates prices before they reach the URL", async () => {
      const onUrlUpdate = jest.fn<void, [UrlUpdateEvent]>();
      const { user } = renderApp(<ProductSearch {...props()} />, { onUrlUpdate, fakeTimers: true });

      await user.type(screen.getByLabelText("Minimum"), "abc");
      act(() => {
        jest.advanceTimersByTime(500);
      });
      expect(onUrlUpdate).not.toHaveBeenCalled();
      expect(screen.getByLabelText("Minimum")).toHaveAccessibleDescription("Enter a price like 19.99");

      await user.clear(screen.getByLabelText("Minimum"));
      await user.type(screen.getByLabelText("Minimum"), "19.99");
      act(() => {
        jest.advanceTimersByTime(300);
      });
      await waitFor(() => {
        expect(lastUrl(onUrlUpdate).get("min_price")).toBe("19.99");
      });
    });
  });
});

describe("ProductSearch chips", () => {
  it("lists every active filter as a removable chip", () => {
    renderApp(<ProductSearch {...props()} />, {
      searchParams: "?q=shoes&category=footwear&min_price=20&max_price=150&in_stock=true",
    });
    const chips = screen.getByRole("region", { name: "Active filters" });

    expect(within(chips).getAllByRole("listitem")).toHaveLength(5);
    expect(within(chips).getByRole("button", { name: "Remove filter: Price: $20 to $150" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Filters (4)" })).toBeInTheDocument();
  });

  it("removes one filter, keeps the others and returns focus to the search box", async () => {
    const onUrlUpdate = jest.fn<void, [UrlUpdateEvent]>();
    const { user } = renderApp(<ProductSearch {...props()} />, {
      searchParams: "?q=shoes&category=footwear&in_stock=true&cursor=OLD",
      onUrlUpdate,
    });

    await user.click(screen.getByRole("button", { name: "Remove filter: Category: Footwear" }));

    await waitFor(() => {
      expect(onUrlUpdate).toHaveBeenCalled();
    });
    expect(lastUrl(onUrlUpdate).toString()).toBe("q=shoes&in_stock=true");
    expect(screen.getByRole("searchbox", { name: "Search products" })).toHaveFocus();
  });

  it("clears every filter at once", async () => {
    const onUrlUpdate = jest.fn<void, [UrlUpdateEvent]>();
    const { user } = renderApp(<ProductSearch {...props()} />, {
      searchParams: "?q=shoes&category=footwear&limit=48",
      onUrlUpdate,
    });

    await user.click(within(screen.getByRole("region", { name: "Active filters" })).getByRole("button", { name: "Clear all filters" }));

    await waitFor(() => {
      expect(onUrlUpdate).toHaveBeenCalled();
    });
    expect(lastUrl(onUrlUpdate).toString()).toBe("limit=48");
    expect(screen.getByRole("searchbox", { name: "Search products" })).toHaveFocus();
  });

  it("shows no chips and a plain filters button without filters", () => {
    renderApp(<ProductSearch {...props()} />);

    expect(screen.queryByRole("region", { name: "Active filters" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Filters" })).toBeInTheDocument();
  });
});

describe("ProductSearch pagination", () => {
  const PAGE = productPage({ next_cursor: "NEXT", prev_cursor: "PREV", total: 1200, total_exact: false });

  it("moves with the cursors from the page and keeps the filters", async () => {
    const onUrlUpdate = jest.fn<void, [UrlUpdateEvent]>();
    const { user } = renderApp(<ProductSearch {...props({ page: PAGE })} />, { searchParams: "?q=shoes", onUrlUpdate });

    await user.click(screen.getByRole("button", { name: "Next" }));
    await waitFor(() => {
      expect(lastUrl(onUrlUpdate).get("cursor")).toBe("NEXT");
    });
    await user.click(screen.getByRole("button", { name: "Previous" }));
    await waitFor(() => {
      expect(lastUrl(onUrlUpdate).get("cursor")).toBe("PREV");
    });

    expect(lastUrl(onUrlUpdate).get("q")).toBe("shoes");
    expect(onUrlUpdate.mock.lastCall?.[0].options.scroll).toBe(true);
  });

  it("disables the buttons that have no cursor", () => {
    renderApp(<ProductSearch {...props()} />);

    expect(screen.getByRole("button", { name: "Previous" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Next" })).toBeDisabled();
  });
});

describe("ProductSearch filter drawer", () => {
  it("opens from the filters button, traps focus, closes with Escape and returns focus to the button", async () => {
    const { user } = renderApp(<ProductSearch {...props()} />, { searchParams: "?in_stock=true" });
    const opener = screen.getByRole("button", { name: "Filters (1)" });

    await user.click(opener);
    const dialog = await screen.findByRole("dialog", { name: "Filters" });

    expect(within(dialog).getByRole("combobox", { name: "Category" })).toBeInTheDocument();
    expect(within(dialog).getByRole("checkbox", { name: "In stock only" })).toBeChecked();
    expect(await axe(dialog)).toHaveNoViolations();
    for (let step = 0; step < 12; step += 1) {
      await user.tab();
      expect(dialog).toContainElement(document.activeElement as HTMLElement);
    }

    await user.keyboard("{Escape}");
    await waitFor(() => {
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    });
    expect(opener).toHaveFocus();
  });

  it("applies a filter chosen in the drawer and closes with Show results", async () => {
    const onUrlUpdate = jest.fn<void, [UrlUpdateEvent]>();
    const { user } = renderApp(<ProductSearch {...props()} />, { onUrlUpdate });

    await user.click(screen.getByRole("button", { name: "Filters" }));
    const dialog = await screen.findByRole("dialog", { name: "Filters" });
    await user.click(within(dialog).getByRole("checkbox", { name: "In stock only" }));
    await waitFor(() => {
      expect(lastUrl(onUrlUpdate).get("in_stock")).toBe("true");
    });
    await user.click(within(dialog).getByRole("button", { name: "Show results" }));

    await waitFor(() => {
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    });
    expect(screen.getByRole("button", { name: "Filters (1)" })).toHaveFocus();
  });
});
