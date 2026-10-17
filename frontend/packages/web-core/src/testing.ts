import { waitFor } from "@testing-library/react";

const PENDING_SELECTOR = '[aria-busy="true"]';

export function pendingElements(root: ParentNode = document): Element[] {
  return [...root.querySelectorAll(PENDING_SELECTOR)];
}

export async function settled(root: ParentNode = document): Promise<void> {
  await waitFor(() => {
    const pending = pendingElements(root);
    if (pending.length > 0) {
      throw new Error(`still pending: ${pending.map((element) => element.outerHTML.slice(0, 80)).join(" | ")}`);
    }
  });
}
