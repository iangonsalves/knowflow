import { getSignInUrl } from "@workos-inc/authkit-nextjs";
import { NextResponse } from "next/server";

export async function GET() {
  return NextResponse.redirect(await getSignInUrl({ returnTo: "/workspaces" }));
}
