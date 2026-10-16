import { redirect } from "next/navigation";
import { failureFromError, type Failure } from "../lib/failure";
import { LOGIN_PATH } from "../lib/paths";

export async function guarded<Value>(work: () => Promise<Value>): Promise<Value | Failure> {
  let failure: Failure;
  try {
    return await work();
  } catch (error) {
    failure = failureFromError(error);
  }
  if (failure.status === 401) {
    redirect(`${LOGIN_PATH}?reason=expired`);
  }
  if (failure.status === 403) {
    redirect(`${LOGIN_PATH}?reason=forbidden`);
  }
  return failure;
}
