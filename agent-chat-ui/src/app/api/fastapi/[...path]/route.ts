/**
 * FastAPI proxy route.
 *
 * Forwards all HTTP methods to the FastAPI backend, preserving headers and
 * body. SSE streams pass through transparently because the upstream Response
 * body (a ReadableStream) is returned directly.
 *
 * Configuration:
 *   FASTAPI_API_URL  — FastAPI base URL (default: http://localhost:8000)
 *                      Used server-side only; never exposed to the browser.
 */

const FASTAPI_URL =
  process.env.FASTAPI_API_URL ?? "http://localhost:8000";

export const runtime = "nodejs";

type RouteContext = { params: Promise<{ path: string[] }> };

async function proxyRequest(
  req: Request,
  context: RouteContext,
): Promise<Response> {
  const { path } = await context.params;
  const upstreamUrl = `${FASTAPI_URL}/${path.join("/")}`;

  const upstreamResponse = await fetch(upstreamUrl, {
    method: req.method,
    headers: req.headers,
    body: req.body,
    // Required for streaming request bodies (e.g. large POST payloads)
    // @ts-expect-error — duplex is not yet in the TypeScript fetch types
    duplex: "half",
  });

  return new Response(upstreamResponse.body, {
    status: upstreamResponse.status,
    headers: upstreamResponse.headers,
  });
}

export async function GET(req: Request, context: RouteContext) {
  return proxyRequest(req, context);
}

export async function POST(req: Request, context: RouteContext) {
  return proxyRequest(req, context);
}

export async function PUT(req: Request, context: RouteContext) {
  return proxyRequest(req, context);
}

export async function PATCH(req: Request, context: RouteContext) {
  return proxyRequest(req, context);
}

export async function DELETE(req: Request, context: RouteContext) {
  return proxyRequest(req, context);
}

export async function OPTIONS(req: Request, context: RouteContext) {
  return proxyRequest(req, context);
}
