import nextCoreWebVitals from "eslint-config-next/core-web-vitals";
import nextTypescript from "eslint-config-next/typescript";

const eslintConfig = [...nextCoreWebVitals, ...nextTypescript, {
  rules: {
    // ─── TypeScript: REGLAS ACTIVAS ─────────────────────────────────
    "@typescript-eslint/no-explicit-any": "warn",
    "@typescript-eslint/no-unused-vars": ["warn", {
      argsIgnorePattern: "^_",
      varsIgnorePattern: "^_",
    }],
    "@typescript-eslint/no-non-null-assertion": "warn",
    "@typescript-eslint/ban-ts-comment": "warn",
    "@typescript-eslint/prefer-as-const": "warn",
    "@typescript-eslint/no-unused-disable-directive": "warn",

    // ─── React: REGLAS ACTIVAS ──────────────────────────────────────
    // CRÍTICO: Esta regla detecta closures stale y bugs de estado.
    // Si genera warnings falsos, usar la directiva:
    // // eslint-disable-next-line react-hooks/exhaustive-deps
    // con comentario explicando por qué.
    "react-hooks/exhaustive-deps": "warn",
    "react-hooks/purity": "warn",
    "react/no-unescaped-entities": "off",
    "react/display-name": "off",
    "react/prop-types": "off",
    "react-compiler/react-compiler": "off",

    // ─── Next.js: REGLAS ACTIVAS ────────────────────────────────────
    "@next/next/no-img-element": "warn",
    "@next/next/no-html-link-for-pages": "off",

    // ─── General: REGLAS ACTIVAS ────────────────────────────────────
    "prefer-const": "warn",
    "no-unused-vars": "off",
    "no-console": ["warn", { allow: ["warn", "error"] }],
    "no-debugger": "error",
    "no-empty": "warn",
    "no-irregular-whitespace": "warn",
    "no-case-declarations": "off",
    "no-fallthrough": "warn",
    "no-mixed-spaces-and-tabs": "error",
    "no-redeclare": "error",
    "no-undef": "off",
    "no-unreachable": "warn",
    "no-useless-escape": "warn",
  },
}, {
  ignores: [
    "node_modules/**",
    ".next/**",
    "out/**",
    "build/**",
    "next-env.d.ts",
    "api/**",
    "policy-engine/**",
    "playbooks/**",
    "mcp-gateway/**",
    "hitl/**",
    "observability/**",
    "services/**",
    "rust-engine/**",
    "skills/**",
    "prisma/**",
  ],
}];

export default eslintConfig;
