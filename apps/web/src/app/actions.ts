"use server";

import { signOut, withAuth } from "@workos-inc/authkit-nextjs";
import { redirect } from "next/navigation";

import { responseMessage } from "@/lib/api";

const apiBaseUrl = process.env.API_INTERNAL_BASE_URL ?? "http://localhost:8000";

async function authorizedFetch(path: string, init: RequestInit): Promise<Response> {
  const { user, accessToken } = await withAuth({ ensureSignedIn: true });
  if (!user || !accessToken) redirect("/sign-in");
  const headers = new Headers(init.headers);
  headers.set("Authorization", `Bearer ${accessToken}`);
  if (init.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  return fetch(`${apiBaseUrl}/api/v1${path}`, { ...init, headers, cache: "no-store" });
}

function redirectWithError(path: string, message: string): never {
  redirect(`${path}?error=${encodeURIComponent(message)}`);
}

export async function createWorkspace(formData: FormData): Promise<void> {
  const name = String(formData.get("name") ?? "").trim();
  const response = await authorizedFetch("/workspaces", {
    method: "POST",
    body: JSON.stringify({ name }),
  });
  if (!response.ok) redirectWithError("/workspaces", await responseMessage(response));
  const workspace = (await response.json()) as { id: string };
  redirect(`/workspaces/${workspace.id}`);
}

export async function addMember(formData: FormData): Promise<void> {
  const workspaceId = String(formData.get("workspace_id") ?? "");
  const email = String(formData.get("email") ?? "").trim();
  const path = `/workspaces/${encodeURIComponent(workspaceId)}`;
  const response = await authorizedFetch(`${path}/members`, {
    method: "POST",
    body: JSON.stringify({ email }),
  });
  if (!response.ok) redirectWithError(path, await responseMessage(response));
  redirect(path);
}

export async function changeMemberRole(formData: FormData): Promise<void> {
  const workspaceId = String(formData.get("workspace_id") ?? "");
  const userId = String(formData.get("user_id") ?? "");
  const role = String(formData.get("role") ?? "MEMBER");
  const path = `/workspaces/${encodeURIComponent(workspaceId)}`;
  const response = await authorizedFetch(
    `/workspaces/${encodeURIComponent(workspaceId)}/members/${encodeURIComponent(userId)}`,
    { method: "PATCH", body: JSON.stringify({ role }) },
  );
  if (!response.ok) redirectWithError(path, await responseMessage(response));
  redirect(path);
}

export async function removeMember(formData: FormData): Promise<void> {
  const workspaceId = String(formData.get("workspace_id") ?? "");
  const userId = String(formData.get("user_id") ?? "");
  const path = `/workspaces/${encodeURIComponent(workspaceId)}`;
  const response = await authorizedFetch(
    `/workspaces/${encodeURIComponent(workspaceId)}/members/${encodeURIComponent(userId)}`,
    { method: "DELETE" },
  );
  if (!response.ok) redirectWithError(path, await responseMessage(response));
  redirect(path);
}

export async function signOutAction(): Promise<void> {
  await signOut();
}
