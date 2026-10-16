import { act, screen, waitFor, within } from "@testing-library/react";
import { axe } from "jest-axe";
import type { UrlUpdateEvent } from "nuqs/adapters/testing";
import { ProductsView, type ProductsViewProps } from "../src/components/products/products-view";
import type { Failure } from "../src/lib/failure";
import { CATEGORY, product } from "./support/api";
import { resetRouter, router } from "./support/navigation-mock";
import { renderApp } from "./support/render";

jest.mock("next/navigation", () => jest.requireActual("./support/navigation-mock") as unknown);

const CATEGORIES = [CATEGORY, { id: "c2", name: "Toys", slug: "toys" }];
const PAGE = {
  items: [
    product(),
    product({ sku: "TY-002", name: "Toy robot", price: "19.50", stock: 0, category: null, version: 1, image_url: "http://127.0.0.1:8000/media/media/products/TY-002/a-1200.webp", thumbnail_url: "http://127.0.0.1:8000/media/media/products/TY-002/a-400.webp" }),
  ],
  next_cursor: "NEXT",
  prev_cursor: "PREV",
  total: 1200,
  total_exact: false,
};

function props(overrides: Partial<ProductsViewProps> = {}): ProductsViewProps {
  return {
    categories: CATEGORIES,
    page: PAGE,
    failure: null,
    deleteProduct: jest.fn().mockResolvedValue({ ok: true }),
    ...overrides,
  };
}

function lastUrl(onUrlUpdate: jest.Mock<void, [UrlUpdateEvent]>): URLSearchParams {
  return onUrlUpdate.mock.lastCall?.[0].searchParams ?? new URLSearchParams();
}

beforeEach(() => {
  resetRouter();
});

describe("ProductsView results", () => {
  it("lists the products in a captioned table and as cards, with no accessibility violations", async () => {
    const { container } = renderApp(<ProductsView {...props()} />);

    const table = screen.getByRole("table", { name: "Product list" });
    expect(within(table).getByRole("link", { name: "Running shoes" })).toHaveAttribute("href", "/admin/products/RS-001");
    expect(within(table).getByText("$59.00")).toBeInTheDocument();
    expect(within(table).getByText("None")).toBeInTheDocument();
    expect(within(screen.getByRole("list", { name: "Product list" })).getAllByRole("listitem")).toHaveLength(2);
    expect(await axe(container)).toHaveNoViolations();
  });

  it("serves product images from the page's own origin and falls back to a placeholder", () => {
    renderApp(<ProductsView {...props()} />);
    const table = screen.getByRole("table", { name: "Product list" });

    expect(within(table).getByAltText("Image of Toy robot")).toHaveAttribute("src", "/media/media/products/TY-002/a-400.webp");
    expect(within(table).getByRole("img", { name: "Running shoes has no image" })).toBeInTheDocument();
  });

  it("announces the approximate total in a status region when the total is an estimate", () => {
    renderApp(<ProductsView {...props()} />);

    expect(screen.getByRole("status")).toHaveTextContent("About 1,200 results");
  });

  it("announces an exact total plainly", () => {
    renderApp(<ProductsView {...props({ page: { ...PAGE, total: 2, total_exact: true } })} />);

    expect(screen.getByRole("status")).toHaveTextContent("2 results");
  });

  it("shows the empty message when nothing matches", () => {
    renderApp(<ProductsView {...props({ page: { items: [], next_cursor: null, prev_cursor: null, total: 0, total_exact: true } })} />);

    expect(within(screen.getByRole("table")).getByText("No products match these filters.")).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("0 results");
  });

  it.each([
    [{ status: 503, title: "Search timeout", fieldErrors: {} }, "not available right now"],
    [{ status: null, title: "Unreachable", fieldErrors: {} }, "not available right now"],
    [{ status: 422, title: "Validation failed", fieldErrors: { min_price: "must not be greater than max_price" } }, "filters are not valid"],
    [{ status: 500, title: "Boom", detail: "Something broke", fieldErrors: {} }, "Something broke"],
    [{ status: 500, title: "Boom", fieldErrors: {} }, "Boom"],
  ] as const)("shows a failed search as an alert: %j", (partial, text) => {
    const failure: Failure = { ok: false, ...partial };
    renderApp(<ProductsView {...props({ page: null, failure })} />);

    expect(within(screen.getByRole("table")).getByRole("alert")).toHaveTextContent(text);
    expect(screen.queryByRole("navigation", { name: "Product pages" })).not.toBeInTheDocument();
  });

  it("shows a server error under the price field", () => {
    const failure: Failure = {
      ok: false,
      status: 422,
      title: "Validation failed",
      fieldErrors: { min_price: "must not be greater than max_price" },
    };
    renderApp(<ProductsView {...props({ page: null, failure })} />, { searchParams: "?min_price=50&max_price=10" });

    expect(screen.getByLabelText("Minimum price")).toHaveAccessibleDescription("must not be greater than max_price");
  });
});

