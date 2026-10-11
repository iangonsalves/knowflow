import "server-only";

import { withAuth } from "@workos-inc/authkit-nextjs";
import { redirect } from "next/navigation";

const apiBaseUrl = process.env.API_INTERNAL_BASE_URL ?? "http://localhost:8000";

export async function apiFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const { user, accessToken } = await withAuth();
  if (!user || !accessToken) redirect("/sign-in");

  const headers = new Headers(init.headers);
  headers.set("Authorization", `Bearer ${accessToken}`);
  if (init.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  return fetch(`${apiBaseUrl}/api/v1${path}`, {
    ...init,
    headers,
    cache: "no-store",
  });
}

export async function responseMessage(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as { error?: { message?: string } };
    return body.error?.message ?? "The request could not be completed.";
  } catch {
    return "The request could not be completed.";
  }
}
