import { nextRules, withoutTypescriptPlugin } from "@ecommerce/config/eslint";
import nextVitals from "eslint-config-next/core-web-vitals";

const config = [...withoutTypescriptPlugin(nextVitals), ...nextRules];

export default config;
