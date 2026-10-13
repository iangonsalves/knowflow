import Link from "next/link";
import { notFound } from "next/navigation";

import { deleteDocument, retryDocument, signOutAction, uploadDocument } from "@/app/actions";
import { apiFetch } from "@/lib/api";

type Workspace = { id: string; name: string; role: "OWNER" | "MEMBER" };
type KnowledgeArea = { id: string; name: string };
type Document = {
  id: string;
  knowledge_area_id: string;
  original_filename: string;
  byte_size: number;
  page_count: number;
  status: "UPLOADED" | "PROCESSING" | "READY" | "FAILED" | "DELETING";
  processing_error_code: string | null;
  processing_error_message: string | null;
  created_at: string;
};

function formatSize(bytes: number): string {
  return `${(bytes / (1024 * 1024)).toFixed(2)} MiB`;
}

function formatStatus(status: Document["status"]): string {
  return status === "UPLOADED" ? "Uploaded" : status[0] + status.slice(1).toLowerCase();
}

export default async function DocumentsPage({
  params,
  searchParams,
}: {
  params: Promise<{ workspaceId: string }>;
  searchParams: Promise<{ error?: string; knowledge_area_id?: string }>;
}) {
  const [{ workspaceId }, query] = await Promise.all([params, searchParams]);
  const workspacePath = `/workspaces/${encodeURIComponent(workspaceId)}`;
  const [workspaceResponse, areaResponse] = await Promise.all([
    apiFetch(workspacePath),
    apiFetch(`${workspacePath}/knowledge-areas`),
  ]);
  if (!workspaceResponse.ok || !areaResponse.ok) notFound();
  const workspace = (await workspaceResponse.json()) as Workspace;
  const areas = (await areaResponse.json()) as KnowledgeArea[];
  const areaNames = new Map(areas.map((area) => [area.id, area.name]));
  const queryString = query.knowledge_area_id
    ? `?knowledge_area_id=${encodeURIComponent(query.knowledge_area_id)}`
    : "";
  const documentResponse = await apiFetch(`${workspacePath}/documents${queryString}`);
  if (!documentResponse.ok) notFound();
  const documents = (await documentResponse.json()) as Document[];
  const isOwner = workspace.role === "OWNER";

  return (
    <main className="app-shell">
      <header className="topbar">
        <Link className="brand" href="/workspaces">KnowFlow</Link>
        <div className="user-menu"><span>{isOwner ? "Owner" : "Member"}</span><form action={signOutAction}><button className="button button-quiet" type="submit">Sign out</button></form></div>
      </header>
      <div className="content-wrap">
        <Link className="back-link" href={workspacePath}>← {workspace.name}</Link>
        <p className="eyebrow">Workspace library</p>
        <h1 className="page-title">Documents</h1>
        <p className="page-intro">Private PDFs are stored outside the database and are available to workspace members.</p>
        {query.error ? <p className="notice notice-error" role="alert">{query.error}</p> : null}
        <nav className="section-nav" aria-label="Workspace sections">
          <Link className="button button-secondary" href={`${workspacePath}/knowledge-areas`}>Knowledge areas</Link>
          <Link className="button button-secondary" href={`${workspacePath}/search`}>Search</Link>
          <Link className="button button-secondary" href={workspacePath}>Members &amp; settings</Link>
        </nav>
        {isOwner ? <section className="panel" aria-labelledby="upload-title">
          <div className="panel-heading"><div><h2 id="upload-title">Upload a PDF</h2><p>PDF files up to 20 MiB and 250 pages are accepted.</p></div></div>
          {areas.length ? <form action={uploadDocument} className="upload-form">
            <input type="hidden" name="workspace_id" value={workspaceId} />
            <div className="form-field"><label className="field-label" htmlFor="document-area">Knowledge area</label><select id="document-area" name="knowledge_area_id" required defaultValue={query.knowledge_area_id ?? ""}><option value="" disabled>Select an area</option>{areas.map((area) => <option key={area.id} value={area.id}>{area.name}</option>)}</select></div>
            <div className="form-field"><label className="field-label" htmlFor="pdf-file">PDF file</label><input id="pdf-file" name="file" type="file" accept="application/pdf,.pdf" required /></div>
            <button className="button button-primary" type="submit">Upload document</button>
          </form> : <p className="empty-state">Create a knowledge area before uploading documents.</p>}
        </section> : null}
        <section className="panel" aria-labelledby="document-list-title">
          <div className="panel-heading"><div><h2 id="document-list-title">{query.knowledge_area_id ? `Area: ${areaNames.get(query.knowledge_area_id) ?? "Documents"}` : "All documents"}</h2><p>{documents.length} {documents.length === 1 ? "document" : "documents"}</p></div>{query.knowledge_area_id ? <Link className="text-button" href={`${workspacePath}/documents`}>Clear filter</Link> : null}</div>
          {documents.length ? <ul className="document-list">{documents.map((document) => (
            <li key={document.id} className="document-row">
              <div className="document-main"><span className="document-icon" aria-hidden="true">PDF</span><div><Link className="document-title" href={`${workspacePath}/documents/${document.id}`}>{document.original_filename}</Link><p className="workspace-meta">{areaNames.get(document.knowledge_area_id) ?? "Knowledge area"} · {document.page_count} pages · {formatSize(document.byte_size)}</p>{document.processing_error_message ? <p className="processing-error" role="status">{document.processing_error_message}</p> : null}</div></div>
              <div className="document-actions"><span className={`status-pill status-${document.status.toLowerCase()}`}>{formatStatus(document.status)}</span><Link className="text-button" href={`${workspacePath}/documents/${document.id}`}>Open</Link><a className="text-button" href={`/api${workspacePath}/documents/${document.id}/content?download=true`}>Download</a>{isOwner && document.status === "FAILED" ? <form action={retryDocument}><input type="hidden" name="workspace_id" value={workspaceId} /><input type="hidden" name="document_id" value={document.id} /><button className="text-button" type="submit">Retry processing</button></form> : null}{isOwner ? <form action={deleteDocument}><input type="hidden" name="workspace_id" value={workspaceId} /><input type="hidden" name="document_id" value={document.id} /><button className="text-button text-danger" type="submit">Delete</button></form> : null}</div>
            </li>
          ))}</ul> : <p className="empty-state">No documents have been uploaded{query.knowledge_area_id ? " to this area" : " yet"}.</p>}
        </section>
      </div>
    </main>
  );
}
