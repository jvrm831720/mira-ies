import { NextRequest, NextResponse } from "next/server";

function getApiBase(): string | null {
  const configured = process.env.MIRA_API_URL || process.env.NEXT_PUBLIC_API_URL;
  if (configured?.trim()) return configured.trim().replace(/\\/+$/, "");
  return process.env.NODE_ENV === "development" ? "http://localhost:8000" : null;
}
const COOKIE_NAME = "mira_control_center_session";

type RouteContext = { params: Promise<{ path: string[] }> };

export async function GET(request: NextRequest, context: RouteContext) {
  const apiBase = getApiBase();
  if (!apiBase) {
    return NextResponse.json({ detail: "API não configurada. Defina MIRA_API_URL no ambiente do servidor." }, { status: 503, headers: { "Cache-Control": "no-store" } });
  }
  const token = request.cookies.get(COOKIE_NAME)?.value;
  if (!token) {
    return NextResponse.json({ detail: "Sessão administrativa ausente ou expirada." }, { status: 401, headers: { "Cache-Control": "no-store" } });
  }

  const { path: segments } = await context.params;
  const encodedPath = segments.map((part) => encodeURIComponent(part)).join("/");
  const target = new URL(`${apiBase}/api/v1/admin/mira-governance/${encodedPath}`);
  target.search = request.nextUrl.search;

  let upstream: Response;
  try {
    upstream = await fetch(target, {
      method: "GET",
      headers: { Accept: "application/json", Authorization: `Bearer ${token}` },
      cache: "no-store",
    });
  } catch {
    return NextResponse.json({ detail: "Não foi possível conectar à API administrativa." }, { status: 502, headers: { "Cache-Control": "no-store" } });
  }

  const payload = await upstream.json().catch(() => ({}));
  const response = NextResponse.json(payload, { status: upstream.status, headers: { "Cache-Control": "no-store" } });
  if (upstream.status === 401) {
    response.cookies.set(COOKIE_NAME, "", {
      httpOnly: true,
      secure: process.env.NODE_ENV === "production",
      sameSite: "lax",
      path: "/",
      maxAge: 0,
    });
  }
  return response;
}
