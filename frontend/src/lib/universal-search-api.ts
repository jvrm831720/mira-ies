import { ApiError } from "./api";
import { getAccessToken } from "./auth";

export type SearchProvider = "students" | "collections" | "work" | "views" | "campaigns";
export type SearchMatch = "exact" | "prefix" | "contains" | "approximate";

export type UniversalSearchHit = {
  id: string;
  provider: SearchProvider;
  title: string;
  subtitle: string;
  href: string;
  rank: number;
  match: SearchMatch;
  action: "navigate";
};

export type UniversalSearchResponse = {
  query: string;
  results: UniversalSearchHit[];
  providers: SearchProvider[];
  unavailable: SearchProvider[];
  partial: boolean;
  count_scope: "bounded_matches";
  per_provider_limit: number;
};

const BASE = process.env.NODE_ENV === "development"
  ? process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000" : "";

/** Pure GET; a search result is never a mutation or critical-action command. */
export async function searchUniversal(query: string, signal?: AbortSignal):
  Promise<UniversalSearchResponse> {
  const q = query.trim();
  if (q.length < 2 || q.length > 80) throw new ApiError(422, "Informe 2 a 80 caracteres.");
  const token = getAccessToken();
  if (!token) throw new ApiError(401, "Sessão necessária para buscar registros.");
  let response: Response;
  try {
    response = await fetch(
      BASE + "/api/v1/search?q=" + encodeURIComponent(q) + "&per_provider=5",
      {
        method: "GET", headers: { Authorization: "Bearer " + token },
        cache: "no-store", signal,
      },
    );
  } catch (error) {
    if (signal?.aborted) throw error;
    throw new ApiError(0, "A busca não pôde se conectar ao servidor.");
  }
  if (!response.ok) {
    if (response.status === 401 || response.status === 403) {
      throw new ApiError(response.status, "Acesso à busca não autorizado.");
    }
    throw new ApiError(response.status, "A busca federada está temporariamente indisponível.");
  }
  const body = await response.json() as UniversalSearchResponse;
  // Only minimal navigational projections are accepted from the server.
  if (!Array.isArray(body.results) || !Array.isArray(body.providers) ||
      !Array.isArray(body.unavailable) || body.count_scope !== "bounded_matches") {
    throw new Error("A busca retornou um formato inesperado.");
  }
  return body;
}
