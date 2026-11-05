import { NextRequest, NextResponse } from "next/server";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const LOCAL_API = "http://localhost:8000";
const FORWARDED_REQUEST_HEADERS = [
  "accept",
  "authorization",
  "content-type",
  "idempotency-key",
  "x-api-key",
  "x-beacon-signature",
  "x-admin-secret",
] as const;
const FORWARDED_RESPONSE_HEADERS = ["content-type", "cache-control", "retry-after"] as const;

type RouteContext = { params: Promise<{ path: string[] }> };

function getApiBase(): string | null {
  const configured = process.env.MIRA_API_URL || process.env.NEXT_PUBLIC_API_URL;
  if (configured?.trim()) return configured.trim().replace(/\/+$/, "");
  return process.env.NODE_ENV === "development" ? LOCAL_API : null;
}

async function proxy(request: NextRequest, context: RouteContext): Promise<NextResponse> {
  const apiBase = getApiBase();
  if (!apiBase) {
    return NextResponse.json(
      { detail: "API não configurada. Defina MIRA_API_URL no ambiente do servidor." },
      { status: 503, headers: { "Cache-Control": "no-store" } },
    );
  }

  const { path } = await context.params;
  const isStudentPortal = path[0] === "student-portal";
  const encodedPath = path.map((segment) => encodeURIComponent(segment)).join("/");
  const target = new URL(`${apiBase}/api/v1/${encodedPath}`);
  target.search = request.nextUrl.search;

  const headers = new Headers();
  for (const name of FORWARDED_REQUEST_HEADERS) {
    const value = request.headers.get(name);
    if (value) headers.set(name, value);
  }
  // Only the isolated student-portal endpoints may receive portal cookies.
  // Never forward other browser cookies or a portal cookie to admin APIs.
  if (isStudentPortal) {
    const portalSession = request.cookies.get("mira_portal_session")?.value;
    if (portalSession) headers.set("cookie", "mira_portal_session=" + portalSession);
    const action = request.headers.get("x-mira-portal-action");
    if (action) headers.set("x-mira-portal-action", action);
  }

  const hasBody = !["GET", "HEAD"].includes(request.method);
  let upstream: Response;
  try {
    upstream = await fetch(target, {
      method: request.method,
      headers,
      body: hasBody ? await request.arrayBuffer() : undefined,
      cache: "no-store",
      redirect: "manual",
    });
  } catch {
    return NextResponse.json(
      { detail: "Não foi possível conectar à API. Verifique MIRA_API_URL e a disponibilidade do backend." },
      { status: 502, headers: { "Cache-Control": "no-store" } },
    );
  }

  const responseHeaders = new Headers();
  for (const name of FORWARDED_RESPONSE_HEADERS) {
    const value = upstream.headers.get(name);
    if (value) responseHeaders.set(name, value);
  }
  responseHeaders.set("Cache-Control", "no-store");
  // The FastAPI cookie is host-only; as the response originates from this
  // Next.js domain it becomes a first-party HttpOnly cookie on Vercel.
  if (isStudentPortal) {
    const sessionCookie = upstream.headers.get("set-cookie");
    if (sessionCookie) responseHeaders.set("set-cookie", sessionCookie);
  }

  const body = [204, 304].includes(upstream.status) ? null : await upstream.arrayBuffer();
  return new NextResponse(body, {
    status: upstream.status,
    headers: responseHeaders,
  });
}

export async function GET(request: NextRequest, context: RouteContext) {
  return proxy(request, context);
}

export async function HEAD(request: NextRequest, context: RouteContext) {
  return proxy(request, context);
}

export async function POST(request: NextRequest, context: RouteContext) {
  return proxy(request, context);
}

export async function PUT(request: NextRequest, context: RouteContext) {
  return proxy(request, context);
}

export async function PATCH(request: NextRequest, context: RouteContext) {
  return proxy(request, context);
}

export async function DELETE(request: NextRequest, context: RouteContext) {
  return proxy(request, context);
}
