import { withAuth } from "@workos-inc/authkit-nextjs";
import { NextRequest, NextResponse } from "next/server";

const apiBaseUrl = process.env.API_INTERNAL_BASE_URL ?? "http://localhost:8000";

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ workspaceId: string }> },
) {
  const { user, accessToken } = await withAuth({ ensureSignedIn: true });
  if (!user || !accessToken) {
    return NextResponse.json({ message: "Sign in to search this workspace." }, { status: 401 });
  }

  const { workspaceId } = await params;
  const upstream = await fetch(
    `${apiBaseUrl}/api/v1/workspaces/${encodeURIComponent(workspaceId)}/search`,
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${accessToken}`,
        "Content-Type": "application/json",
      },
      body: await request.text(),
      cache: "no-store",
    },
  );
  const body = await upstream.text();
  return new NextResponse(body, {
    status: upstream.status,
    headers: {
      "Content-Type": upstream.headers.get("content-type") ?? "application/json",
      "Cache-Control": "no-store",
    },
  });
}
