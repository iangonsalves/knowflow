import tseslint from "typescript-eslint";

const eslintConfig = tseslint.config(
  { ignores: ["**/.next/**", "**/node_modules/**", "**/out/**", "**/coverage/**"] },
  ...tseslint.configs.recommended,
);

export default eslintConfig;
