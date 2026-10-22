import type { NextRequest } from "next/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const FORWARDED_REQUEST_HEADERS = [
  "accept",
  "authorization",
  "content-type",
  "idempotency-key",
  "x-api-key",
  "x-admin-secret",
  "x-correlation-id",
];
const HOP_BY_HOP_HEADERS = new Set([
  "connection",
  "content-encoding",
  "keep-alive",
  "proxy-authenticate",
  "proxy-authorization",
  "te",
  "trailer",
  "transfer-encoding",
  "upgrade",
]);

async function proxy(request: NextRequest): Promise<Response> {
  const configuredOrigin = process.env.BACKEND_API_URL?.trim();
  if (!configuredOrigin) {
    return Response.json(
      { detail: "A API ainda não está configurada neste ambiente." },
      { status: 503 },
    );
  }

  const origin = configuredOrigin.startsWith("http")
    ? configuredOrigin
    : `http://${configuredOrigin}`;
  const target = new URL(`${request.nextUrl.pathname}${request.nextUrl.search}`, `${origin}/`);
  const headers = new Headers();
  for (const name of FORWARDED_REQUEST_HEADERS) {
    const value = request.headers.get(name);
    if (value) headers.set(name, value);
  }

  const method = request.method.toUpperCase();
  const body = method === "GET" || method === "HEAD"
    ? undefined
    : Buffer.from(await request.arrayBuffer());
  const upstream = await fetch(target, {
    method,
    headers,
    body,
    cache: "no-store",
    redirect: "manual",
  });
  const responseHeaders = new Headers();
  upstream.headers.forEach((value, name) => {
    if (!HOP_BY_HOP_HEADERS.has(name.toLowerCase())) responseHeaders.set(name, value);
  });

  return new Response(upstream.body, {
    status: upstream.status,
    statusText: upstream.statusText,
    headers: responseHeaders,
  });
}

export const GET = proxy;
export const POST = proxy;
export const PUT = proxy;
export const PATCH = proxy;
export const DELETE = proxy;
export const HEAD = proxy;