describe("ProductsView URL state", () => {
  it("reads the filters from the URL and ignores invalid values", () => {
    renderApp(<ProductsView {...props()} />, {
      searchParams: "?q=shoes&category=sports&min_price=abc&max_price=99.50&in_stock=true&sort=newest&limit=7",
    });

    expect(screen.getByLabelText("Search")).toHaveValue("shoes");
    expect(screen.getByRole("combobox", { name: "Category" })).toHaveTextContent("Sports");
    expect(screen.getByLabelText("Minimum price")).toHaveValue("");
    expect(screen.getByLabelText("Maximum price")).toHaveValue("99.50");
    expect(screen.getByRole("combobox", { name: "Availability" })).toHaveTextContent("In stock only");
    expect(screen.getByRole("combobox", { name: "Sort by" })).toHaveTextContent("Newest first");
    expect(screen.getByRole("combobox", { name: "Results per page" })).toHaveTextContent("24 per page");
  });

  it("shows best match as the sort when searching and newest otherwise", () => {
    const { unmount } = renderApp(<ProductsView {...props()} />);
    expect(screen.getByRole("combobox", { name: "Sort by" })).toHaveTextContent("Newest first");
    unmount();

    renderApp(<ProductsView {...props()} />, { searchParams: "?q=shoes" });
    expect(screen.getByRole("combobox", { name: "Sort by" })).toHaveTextContent("Best match");
  });

  it("writes a changed category to the URL, clears the cursor and keeps other filters", async () => {
    const onUrlUpdate = jest.fn<void, [UrlUpdateEvent]>();
    const { user } = renderApp(<ProductsView {...props()} />, { searchParams: "?q=shoes&cursor=OLD", onUrlUpdate });

    await user.click(screen.getByRole("combobox", { name: "Category" }));
    await user.click(await screen.findByRole("option", { name: "Toys" }));

    await waitFor(() => {
      expect(onUrlUpdate).toHaveBeenCalled();
    });
    const params = lastUrl(onUrlUpdate);
    expect(params.get("category")).toBe("toys");
    expect(params.get("q")).toBe("shoes");
    expect(params.has("cursor")).toBe(false);
  });

  it("pushes a history entry per change, so back and forward restore each state", async () => {
    const onUrlUpdate = jest.fn<void, [UrlUpdateEvent]>();
    const { user } = renderApp(<ProductsView {...props()} />, { onUrlUpdate });

    await user.click(screen.getByRole("combobox", { name: "Availability" }));
    await user.click(await screen.findByRole("option", { name: "In stock only" }));

    await waitFor(() => {
      expect(onUrlUpdate).toHaveBeenCalled();
    });
    const event = onUrlUpdate.mock.lastCall?.[0];
    expect(event?.options.history).toBe("push");
    expect(event?.options.shallow).toBe(false);
  });

  it("does not write defaults: the sort that matches the implied one and the default page size", async () => {
    const onUrlUpdate = jest.fn<void, [UrlUpdateEvent]>();
    const { user } = renderApp(<ProductsView {...props()} />, { searchParams: "?sort=price_asc&limit=48", onUrlUpdate });

    await user.click(screen.getByRole("combobox", { name: "Sort by" }));
    await user.click(await screen.findByRole("option", { name: "Newest first" }));
    await waitFor(() => {
      expect(lastUrl(onUrlUpdate).has("sort")).toBe(false);
    });

    await user.click(screen.getByRole("combobox", { name: "Results per page" }));
    await user.click(await screen.findByRole("option", { name: "24 per page" }));
    await waitFor(() => {
      expect(lastUrl(onUrlUpdate).has("limit")).toBe(false);
    });
  });

  it("writes an explicit sort that differs from the implied one", async () => {
    const onUrlUpdate = jest.fn<void, [UrlUpdateEvent]>();
    const { user } = renderApp(<ProductsView {...props()} />, { searchParams: "?q=shoes", onUrlUpdate });

    await user.click(screen.getByRole("combobox", { name: "Sort by" }));
    await user.click(await screen.findByRole("option", { name: "Newest first" }));

    await waitFor(() => {
      expect(lastUrl(onUrlUpdate).get("sort")).toBe("newest");
    });
  });

  it("applies the search text to the URL 300 ms after the last keystroke and clears the cursor", async () => {
    jest.useFakeTimers();
    try {
      const onUrlUpdate = jest.fn<void, [UrlUpdateEvent]>();
      const { user } = renderApp(<ProductsView {...props()} />, { searchParams: "?cursor=OLD", onUrlUpdate, fakeTimers: true });

      await user.type(screen.getByLabelText("Search"), "boots");
      expect(screen.getByLabelText("Search")).toHaveValue("boots");
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
      expect(lastUrl(onUrlUpdate).get("q")).toBe("boots");
      expect(lastUrl(onUrlUpdate).has("cursor")).toBe(false);
    } finally {
      jest.useRealTimers();
    }
  });

  it("applies a valid price after the debounce and flags an invalid one without writing it", async () => {
    jest.useFakeTimers();
    try {
      const onUrlUpdate = jest.fn<void, [UrlUpdateEvent]>();
      const { user } = renderApp(<ProductsView {...props()} />, { onUrlUpdate, fakeTimers: true });

      await user.type(screen.getByLabelText("Minimum price"), "1x");
      expect(screen.getByLabelText("Minimum price")).toBeInvalid();
      expect(screen.getByLabelText("Minimum price")).toHaveAccessibleDescription("Enter a price like 19.99");
      act(() => {
        jest.advanceTimersByTime(1000);
      });
      expect(onUrlUpdate).not.toHaveBeenCalled();

      await user.clear(screen.getByLabelText("Minimum price"));
      await user.type(screen.getByLabelText("Minimum price"), "15.5");
      act(() => {
        jest.advanceTimersByTime(300);
      });

      await waitFor(() => {
        expect(lastUrl(onUrlUpdate).get("min_price")).toBe("15.5");
      });
    } finally {
      jest.useRealTimers();
    }
  });

  it("clears every filter at once", async () => {
    const onUrlUpdate = jest.fn<void, [UrlUpdateEvent]>();
    const { user } = renderApp(<ProductsView {...props()} />, {
      searchParams: "?q=shoes&category=sports&in_stock=true&sort=price_asc&limit=48&cursor=C",
      onUrlUpdate,
    });

    await user.click(screen.getByRole("button", { name: "Clear filters" }));

    await waitFor(() => {
      expect(onUrlUpdate).toHaveBeenCalled();
    });
    expect([...lastUrl(onUrlUpdate).keys()].sort()).toEqual(["limit"]);
    await waitFor(() => {
      expect(screen.getByLabelText("Search")).toHaveValue("");
    });
  });

  it("does not offer to clear when nothing is filtered", () => {
    renderApp(<ProductsView {...props()} />, { searchParams: "?sort=price_asc" });

    expect(screen.queryByRole("button", { name: "Clear filters" })).not.toBeInTheDocument();
  });

  it("keeps an unknown category slug from the URL selectable", () => {
    renderApp(<ProductsView {...props()} />, { searchParams: "?category=gadgets" });

    expect(screen.getByRole("combobox", { name: "Category" })).toHaveTextContent("gadgets");
  });
});

