import { addMember, changeMemberRole, removeMember } from "@/app/actions";
import ConfirmSubmit from "@/app/components/ConfirmSubmit";
import PendingSubmitButton from "@/app/components/PendingSubmitButton";
import { apiFetch } from "@/lib/api";
import { getWorkspaceCapabilities } from "@/lib/ui-helpers.mjs";
import { requireApiSuccess } from "@/lib/require-api-success";

type Workspace = { name: string; role: "OWNER" | "MEMBER" };
type Member = { user_id: string; email: string; display_name: string | null; role: "OWNER" | "MEMBER"; created_at: string };

export default async function MembersPage({ params, searchParams }: {
  params: Promise<{ workspaceId: string }>;
  searchParams: Promise<{ error?: string }>;
}) {
  const [{ workspaceId }, { error }] = await Promise.all([params, searchParams]);
  const base = `/workspaces/${encodeURIComponent(workspaceId)}`;
  const workspaceResponse = await apiFetch(base);
  requireApiSuccess(workspaceResponse);
  const workspace = (await workspaceResponse.json()) as Workspace;
  const membersResponse = await apiFetch(`${base}/members`);
  requireApiSuccess(membersResponse);
  const members = (await membersResponse.json()) as Member[];
  const { canManageMembers: isOwner } = getWorkspaceCapabilities(workspace.role);

  return (
    <div className="page-content">
      <p className="eyebrow">Workspace access</p>
      <h1 className="page-title">Members</h1>
      <p className="page-intro">People in {workspace.name} can browse authorized documents and ask questions using the workspace knowledge base.</p>
      {error ? <p className="notice notice-error" role="alert">{error}</p> : null}
      <section className="panel" aria-labelledby="member-list-title">
        <div className="panel-heading"><div><h2 id="member-list-title">Workspace members</h2><p>{members.length} {members.length === 1 ? "person" : "people"} · Roles are managed within KnowFlow.</p></div></div>
        <ul className="member-list">
          {members.map((member) => (
            <li key={member.user_id}>
              <div className="member-info"><span className="workspace-name">{member.display_name || member.email}</span>{member.display_name ? <span className="workspace-meta">{member.email}</span> : null}</div>
              <span className={`role-pill${member.role === "OWNER" ? " role-owner" : ""}`}>{member.role === "OWNER" ? "Owner" : "Member"}</span>
              {isOwner ? <div className="member-actions">
                <form action={changeMemberRole}>
                  <input type="hidden" name="workspace_id" value={workspaceId} />
                  <input type="hidden" name="user_id" value={member.user_id} />
                  <input type="hidden" name="role" value={member.role === "OWNER" ? "MEMBER" : "OWNER"} />
                  <ConfirmSubmit label={member.role === "OWNER" ? "Change to Member" : "Make Owner"} confirmation={`Change ${member.display_name || member.email} to ${member.role === "OWNER" ? "Member" : "Owner"}?`} />
                </form>
                <form action={removeMember}>
                  <input type="hidden" name="workspace_id" value={workspaceId} />
                  <input type="hidden" name="user_id" value={member.user_id} />
                  <ConfirmSubmit label="Remove" confirmation={`Remove ${member.display_name || member.email} from ${workspace.name}?`} danger />
                </form>
              </div> : null}
            </li>
          ))}
        </ul>
        {isOwner ? <form action={addMember} className="form-row add-member-form">
          <input type="hidden" name="workspace_id" value={workspaceId} />
          <label className="field-label" htmlFor="member-email">Add an existing verified account</label>
          <div className="input-row"><input id="member-email" name="email" type="email" maxLength={320} required autoComplete="email" placeholder="colleague@example.com" /><PendingSubmitButton label="Add member" pendingLabel="Adding…" /></div>
          <p className="workspace-meta">The person must already have a KnowFlow account.</p>
        </form> : <p className="member-note">Only a workspace Owner can add members, change roles, or remove access.</p>}
      </section>
    </div>
  );
}
