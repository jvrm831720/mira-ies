import type { NavigationGroup } from "@/components/layout/navigation";
import type { SearchHit, SearchCategory } from "./universal-search-api";

export type SearchPaletteEntry = {
  key: string;
  category: SearchCategory | "navigation";
  categoryLabel: string;
  title: string;
  detail: string;
  href: string;
  score: number;
};

export const CATEGORY_LABELS: Record<SearchCategory | "navigation", string> = {
  students: "Aluno", collections: "Caso financeiro", work: "Atividade humana",
  views: "Visualização", campaigns: "Campanha", navigation: "Navegação",
};
const UUID = "[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}";
const SAFE_ROUTES: Record<SearchCategory, RegExp> = {
  students: new RegExp("^/alunos/" + UUID + "$"),
  collections: new RegExp("^/cobranca/casos/" + UUID + "$"),
  work: new RegExp("^/trabalho\\?activity=" + UUID + "$"),
  views: new RegExp("^/(alunos|cobranca|campanhas)\\?saved_view=" + UUID + "$"),
  campaigns: new RegExp("^/campanhas\\?proposal=" + UUID + "$"),
};
const ROOT: Record<Exclude<SearchCategory, "views">, string> = {
  students: "/alunos", collections: "/cobranca", work: "/trabalho", campaigns: "/campanhas",
};

function normalize(value: string): string {
  return value.normalize("NFD").replace(/[\u0300-\u036f]/g, "")
    .toLocaleLowerCase("pt-BR").trim();
}

/** Bounded one-edit matcher used only for the small *authorized* navigation catalog. */
function oneEdit(a: string, b: string): boolean {
  if (Math.abs(a.length - b.length) > 1 || a.length < 3 || b.length < 3) return false;
  let edits = 0, i = 0, j = 0;
  while (i < a.length && j < b.length) {
    if (a[i] === b[j]) { i++; j++; continue; }
    if (++edits > 1) return false;
    if (a.length > b.length) i++;
    else if (b.length > a.length) j++;
    else { i++; j++; }
  }
  return edits + (a.length - i) + (b.length - j) <= 1;
}

export function navigationSearch(groups: NavigationGroup[], query: string): SearchPaletteEntry[] {
  const normalized = normalize(query);
  return groups.flatMap(group => group.items.flatMap(route => {
    const tokens = normalize([route.label, route.keywords || "", group.label].join(" ")).split(/\s+/);
    const words = normalized.split(/\s+/).filter(Boolean);
    const matched = !words.length || words.every(word =>
      tokens.some(token => token.includes(word) || oneEdit(word, token)));
    if (!matched) return [];
    return [{
      key: "navigation:" + route.href, category: "navigation" as const,
      categoryLabel: group.label, title: route.label, detail: "Abrir página · Somente navegação",
      href: route.href,
      score: !normalized ? 1 : normalize(route.label).includes(normalized) ? 3.5 : 1.5,
    }];
  })).slice(0, 18);
}

/** Safety net: even if a server provider regresses, don't link outside the
 * explicit record resolvers or the user's currently visible module routes. */
export function authorizedResults(
  hits: SearchHit[], groups: NavigationGroup[],
): SearchPaletteEntry[] {
  const available = new Set(groups.flatMap(group => group.items.map(item => item.href)));
  return hits.flatMap(hit => {
    const route = SAFE_ROUTES[hit.category];
    if (!route || !route.test(hit.href) || hit.kind !== "navigate") return [];
    const root = hit.category === "views"
      ? hit.href.split("?")[0]
      : ROOT[hit.category];
    if (!available.has(root)) return [];
    return [{
      key: hit.category + ":" + hit.id,
      category: hit.category,
      categoryLabel: CATEGORY_LABELS[hit.category],
      title: hit.title,
      detail: hit.subtitle,
      href: hit.href,
      score: Number.isFinite(hit.score) ? hit.score : 0,
    }];
  });
}

export function mergeSearchResults(
  remote: SearchHit[], groups: NavigationGroup[], query: string,
): SearchPaletteEntry[] {
  const candidates = [...authorizedResults(remote, groups), ...navigationSearch(groups, query)];
  const unique = new Map<string, SearchPaletteEntry>();
  for (const item of candidates) {
    if (!unique.has(item.href)) unique.set(item.href, item);
  }
  return [...unique.values()].sort((a, b) =>
    b.score - a.score || a.categoryLabel.localeCompare(b.categoryLabel, "pt-BR") ||
    a.title.localeCompare(b.title, "pt-BR") || a.key.localeCompare(b.key)
  ).slice(0, 36);
}
