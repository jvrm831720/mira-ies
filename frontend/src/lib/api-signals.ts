import { clearAuth, getAccessToken, getApiKey } from "./auth";
import type { SignalsCatalogResponse, SignalsEvaluateResponse } from "@/types/signals";

const BASE =
  process.env.NODE_ENV === "development"
    ? process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"
    : "";

async function signalsFetch<T>(path: string): Promise<T> {
  const token = getAccessToken();
  const key = getApiKey();
  const headers = new Headers();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  else if (key) headers.set("X-API-Key", key);

  let res: Response;
  try {
    res = await fetch(`${BASE}${path}`, { headers });
  } catch {
    throw new Error("Falha de rede ao falar com o servidor");
  }

  if (res.status === 401) {
    clearAuth();
    if (
      typeof window !== "undefined" &&
      !window.location.pathname.startsWith("/login")
    ) {
      window.location.href = "/login";
    }
    throw new Error("Sessão expirada ou não autorizada");
  }

  if (!res.ok) {
    let detail = `Erro ${res.status}`;
    try {
      const body = await res.json();
      detail = body.detail || body.message || detail;
      if (Array.isArray(detail)) {
        detail = detail
          .map((d: { msg?: string }) => d.msg || JSON.stringify(d))
          .join(", ");
      }
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
  catalog: () =>
    signalsFetch<SignalsCatalogResponse>("/api/v1/signals/catalog"),
};
