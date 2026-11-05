import { dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { FlatCompat } from "@eslint/eslintrc";
import { defineConfig, globalIgnores } from "eslint/config";

const compat = new FlatCompat({ baseDirectory: dirname(fileURLToPath(import.meta.url)) });

export default defineConfig([
  ...compat.extends("next/core-web-vitals"),
  globalIgnores([
    ".next/**",
    "node_modules/**",
    "next-env.d.ts",
    "out/**",
    "build/**",
    "coverage/**",
  ]),
  {
    files: ["src/**/*.{ts,tsx}"],
    ignores: ["src/components/ui/icons.tsx"],
    rules: {
      "no-restricted-imports": ["error", {
        paths: [
          { name: "lucide-react", message: "Use @/components/ui/icons (Untitled UI)." },
          { name: "@untitledui/icons", message: "Importe pelo adaptador @/components/ui/icons." },
        ],
      }],
    },
  },
]);
