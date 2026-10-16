import js from "@eslint/js";
import jsxA11y from "eslint-plugin-jsx-a11y";
import reactHooks from "eslint-plugin-react-hooks";
import storybook from "eslint-plugin-storybook";
import globals from "globals";
import tseslint from "typescript-eslint";

const IGNORED = [
  "**/node_modules/**",
  "**/.next/**",
  "**/.turbo/**",
  "**/coverage/**",
  "**/dist/**",
  "**/storybook-static/**",
  "**/next-env.d.ts",
];

const ARBITRARY_VALUE =
  "(?:^|\\s)(?!(?:group-|peer-)?(?:data|aria)-)[a-z][a-z0-9]*(?:-[a-z0-9]+)*-\\[";

const stylingRules = {
  "no-restricted-syntax": [
    "error",
    {
      selector: "JSXAttribute[name.name='style']",
      message: "Inline style objects are not allowed. Use Tailwind token classes.",
    },
    {
      selector: `Literal[value=/${ARBITRARY_VALUE}/]`,
      message: "Arbitrary Tailwind values are not allowed. Add a token to the shared theme.",
    },
    {
      selector: `TemplateElement[value.raw=/${ARBITRARY_VALUE}/]`,
      message: "Arbitrary Tailwind values are not allowed. Add a token to the shared theme.",
    },
  ],
};

export const base = tseslint.config(
  { ignores: IGNORED },
  js.configs.recommended,
  ...tseslint.configs.recommendedTypeChecked,
  {
    languageOptions: {
      parserOptions: { projectService: true },
    },
    rules: {
      "@typescript-eslint/consistent-type-imports": "error",
      "@typescript-eslint/no-floating-promises": "error",
      "@typescript-eslint/ban-ts-comment": [
        "error",
        { "ts-expect-error": "allow-with-description", minimumDescriptionLength: 5 },
      ],
    },
  },
  {
    files: ["**/*.{test,spec}.{ts,tsx,cjs,mjs}", "**/jest/setup.cjs"],
    languageOptions: { globals: globals.jest },
  },
  {
    files: ["**/*.cjs"],
    rules: { "@typescript-eslint/no-require-imports": "off" },
  },
  {
    files: ["**/*.{js,cjs,mjs}"],
    ...tseslint.configs.disableTypeChecked,
  },
  {
    files: ["**/*.{js,cjs,mjs}"],
    languageOptions: { globals: globals.node },
  },
);

export function withoutTypescriptPlugin(configs) {
  return configs.map((config) => {
    if (!config.plugins?.["@typescript-eslint"]) {
      return config;
    }
    const plugins = Object.fromEntries(
      Object.entries(config.plugins).filter(([name]) => name !== "@typescript-eslint"),
    );
    return { ...config, plugins };
  });
}

export const nextRules = tseslint.config(
  ...base,
  {
    files: ["**/*.{ts,tsx}"],
    rules: {
      ...jsxA11y.flatConfigs.strict.rules,
      ...reactHooks.configs.flat["recommended-latest"].rules,
    },
  },
  { files: ["**/*.{ts,tsx}"], languageOptions: { globals: globals.browser }, rules: stylingRules },
  {
    files: ["**/*.test.{ts,tsx}", "**/*.stories.{ts,tsx}"],
    rules: { "no-restricted-syntax": "off" },
  },
);

export const react = tseslint.config(
  ...base,
  jsxA11y.flatConfigs.strict,
  reactHooks.configs.flat["recommended-latest"],
  {
    files: ["**/*.{ts,tsx}"],
    languageOptions: { globals: globals.browser },
    rules: stylingRules,
  },
  {
    files: ["**/*.test.{ts,tsx}", "**/*.stories.{ts,tsx}", "**/.storybook/**"],
    rules: {
      "no-restricted-syntax": "off",
    },
  },
  ...storybook.configs["flat/recommended"],
);

export default base;
