import Link from "next/link";
import { apiFetch } from "@/lib/api";
import { getWorkspaceCapabilities, getDocumentStatusLabel } from "@/lib/ui-helpers.mjs";
import { requireApiSuccess } from "@/lib/require-api-success";

type Workspace = { id: string; name: string; role: "OWNER" | "MEMBER" };
type Area = { id: string; name: string; document_count: number };
type Document = { id: string; original_filename: string; status: string; created_at: string };
type Member = { user_id: string };

export default async function WorkspacePage({ params }: { params: Promise<{ workspaceId: string }> }) {
  const { workspaceId } = await params;
  const base = `/workspaces/${encodeURIComponent(workspaceId)}`;
  const [workspaceResponse, areasResponse, documentsResponse] = await Promise.all([
    apiFetch(base), apiFetch(`${base}/knowledge-areas`), apiFetch(`${base}/documents`),
  ]);
  requireApiSuccess(workspaceResponse);
  requireApiSuccess(areasResponse);
  requireApiSuccess(documentsResponse);
  const workspace = (await workspaceResponse.json()) as Workspace;
  const areas = (await areasResponse.json()) as Area[];
  const documents = (await documentsResponse.json()) as Document[];
  const readyCount = documents.filter((document) => document.status === "READY").length;
  const processingCount = documents.filter((document) => ["UPLOADED", "PROCESSING"].includes(document.status)).length;
  const failedCount = documents.filter((document) => document.status === "FAILED").length;
  const { canManageMembers: isOwner } = getWorkspaceCapabilities(workspace.role);
  const memberResponse = isOwner ? await apiFetch(`${base}/members`) : null;
  if (memberResponse) requireApiSuccess(memberResponse);
  const members = memberResponse ? ((await memberResponse.json()) as Member[]) : null;

  return (
    <div className="page-content">
      <p className="eyebrow">Workspace overview</p>
      <div className="dashboard-heading">
        <div><h1 className="page-title">{workspace.name}</h1><p className="page-intro">Your team’s documents, organized and ready to explore.</p></div>
        <Link className="button button-primary" href={`${base}/search`}>Ask KnowFlow</Link>
      </div>

      <section className="metric-grid" aria-label="Workspace summary">
        <article className="metric-card"><span>Knowledge areas</span><strong>{areas.length}</strong><Link href={`${base}/knowledge-areas`}>Browse areas</Link></article>
        <article className="metric-card"><span>Documents</span><strong>{documents.length}</strong><Link href={`${base}/documents`}>View library</Link></article>
        <article className="metric-card"><span>Ready to search</span><strong>{readyCount}</strong><span className="metric-note">{processingCount} processing · {failedCount} failed</span></article>
        {members ? <article className="metric-card"><span>Workspace members</span><strong>{members.length}</strong><Link href={`${base}/members`}>Manage members</Link></article> : null}
      </section>

      {documents.length === 0 ? (
        <section className="empty-panel">
          <p className="eyebrow">Build your knowledge base</p>
          <h2>Start with a Knowledge Area</h2>
          <p>Use areas to organize policies and procedures, then upload a selectable-text PDF.</p>
          {isOwner ? <Link className="button button-primary" href={`${base}/knowledge-areas`}>Create a Knowledge Area</Link> : <Link className="button button-secondary" href={`${base}/knowledge-areas`}>Browse Knowledge Areas</Link>}
        </section>
      ) : (
        <section className="panel" aria-labelledby="recent-documents-title">
          <div className="panel-heading"><div><h2 id="recent-documents-title">Recently added</h2><p>Documents in this workspace knowledge base.</p></div><Link className="text-button" href={`${base}/documents`}>View all</Link></div>
          <ul className="recent-document-list">
            {documents.slice(0, 5).map((document) => (
              <li key={document.id}><span className="document-icon" aria-hidden="true">PDF</span><Link href={`${base}/documents/${document.id}`} className="document-title">{document.original_filename}</Link><span className={`status-pill status-${document.status.toLowerCase()}`}>{getDocumentStatusLabel(document.status)}</span></li>
            ))}
          </ul>
          {readyCount === 0 ? <p className="notice notice-neutral">Ask KnowFlow becomes available when at least one document is Ready.</p> : null}
        </section>
      )}
    </div>
  );
}
