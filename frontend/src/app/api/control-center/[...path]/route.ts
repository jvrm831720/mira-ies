import { NextRequest, NextResponse } from "next/server";

const API_BASE = (process.env.MIRA_API_URL || process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/+$/, "");
const COOKIE_NAME = "mira_control_center_session";
const SESSION_TTL_SECONDS = 20 * 60;

type RouteContext = { params: Promise<{ path: string[] }> };

async function proxy(request: NextRequest, context: RouteContext): Promise<NextResponse> {
  const origin = request.headers.get("origin");
  if (request.method !== "GET" && request.method !== "HEAD" && origin !== request.nextUrl.origin) {
    return NextResponse.json({ detail: "Origem da requisição não autorizada." }, { status: 403 });
  }

  const { path: segments } = await context.params;
  const path = segments.join("/");

  if (request.method === "POST" && path === "auth/logout") {
    const response = NextResponse.json({ ok: true });
    response.cookies.set(COOKIE_NAME, "", {
      httpOnly: true,
      secure: process.env.NODE_ENV === "production",
      sameSite: "lax",
      path: "/",
      maxAge: 0,
    });
    return response;
  }

  const isLogin = request.method === "POST" && path === "auth/login";
  const isVerify = request.method === "POST" && path === "auth/verify";
  const token = request.cookies.get(COOKIE_NAME)?.value;

  if (!isLogin && !isVerify && !token) {
    return NextResponse.json({ detail: "Sessão administrativa ausente ou expirada." }, { status: 401 });
  }

  const encodedPath = segments.map((part) => encodeURIComponent(part)).join("/");
  const target = new URL(`${API_BASE}/api/v1/admin/control-center/${encodedPath}`);
  target.search = request.nextUrl.search;

  const headers = new Headers({ Accept: "application/json" });
  const contentType = request.headers.get("content-type");
  if (contentType) headers.set("Content-Type", contentType);
  if (!isLogin && !isVerify && token) headers.set("Authorization", `Bearer ${token}`);

  let body: string | undefined;
  if (request.method !== "GET" && request.method !== "HEAD") body = await request.text();

  let upstream: Response;
  try {
    upstream = await fetch(target, { method: request.method, headers, body, cache: "no-store" });
  } catch {
    return NextResponse.json({ detail: "Não foi possível conectar à API administrativa." }, { status: 502 });
  }

  const payload = await upstream.json().catch(() => ({})) as Record<string, unknown>;
  if (!upstream.ok) {
    const response = NextResponse.json(payload, { status: upstream.status });
    if (upstream.status === 401 && !isLogin && !isVerify) {
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

  if (isVerify) {
    const accessToken = payload.access_token;
    if (typeof accessToken !== "string" || !accessToken) {
      return NextResponse.json({ detail: "A API não retornou uma sessão administrativa válida." }, { status: 502 });
    }
    const safePayload = { ...payload };
    delete safePayload.access_token;
    const response = NextResponse.json(safePayload, { status: upstream.status });
    const expiresIn = typeof payload.expires_in === "number" ? payload.expires_in : SESSION_TTL_SECONDS;
    response.cookies.set(COOKIE_NAME, accessToken, {
      httpOnly: true,
      secure: process.env.NODE_ENV === "production",
      sameSite: "lax",
      path: "/",
      maxAge: Math.min(expiresIn, SESSION_TTL_SECONDS),
    });
    return response;
  }

  return NextResponse.json(payload, { status: upstream.status });
}

export async function GET(request: NextRequest, context: RouteContext) {
  return proxy(request, context);
}
export async function POST(request: NextRequest, context: RouteContext) {
  return proxy(request, context);
}
export async function PATCH(request: NextRequest, context: RouteContext) {
  return proxy(request, context);
}
