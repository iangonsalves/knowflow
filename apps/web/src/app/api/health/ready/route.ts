const apiBaseUrl = process.env.API_INTERNAL_BASE_URL ?? "http://localhost:8000";

export const dynamic = "force-dynamic";

export async function GET(): Promise<Response> {
  try {
    const response = await fetch(`${apiBaseUrl}/health/ready`, {
      cache: "no-store",
      signal: AbortSignal.timeout(8_000),
    });
    if (response.ok) {
      return Response.json(
        { status: "ready" },
        { headers: { "Cache-Control": "no-store" } },
      );
    }
  } catch {
    // A sleeping or booting free backend is expected; expose only a safe state.
  }

  return Response.json(
    { status: "starting" },
    { status: 503, headers: { "Cache-Control": "no-store", "Retry-After": "5" } },
  );
}
