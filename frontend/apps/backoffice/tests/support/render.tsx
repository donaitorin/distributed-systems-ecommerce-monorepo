import { render } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactElement } from "react";
import { withNuqsTestingAdapter, type OnUrlUpdateFunction } from "nuqs/adapters/testing";
import { NavigationContext } from "@ecommerce/web-core/client";
import { NotificationsProvider } from "../../src/components/notifications";
import { router } from "./navigation-mock";

export type RenderOptions = {
  searchParams?: string | Record<string, string>;
  onUrlUpdate?: OnUrlUpdateFunction;
  fakeTimers?: boolean;
};

export function renderApp(ui: ReactElement, { searchParams, onUrlUpdate, fakeTimers = false }: RenderOptions = {}) {
  const Adapter = withNuqsTestingAdapter({ searchParams, onUrlUpdate, rateLimitFactor: 0, hasMemory: true });
  const user = userEvent.setup(fakeTimers ? { advanceTimers: jest.advanceTimersByTime } : {});
  const view = render(
    <Adapter>
      <NavigationContext value={{ push: router.push, refresh: router.refresh }}>
        <NotificationsProvider>{ui}</NotificationsProvider>
      </NavigationContext>
    </Adapter>,
  );
  return { user, ...view };
}
