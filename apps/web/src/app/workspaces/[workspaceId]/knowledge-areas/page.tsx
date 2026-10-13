import Link from "next/link";
import {
  createKnowledgeArea,
  deleteKnowledgeArea,
  updateKnowledgeArea,
} from "@/app/actions";
import ConfirmSubmit from "@/app/components/ConfirmSubmit";
import PendingSubmitButton from "@/app/components/PendingSubmitButton";
import { apiFetch } from "@/lib/api";
import { getWorkspaceCapabilities } from "@/lib/ui-helpers.mjs";
import { requireApiSuccess } from "@/lib/require-api-success";

type Workspace = { id: string; name: string; role: "OWNER" | "MEMBER" };
type KnowledgeArea = {
  id: string;
  name: string;
  description: string | null;
  document_count: number;
};

export default async function KnowledgeAreasPage({
  params,
  searchParams,
}: {
  params: Promise<{ workspaceId: string }>;
  searchParams: Promise<{ error?: string }>;
}) {
  const [{ workspaceId }, { error }] = await Promise.all([params, searchParams]);
  const workspacePath = `/workspaces/${encodeURIComponent(workspaceId)}`;
  const workspaceResponse = await apiFetch(workspacePath);
  requireApiSuccess(workspaceResponse);
  const workspace = (await workspaceResponse.json()) as Workspace;
  const areaResponse = await apiFetch(`${workspacePath}/knowledge-areas`);
  requireApiSuccess(areaResponse);
  const areas = (await areaResponse.json()) as KnowledgeArea[];
  const { canManageKnowledgeAreas: isOwner } = getWorkspaceCapabilities(workspace.role);

  return (
    <div className="page-content">
        <p className="eyebrow">Workspace structure</p>
        <h1 className="page-title">Knowledge areas</h1>
        <p className="page-intro">Group documents by the teams and topics that use them.</p>
        {error ? <p className="notice notice-error" role="alert">{error}</p> : null}
        {isOwner ? (
          <section className="panel" aria-labelledby="create-area-title">
            <div className="panel-heading"><div><h2 id="create-area-title">Create an area</h2><p>Area names must be unique within this workspace.</p></div></div>
            <form action={createKnowledgeArea} className="stack-form">
              <input type="hidden" name="workspace_id" value={workspaceId} />
              <label className="field-label" htmlFor="area-name">Name</label>
              <input id="area-name" name="name" minLength={1} maxLength={120} required placeholder="Human Resources" />
              <label className="field-label" htmlFor="area-description">Description <span className="optional-label">(optional)</span></label>
              <textarea id="area-description" name="description" maxLength={500} rows={2} placeholder="Policies and employee guidance" />
              <div><PendingSubmitButton label="Create area" pendingLabel="Creating…" /></div>
            </form>
          </section>
        ) : null}
        <section className="panel" aria-labelledby="area-list-title">
          <div className="panel-heading"><div><h2 id="area-list-title">Areas in {workspace.name}</h2><p>{isOwner ? "Manage organization areas and their documents." : "Browse areas available to workspace members."}</p></div></div>
          {areas.length ? <ul className="area-list">
            {areas.map((area) => (
              <li key={area.id} className="area-card">
                <div className="area-card-heading">
                  <div><h3>{area.name}</h3><p>{area.description || "No description"}</p><span className="workspace-meta">{area.document_count} {area.document_count === 1 ? "document" : "documents"}</span></div>
                  <Link className="text-button" href={`${workspacePath}/documents?knowledge_area_id=${area.id}`}>View documents</Link>
                </div>
                {isOwner ? <div className="area-management">
                  <form action={updateKnowledgeArea} className="inline-area-form">
                    <input type="hidden" name="workspace_id" value={workspaceId} />
                    <input type="hidden" name="area_id" value={area.id} />
                    <label className="visually-hidden" htmlFor={`area-name-${area.id}`}>Rename {area.name}</label>
                    <input id={`area-name-${area.id}`} name="name" defaultValue={area.name} maxLength={120} required />
                    <label className="visually-hidden" htmlFor={`area-description-${area.id}`}>Description for {area.name}</label>
                    <input id={`area-description-${area.id}`} name="description" defaultValue={area.description ?? ""} maxLength={500} placeholder="Description" />
                    <button className="button button-secondary" type="submit">Save</button>
                  </form>
                  <form action={deleteKnowledgeArea}>
                    <input type="hidden" name="workspace_id" value={workspaceId} />
                    <input type="hidden" name="area_id" value={area.id} />
                    <ConfirmSubmit label="Delete area" confirmation={`Delete ${area.name}? Only empty areas can be deleted.`} danger />
                  </form>
                </div> : null}
              </li>
            ))}
          </ul> : <p className="empty-state">No knowledge areas yet.</p>}
          {!isOwner ? <p className="member-note">Only an Owner can create or change knowledge areas.</p> : null}
        </section>
    </div>
  );
}
