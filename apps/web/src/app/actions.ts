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
  if (init.body && !(init.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  try {
    return await fetch(`${apiBaseUrl}/api/v1${path}`, { ...init, headers, cache: "no-store" });
  } catch {
    return Response.json(
      { error: { code: "service_unavailable", message: "KnowFlow is temporarily unavailable. Try again shortly." } },
      { status: 503 },
    );
  }
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
  const path = `/workspaces/${encodeURIComponent(workspaceId)}/members`;
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
  const path = `/workspaces/${encodeURIComponent(workspaceId)}/members`;
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
  const path = `/workspaces/${encodeURIComponent(workspaceId)}/members`;
  const response = await authorizedFetch(
    `/workspaces/${encodeURIComponent(workspaceId)}/members/${encodeURIComponent(userId)}`,
    { method: "DELETE" },
  );
  if (!response.ok) redirectWithError(path, await responseMessage(response));
  redirect(path);
}

export async function createKnowledgeArea(formData: FormData): Promise<void> {
  const workspaceId = String(formData.get("workspace_id") ?? "");
  const path = `/workspaces/${encodeURIComponent(workspaceId)}`;
  const response = await authorizedFetch(`${path}/knowledge-areas`, {
    method: "POST",
    body: JSON.stringify({
      name: String(formData.get("name") ?? "").trim(),
      description: String(formData.get("description") ?? "").trim() || null,
    }),
  });
  if (!response.ok) redirectWithError(`${path}/knowledge-areas`, await responseMessage(response));
  redirect(`${path}/knowledge-areas`);
}

export async function updateKnowledgeArea(formData: FormData): Promise<void> {
  const workspaceId = String(formData.get("workspace_id") ?? "");
  const areaId = String(formData.get("area_id") ?? "");
  const path = `/workspaces/${encodeURIComponent(workspaceId)}/knowledge-areas`;
  const response = await authorizedFetch(`${path}/${encodeURIComponent(areaId)}`, {
    method: "PATCH",
    body: JSON.stringify({
      name: String(formData.get("name") ?? "").trim(),
      description: String(formData.get("description") ?? "").trim() || null,
    }),
  });
  if (!response.ok) redirectWithError(path, await responseMessage(response));
  redirect(path);
}

export async function deleteKnowledgeArea(formData: FormData): Promise<void> {
  const workspaceId = String(formData.get("workspace_id") ?? "");
  const areaId = String(formData.get("area_id") ?? "");
  const path = `/workspaces/${encodeURIComponent(workspaceId)}/knowledge-areas`;
  const response = await authorizedFetch(`${path}/${encodeURIComponent(areaId)}`, {
    method: "DELETE",
  });
  if (!response.ok) redirectWithError(path, await responseMessage(response));
  redirect(path);
}

export async function uploadDocument(formData: FormData): Promise<void> {
  const workspaceId = String(formData.get("workspace_id") ?? "");
  const path = `/workspaces/${encodeURIComponent(workspaceId)}/documents`;
  const body = new FormData();
  body.set("knowledge_area_id", String(formData.get("knowledge_area_id") ?? ""));
  const file = formData.get("file");
  if (file instanceof File) body.set("file", file);
  const response = await authorizedFetch(path, { method: "POST", body });
  if (!response.ok) redirectWithError(path, await responseMessage(response));
  redirect(path);
}

export async function deleteDocument(formData: FormData): Promise<void> {
  const workspaceId = String(formData.get("workspace_id") ?? "");
  const documentId = String(formData.get("document_id") ?? "");
  const path = `/workspaces/${encodeURIComponent(workspaceId)}/documents`;
  const response = await authorizedFetch(`${path}/${encodeURIComponent(documentId)}`, {
    method: "DELETE",
  });
  if (!response.ok) redirectWithError(path, await responseMessage(response));
  redirect(path);
}

export async function retryDocument(formData: FormData): Promise<void> {
  const workspaceId = String(formData.get("workspace_id") ?? "");
  const documentId = String(formData.get("document_id") ?? "");
  const path = `/workspaces/${encodeURIComponent(workspaceId)}/documents`;
  const response = await authorizedFetch(
    `${path}/${encodeURIComponent(documentId)}/retry`,
    { method: "POST" },
  );
  if (!response.ok) redirectWithError(path, await responseMessage(response));
  redirect(path);
}

export async function signOutAction(): Promise<void> {
  await signOut();
}
