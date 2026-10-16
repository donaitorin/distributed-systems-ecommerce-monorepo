import "./zod-config";
import { createParser } from "nuqs/server";
import type { ZodType } from "zod";

export function zodParser<Output>(schema: ZodType<Output>, serialize: (value: Output) => string = String) {
  return createParser<Output>({
    parse: (value) => {
      const result = schema.safeParse(value);
      return result.success ? result.data : null;
    },
    serialize,
  });
}
