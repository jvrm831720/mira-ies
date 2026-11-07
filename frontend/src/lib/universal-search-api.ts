import { ApiError } from "./api";
import { getAccessToken } from "./auth";

export type SearchCategory = "students" | "collections" | "work" | "views" | "campaigns";
export type SearchHit = {
  category: SearchCategory;
  id: string;
  title: string;
  subtitle: string;
  href: string;
  score: number;
  kind: "navigate";
};
export type SearchProviderStatus = { status: "ok" | "unavailable"; returned: number };
export type UniversalSearchResponse = {
  query: string;
  results: SearchHit[];
  providers: Partial<Record<SearchCategory, SearchProviderStatus>>;
  partial: boolean;
  as_of: string;
  returned: number;
  limit_per_provider: number;
  count_scope: "bounded_matches_only";
  navigation_provider: "client_permission_filtered";
  actions_executed: false;
};

const BASE = process.env.NODE_ENV === "development"
  ? process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000" : "";

/** Human-session only; never fall back to a long-lived service/API key. */
export async function universalSearch(
  query: string, signal?: AbortSignal,
): Promise<UniversalSearchResponse> {
  const token = getAccessToken();
  if (!token) throw new ApiError(401, "Sessão de usuário não disponível.");
  const q = query.trim().slice(0, 80);
  if (q.length < 2) throw new Error("Digite ao menos dois caracteres.");
  let response: Response;
  try {
    response = await fetch(BASE + "/api/v1/search/universal?q=" + encodeURIComponent(q) + "&limit=5", {
      method: "GET",
      headers: { Authorization: "Bearer " + token, Accept: "application/json" },
      cache: "no-store",
      signal,
    });
  } catch (error) {
    if (signal?.aborted) throw error;
    throw new ApiError(0, "Busca temporariamente indisponível.");
  }
  if (!response.ok) {
    throw new ApiError(response.status, response.status === 403
      ? "Você não tem acesso à busca deste workspace."
      : "Não foi possível consultar os registros. Páginas autorizadas permanecem acessíveis.");
  }
  return response.json() as Promise<UniversalSearchResponse>;
}
