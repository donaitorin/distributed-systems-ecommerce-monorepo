import { render } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactElement } from "react";
import { withNuqsTestingAdapter, type OnUrlUpdateFunction } from "nuqs/adapters/testing";

export type RenderOptions = {
  searchParams?: string | Record<string, string>;
  onUrlUpdate?: OnUrlUpdateFunction;
  fakeTimers?: boolean;
};

export function renderApp(ui: ReactElement, { searchParams, onUrlUpdate, fakeTimers = false }: RenderOptions = {}) {
  const Adapter = withNuqsTestingAdapter({ searchParams, onUrlUpdate, rateLimitFactor: 0, hasMemory: true });
  const user = userEvent.setup(fakeTimers ? { advanceTimers: jest.advanceTimersByTime } : {});
  const view = render(<Adapter>{ui}</Adapter>);
  return { user, ...view };
}
