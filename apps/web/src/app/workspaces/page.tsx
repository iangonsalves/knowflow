import Link from "next/link";

import { createWorkspace, signOutAction } from "@/app/actions";
import PendingSubmitButton from "@/app/components/PendingSubmitButton";
import { apiFetch } from "@/lib/api";

type Workspace = {
  id: string;
  name: string;
  slug: string;
  role: "OWNER" | "MEMBER";
  created_at: string;
};

type UserProfile = { id: string; email: string; display_name: string | null };

export default async function WorkspacesPage({
  searchParams,
}: {
  searchParams: Promise<{ error?: string }>;
}) {
  const [{ error }, meResponse, workspaceResponse] = await Promise.all([
    searchParams,
    apiFetch("/me"),
    apiFetch("/workspaces"),
  ]);
  const profile = meResponse.ok ? ((await meResponse.json()) as UserProfile) : null;
  const workspaces = workspaceResponse.ok ? ((await workspaceResponse.json()) as Workspace[]) : [];

  return (
    <main className="app-shell">
      <header className="topbar">
        <Link className="brand" href="/workspaces">KnowFlow</Link>
        <div className="user-menu">
          <span>{profile?.display_name || profile?.email || "Signed in"}</span>
          <form action={signOutAction}><button className="button button-quiet" type="submit">Sign out</button></form>
        </div>
      </header>
      <div className="content-wrap">
        <p className="eyebrow">Identity &amp; tenancy</p>
        <h1 className="page-title">Your workspaces</h1>
        <p className="page-intro">Workspace access is determined by your KnowFlow membership.</p>
        {error ? <p className="notice notice-error" role="alert">{error}</p> : null}
        {!meResponse.ok || !workspaceResponse.ok ? (
          <p className="notice notice-error" role="alert">Could not load your account. Check the API and WorkOS configuration.</p>
        ) : null}
        <section className="panel" aria-labelledby="workspace-list-title">
          <div className="panel-heading">
            <div><h2 id="workspace-list-title">Workspaces</h2><p>Only workspaces where you are a member appear here.</p></div>
          </div>
          {workspaces.length ? (
            <ul className="workspace-list">
              {workspaces.map((workspace) => (
                <li key={workspace.id}>
                  <Link href={`/workspaces/${workspace.id}`}>
                    <span className="workspace-name">{workspace.name}</span>
                    <span className="workspace-meta">{workspace.role === "OWNER" ? "Owner" : "Member"}</span>
                  </Link>
                </li>
              ))}
            </ul>
          ) : <p className="empty-state">You do not belong to a workspace yet.</p>}
        </section>
        <section className="panel create-panel" aria-labelledby="create-workspace-title">
          <div className="panel-heading">
            <div><h2 id="create-workspace-title">Create a workspace</h2><p>You will become its first Owner.</p></div>
          </div>
          <form action={createWorkspace} className="form-row">
            <label className="field-label" htmlFor="workspace-name">Workspace name</label>
            <div className="input-row">
              <input id="workspace-name" name="name" minLength={1} maxLength={120} required placeholder="Acme Technologies" />
              <PendingSubmitButton label="Create workspace" pendingLabel="Creating…" />
            </div>
          </form>
        </section>
      </div>
    </main>
  );
}