describe("ProductsView pagination", () => {
  it("moves to the next and previous pages through the cursor in the URL", async () => {
    const onUrlUpdate = jest.fn<void, [UrlUpdateEvent]>();
    const { user } = renderApp(<ProductsView {...props()} />, { searchParams: "?q=shoes", onUrlUpdate });

    await user.click(screen.getByRole("button", { name: "Next" }));
    await waitFor(() => {
      expect(lastUrl(onUrlUpdate).get("cursor")).toBe("NEXT");
    });
    expect(lastUrl(onUrlUpdate).get("q")).toBe("shoes");

    await user.click(screen.getByRole("button", { name: "Previous" }));
    await waitFor(() => {
      expect(lastUrl(onUrlUpdate).get("cursor")).toBe("PREV");
    });
  });

  it("disables the buttons that have nowhere to go", () => {
    renderApp(<ProductsView {...props({ page: { ...PAGE, next_cursor: null, prev_cursor: null } })} />);

    expect(screen.getByRole("button", { name: "Next" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Previous" })).toBeDisabled();
  });

  it("offers to go back to the first page when a pasted cursor does not match the filters", async () => {
    const onUrlUpdate = jest.fn<void, [UrlUpdateEvent]>();
    const failure: Failure = {
      ok: false,
      status: 422,
      title: "Validation failed",
      fieldErrors: { cursor: "does not match" },
    };
    const { user } = renderApp(<ProductsView {...props({ page: null, failure })} />, {
      searchParams: "?q=shoes&cursor=STALE",
      onUrlUpdate,
    });

    expect(within(screen.getByRole("table")).getByRole("alert")).toHaveTextContent("no longer matches");
    await user.click(screen.getByRole("button", { name: "Back to the first page" }));

    await waitFor(() => {
      expect(lastUrl(onUrlUpdate).has("cursor")).toBe(false);
    });
    expect(lastUrl(onUrlUpdate).get("q")).toBe("shoes");
  });
});

describe("ProductsView delete", () => {
  it("asks for confirmation, deletes with the version it saw and refreshes the list", async () => {
    const deleteProduct = jest.fn().mockResolvedValue({ ok: true });
    const { user } = renderApp(<ProductsView {...props({ deleteProduct })} />);

    await user.click(within(screen.getByRole("table")).getByRole("button", { name: "Delete Running shoes" }));
    expect(await screen.findByRole("dialog", { name: "Delete this product?" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Delete product" }));

    await waitFor(() => {
      expect(router.refresh).toHaveBeenCalledTimes(1);
    });
    expect(deleteProduct).toHaveBeenCalledWith("RS-001", '"3"');
    await waitFor(() => {
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    });
  });

  it("can be started from a card too, and cancelled", async () => {
    const deleteProduct = jest.fn();
    const { user } = renderApp(<ProductsView {...props({ deleteProduct })} />);

    await user.click(within(screen.getByRole("list", { name: "Product list" })).getByRole("button", { name: "Delete Toy robot" }));
    await user.click(await screen.findByRole("button", { name: "Cancel" }));

    expect(deleteProduct).not.toHaveBeenCalled();
    await waitFor(() => {
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    });
  });
});
