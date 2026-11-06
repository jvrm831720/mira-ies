import assert from "node:assert/strict";
import { test } from "node:test";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../src");
const HEX = /#[0-9a-fA-F]{3,8}\b/g;
const RAW_TYPE = /text-\[\d+(?:\.\d+)?px\]/g;
const CSS_PX_FONT = /font-size:\s*\d+(?:\.\d+)?px\b/g;

function scan(folder) {
  return fs.readdirSync(folder, { withFileTypes: true }).flatMap(entry => {
    const target = path.join(folder, entry.name);
    if (entry.isDirectory()) return scan(target);
    return /\.(?:ts|tsx|css)$/.test(entry.name) ? [target] : [];
  });
}

test("frontend does not embed hex colors outside token declarations or arbitrary font sizes", () => {
  const violations = [];
  for (const file of scan(root)) {
    const relative = path.relative(root, file);
    const contents = fs.readFileSync(file, "utf8").split("\n");
    for (let index = 0; index < contents.length; index++) {
      const line = contents[index];
      const isTokenDeclaration = relative === "app/globals.css"
        && /^\s*--[\w-]+\s*:\s*#[\da-fA-F]{3,8}\s*;/.test(line);
      if (!isTokenDeclaration && HEX.test(line)) {
        violations.push(relative + ":" + (index + 1) + ": raw hex");
      }
      HEX.lastIndex = 0;
      if (RAW_TYPE.test(line)) violations.push(relative + ":" + (index + 1) + ": arbitrary font-size");
      RAW_TYPE.lastIndex = 0;
      if (relative === "app/globals.css" && !/^\s*--[\w-]+:/.test(line) && CSS_PX_FONT.test(line)) {
        violations.push(relative + ":" + (index + 1) + ": hardcoded CSS font-size");
      }
      CSS_PX_FONT.lastIndex = 0;
    }
  }
  assert.deepEqual(violations, [], "Move design literals into approved CSS tokens:\n" + violations.slice(0, 60).join("\n"));
});
