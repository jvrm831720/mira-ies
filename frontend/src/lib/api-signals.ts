import { api as baseApi } from "./api";
import type { SignalsCatalogResponse, SignalsEvaluateResponse } from "@/types/signals";

/** Extensões de API da Sprint A (sinais) sem alterar o objeto api monolítico. */
async function requestSignals<T>(path: string): Promise<T> {
  // Reutiliza o mesmo transporte do cliente principal.
  return (baseApi as unknown as { baseUrl: string }) && signalsFetch<T>(path);
}

async function signalsFetch<T>(path: string): Promise<T> {
  const { getAccessToken, getApiKey, clearAuth } = await import("./auth");
  const BASE =
    process.env.NODE_ENV === "development"
      ? process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"
      : "";
  const token = getAccessToken();
  const key = getApiKey();
  const headers = new Headers();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  else if (key) headers.set("X-API-Key", key);

  const res = await fetch(`${BASE}${path}`, { headers });
  if (res.status === 401) {
    clearAuth();
    if (typeof window !== "undefined" && !window.location.pathname.startsWith("/login")) {
      window.location.href = "/login";
    }
    throw new Error("Sessão expirada ou não autorizada");
  }
  if (!res.ok) {
    let detail = `Erro ${res.status}`;
    try {
      const body = await res.json();
      detail = body.detail || body.message || detail;
    } catch {
      /* ignore */
    }
    throw new Error(String(detail));
  }
  return (await res.json()) as T;
}

export const signalsApi = {
  evaluate: (studentId: string) =>
    signalsFetch<SignalsEvaluateResponse>(
      `/api/v1/signals/evaluate?student_id=${encodeURIComponent(studentId)}`
    ),
  catalog: () => signalsFetch<SignalsCatalogResponse>("/api/v1/signals/catalog"),
};

// Augment the main api object for ergonomic use in components.
declare module "./api" {
  interface ApiSignals {
    signalsEvaluate: (studentId: string) => Promise<SignalsEvaluateResponse>;
    signalsCatalog: () => Promise<SignalsCatalogResponse>;
  }
}

export function attachSignalsApi(api: Record<string, unknown>) {
  api.signalsEvaluate = (studentId: string) => signalsApi.evaluate(studentId);
  api.signalsCatalog = () => signalsApi.catalog();
  return api;
}
