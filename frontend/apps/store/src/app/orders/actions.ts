"use server";

import { revalidatePath } from "next/cache";
import { getSession } from "@ecommerce/auth/next";

export async function refreshCartCountAction(): Promise<void> {
  if ((await getSession()) !== null) {
    revalidatePath("/", "layout");
  }
}
