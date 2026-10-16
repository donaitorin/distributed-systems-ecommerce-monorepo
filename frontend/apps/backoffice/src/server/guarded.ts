import { redirect } from "next/navigation";
import { isFailure, settle, type Failure } from "@ecommerce/web-core";
import { LOGIN_PATH } from "../lib/paths";

export async function guarded<Value>(work: () => Promise<Value>): Promise<Value | Failure> {
  const result = await settle(work);
  if (!isFailure(result)) {
    return result;
  }
  if (result.status === 401) {
    redirect(`${LOGIN_PATH}?reason=expired`);
  }
  if (result.status === 403) {
    redirect(`${LOGIN_PATH}?reason=forbidden`);
  }
  return result;
}
