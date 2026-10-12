import { withAuth } from "@workos-inc/authkit-nextjs";
import { NextRequest, NextResponse } from "next/server";

const apiBaseUrl = process.env.API_INTERNAL_BASE_URL ?? "http://localhost:8000";

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ workspaceId: string; documentId: string }> },
) {
  const { user, accessToken } = await withAuth({ ensureSignedIn: true });
  if (!user || !accessToken) return NextResponse.redirect(new URL("/sign-in", request.url));

  const { workspaceId, documentId } = await params;
  const upstreamUrl = new URL(
    `/api/v1/workspaces/${encodeURIComponent(workspaceId)}/documents/${encodeURIComponent(documentId)}/content`,
    apiBaseUrl,
  );
  const download = request.nextUrl.searchParams.get("download");
  if (download === "true") upstreamUrl.searchParams.set("download", "true");

  const upstream = await fetch(upstreamUrl, {
    headers: { Authorization: `Bearer ${accessToken}` },
    cache: "no-store",
  });
  const headers = new Headers();
  for (const name of ["content-type", "content-length", "content-disposition", "cache-control", "x-content-type-options"]) {
    const value = upstream.headers.get(name);
    if (value) headers.set(name, value);
  }
  return new NextResponse(upstream.body, { status: upstream.status, headers });
}
