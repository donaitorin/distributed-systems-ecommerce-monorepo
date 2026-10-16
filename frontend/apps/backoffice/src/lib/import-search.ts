import "./zod-config";
import { z } from "zod";
import { zodParser } from "./zod-parser";

export const importUrlParser = zodParser(z.uuid());
