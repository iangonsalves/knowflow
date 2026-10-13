import Link from "next/link";
import { notFound } from "next/navigation";

import { addMember, changeMemberRole, removeMember, signOutAction } from "@/app/actions";
import { apiFetch } from "@/lib/api";

type Workspace = {
  id: string;
  name: string;
  slug: string;
  role: "OWNER" | "MEMBER";
};

type Member = {
  user_id: string;
  email: string;
  display_name: string | null;
  role: "OWNER" | "MEMBER";
  created_at: string;
};

export default async function WorkspacePage({
  params,
  searchParams,
}: {
  params: Promise<{ workspaceId: string }>;
  searchParams: Promise<{ error?: string }>;
}) {
  const [{ workspaceId }, { error }] = await Promise.all([params, searchParams]);
  const workspaceResponse = await apiFetch(`/workspaces/${encodeURIComponent(workspaceId)}`);
  if (workspaceResponse.status === 404) notFound();
  if (!workspaceResponse.ok) notFound();
  const workspace = (await workspaceResponse.json()) as Workspace;
  const membersResponse = await apiFetch(`/workspaces/${encodeURIComponent(workspaceId)}/members`);
  const members = membersResponse.ok ? ((await membersResponse.json()) as Member[]) : [];
  const isOwner = workspace.role === "OWNER";

  return (
    <main className="app-shell">
      <header className="topbar">
        <Link className="brand" href="/workspaces">KnowFlow</Link>
        <div className="user-menu"><span>{isOwner ? "Owner" : "Member"}</span><form action={signOutAction}><button className="button button-quiet" type="submit">Sign out</button></form></div>
      </header>
      <div className="content-wrap">
        <Link className="back-link" href="/workspaces">← All workspaces</Link>
        <p className="eyebrow">Workspace</p>
        <div className="title-row"><h1 className="page-title">{workspace.name}</h1><span className={`role-pill ${isOwner ? "role-owner" : ""}`}>{isOwner ? "Owner" : "Member"}</span></div>
        <p className="page-intro">Organize internal documents into knowledge areas and manage workspace access.</p>
        <nav className="section-nav" aria-label="Workspace sections">
          <Link className="button button-secondary" href={`/workspaces/${workspaceId}/knowledge-areas`}>Knowledge areas</Link>
          <Link className="button button-secondary" href={`/workspaces/${workspaceId}/documents`}>Documents</Link>
          <Link className="button button-secondary" href={`/workspaces/${workspaceId}/search`}>Ask KnowFlow</Link>
        </nav>
        {error ? <p className="notice notice-error" role="alert">{error}</p> : null}
        <section className="panel" aria-labelledby="members-title">
          <div className="panel-heading"><div><h2 id="members-title">Members</h2><p>Membership is scoped to this workspace.</p></div></div>
          <ul className="member-list">
            {members.map((member) => (
              <li key={member.user_id}>
                <div className="member-info"><span className="workspace-name">{member.display_name || member.email}</span><span className="workspace-meta">{member.display_name ? member.email : ""}</span></div>
                <span className="role-pill">{member.role === "OWNER" ? "Owner" : "Member"}</span>
                {isOwner ? (
                  <div className="member-actions">
                    <form action={changeMemberRole}>
                      <input type="hidden" name="workspace_id" value={workspaceId} />
                      <input type="hidden" name="user_id" value={member.user_id} />
                      <input type="hidden" name="role" value={member.role === "OWNER" ? "MEMBER" : "OWNER"} />
                      <button className="text-button" type="submit">{member.role === "OWNER" ? "Make Member" : "Make Owner"}</button>
                    </form>
                    <form action={removeMember}>
                      <input type="hidden" name="workspace_id" value={workspaceId} />
                      <input type="hidden" name="user_id" value={member.user_id} />
                      <button className="text-button text-danger" type="submit">Remove</button>
                    </form>
                  </div>
                ) : null}
              </li>
            ))}
          </ul>
          {isOwner ? (
            <form action={addMember} className="form-row add-member-form">
              <input type="hidden" name="workspace_id" value={workspaceId} />
              <label className="field-label" htmlFor="member-email">Add an existing verified account</label>
              <div className="input-row">
                <input id="member-email" name="email" type="email" maxLength={320} required placeholder="colleague@example.com" />
                <button className="button button-primary" type="submit">Add Member</button>
              </div>
            </form>
          ) : <p className="member-note">Only an Owner can manage workspace membership.</p>}
        </section>
      </div>
    </main>
  );
}
