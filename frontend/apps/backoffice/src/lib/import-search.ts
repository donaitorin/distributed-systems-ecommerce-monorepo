import "@ecommerce/web-core/zod-config";
import { z } from "zod";
import { zodParser } from "@ecommerce/web-core";

export const importUrlParser = zodParser(z.uuid());
