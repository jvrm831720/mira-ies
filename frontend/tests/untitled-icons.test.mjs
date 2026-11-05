import assert from "node:assert/strict";
import { readdirSync, readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import test from "node:test";

const root = join(dirname(fileURLToPath(import.meta.url)), "../src");
const iconsFile = join(root, "components/ui/icons.tsx");

function sourceFiles(folder) {
  return readdirSync(folder, { withFileTypes: true }).flatMap((entry) => {
    const path = join(folder, entry.name);
    if (entry.isDirectory()) return sourceFiles(path);
    return entry.name.endsWith(".ts") || entry.name.endsWith(".tsx") ? [path] : [];
  });
}

const sources = sourceFiles(root);
const exportsFile = readFileSync(iconsFile, "utf8");
const exported = new Set([
  "LucideIcon",
  ...[...exportsFile.matchAll(/export \{ (\w+)(?: as (\w+))? \} from ["']@untitledui\/icons["']/g)].map((match) => match[2] || match[1]),
]);

test("MIRA usa somente o adaptador Untitled UI Icons", () => {
  for (const path of sources) {
    const source = readFileSync(path, "utf8");
    assert.doesNotMatch(source, /from\s*["']lucide-react["']/, path);
    if (path !== iconsFile) assert.doesNotMatch(source, /from\s*["']@untitledui\/icons["']/, path);
  }
});

test("todos os ícones importados pela MIRA estão exportados pelo adaptador", () => {
  assert.ok(exported.size > 90, "adaptador sem conjunto completo de ícones");
  for (const path of sources) {
    if (path === iconsFile) continue;
    const source = readFileSync(path, "utf8");
    for (const match of source.matchAll(/import\s+(?:type\s+)?\{([^}]*)\}\s+from\s+["']@\/components\/ui\/icons["']/gs)) {
      for (const token of match[1].split(",")) {
        const symbol = token.trim().split(/\s+as\s+/)[0].trim().replace(/^type\s+/, "");
        if (symbol) assert.ok(exported.has(symbol), symbol + " não exportado para " + path);
      }
    }
  }
});
