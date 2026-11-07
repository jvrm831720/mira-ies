import type { UniversalSearchHit } from "./universal-search-api";

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const SEARCH_PROVIDERS = new Set(["students", "collections", "work", "views", "campaigns"]);

/** Navigation-only allowlist, also checked against workspace-visible sidebar routes. */
export function safeSearchDestination(hit: UniversalSearchHit, permittedRoots: string[]): boolean {
  if (!hit || hit.action !== "navigate" || typeof hit.href !== "string" ||
      !hit.href.startsWith("/") || hit.href.startsWith("//") || hit.href.length > 1200) return false;
  let url: URL;
  try { url = new URL(hit.href, "https://mira.invalid"); } catch { return false; }
  if (url.origin !== "https://mira.invalid" || url.hash || !SEARCH_PROVIDERS.has(hit.provider)) return false;
  const params = [...url.searchParams.keys()];
  const p = url.pathname;
  let root: string;
  if (hit.provider === "students") {
    root = "/alunos";
    if (!p.startsWith(root + "/") || !UUID.test(p.slice(root.length + 1)) || params.length) return false;
  } else if (hit.provider === "collections") {
    root = "/cobranca";
    if (!p.startsWith("/cobranca/casos/") || !UUID.test(p.slice(16)) || params.length) return false;
  } else if (hit.provider === "work") {
    root = "/trabalho";
    if (p !== root || params.length !== 1 || params[0] !== "activity" ||
        !UUID.test(url.searchParams.get("activity") || "")) return false;
  } else if (hit.provider === "views") {
    root = p;
    if (!["/alunos", "/cobranca", "/campanhas", "/academico"].includes(root) ||
        params.length !== 1 || params[0] !== "saved_view" ||
        !UUID.test(url.searchParams.get("saved_view") || "")) return false;
  } else {
    root = "/campanhas";
    if (p !== root || params.length) return false;
  }
  return permittedRoots.includes(root);
}
