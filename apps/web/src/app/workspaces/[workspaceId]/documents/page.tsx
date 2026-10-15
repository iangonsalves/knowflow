import Link from "next/link";
import { deleteDocument, retryDocument, uploadDocument } from "@/app/actions";
import ConfirmSubmit from "@/app/components/ConfirmSubmit";
import PendingSubmitButton from "@/app/components/PendingSubmitButton";
import { apiFetch } from "@/lib/api";
import { getDocumentStatusLabel, getWorkspaceCapabilities } from "@/lib/ui-helpers.mjs";
import { requireApiSuccess } from "@/lib/require-api-success";

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
  requireApiSuccess(workspaceResponse);
  requireApiSuccess(areaResponse);
  const workspace = (await workspaceResponse.json()) as Workspace;
  const areas = (await areaResponse.json()) as KnowledgeArea[];
  const areaNames = new Map(areas.map((area) => [area.id, area.name]));
  const queryString = query.knowledge_area_id
    ? `?knowledge_area_id=${encodeURIComponent(query.knowledge_area_id)}`
    : "";
  const documentResponse = await apiFetch(`${workspacePath}/documents${queryString}`);
  requireApiSuccess(documentResponse);
  const documents = (await documentResponse.json()) as Document[];
  const { canManageDocuments: isOwner } = getWorkspaceCapabilities(workspace.role);

  return (
    <div className="page-content">
        <p className="eyebrow">Workspace library</p>
        <h1 className="page-title">Documents</h1>
        <p className="page-intro">Private PDFs are stored outside the database and are available to workspace members.</p>
        {query.error ? <p className="notice notice-error" role="alert">{query.error}</p> : null}
        {isOwner ? <section className="panel" aria-labelledby="upload-title">
          <div className="panel-heading"><div><h2 id="upload-title">Upload a PDF</h2><p>PDF only · selectable text required · up to 8 MiB and 250 pages. Scanned PDFs need OCR, which V1 does not provide.</p></div></div>
          {areas.length ? <form action={uploadDocument} className="upload-form">
            <input type="hidden" name="workspace_id" value={workspaceId} />
            <div className="form-field"><label className="field-label" htmlFor="document-area">Knowledge area</label><select id="document-area" name="knowledge_area_id" required defaultValue={query.knowledge_area_id ?? ""}><option value="" disabled>Select an area</option>{areas.map((area) => <option key={area.id} value={area.id}>{area.name}</option>)}</select></div>
            <div className="form-field"><label className="field-label" htmlFor="pdf-file">PDF file</label><input id="pdf-file" name="file" type="file" accept="application/pdf,.pdf" required /></div>
            <PendingSubmitButton label="Upload document" pendingLabel="Uploading…" />
          </form> : <p className="empty-state">Create a knowledge area before uploading documents.</p>}
        </section> : null}
        <section className="panel" aria-labelledby="document-list-title">
          <div className="panel-heading"><div><h2 id="document-list-title">{query.knowledge_area_id ? `Area: ${areaNames.get(query.knowledge_area_id) ?? "Documents"}` : "All documents"}</h2><p>{documents.length} {documents.length === 1 ? "document" : "documents"}</p></div><div className="document-actions">{documents.some((document) => ["UPLOADED", "PROCESSING"].includes(document.status)) ? <a className="text-button" href={`${workspacePath}/documents${queryString}`}>Refresh status</a> : null}{query.knowledge_area_id ? <Link className="text-button" href={`${workspacePath}/documents`}>Clear filter</Link> : null}</div></div>
          {documents.length ? <ul className="document-list">{documents.map((document) => (
            <li key={document.id} className="document-row">
              <div className="document-main"><span className="document-icon" aria-hidden="true">PDF</span><div><Link className="document-title" href={`${workspacePath}/documents/${document.id}`}>{document.original_filename}</Link><p className="workspace-meta">{areaNames.get(document.knowledge_area_id) ?? "Knowledge area"} · {document.page_count} pages · {formatSize(document.byte_size)}</p>{document.processing_error_message ? <p className="processing-error" role="status">{document.processing_error_message}</p> : null}</div></div>
              <div className="document-actions"><span className={`status-pill status-${document.status.toLowerCase()}`} aria-label={`Status: ${getDocumentStatusLabel(document.status)}`}>{getDocumentStatusLabel(document.status)}</span><Link className="text-button" href={`${workspacePath}/documents/${document.id}`}>Open</Link><a className="text-button" href={`/api${workspacePath}/documents/${document.id}/content?download=true`}>Download</a>{["UPLOADED", "PROCESSING"].includes(document.status) ? <span className="workspace-meta">Becomes searchable when Ready</span> : null}{isOwner && document.status === "FAILED" ? <form action={retryDocument}><input type="hidden" name="workspace_id" value={workspaceId} /><input type="hidden" name="document_id" value={document.id} /><PendingSubmitButton label="Retry processing" pendingLabel="Retrying…" className="text-button" /></form> : null}{isOwner ? <form action={deleteDocument}><input type="hidden" name="workspace_id" value={workspaceId} /><input type="hidden" name="document_id" value={document.id} /><ConfirmSubmit label="Delete" confirmation={`Delete ${document.original_filename}? Access is revoked immediately.`} danger /></form> : null}</div>
            </li>
          ))}</ul> : <p className="empty-state">No documents have been uploaded{query.knowledge_area_id ? " to this area" : " yet"}.</p>}
        </section>
    </div>
  );
}
