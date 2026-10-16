"use server";

import { signOut } from "@ecommerce/auth/next";
import { redirect } from "next/navigation";
import { LOGIN_PATH } from "../lib/paths";

export async function signOutAction(): Promise<void> {
  await signOut().catch(() => undefined);
  redirect(LOGIN_PATH);
}
