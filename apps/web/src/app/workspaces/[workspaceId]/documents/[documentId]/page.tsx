import Link from "next/link";
import { deleteDocument } from "@/app/actions";
import ConfirmSubmit from "@/app/components/ConfirmSubmit";
import { apiFetch } from "@/lib/api";
import { getDocumentStatusLabel, getWorkspaceCapabilities } from "@/lib/ui-helpers.mjs";
import { requireApiSuccess } from "@/lib/require-api-success";

type Workspace = { name: string; role: "OWNER" | "MEMBER" };
type Document = {
  id: string;
  knowledge_area_id: string;
  original_filename: string;
  byte_size: number;
  page_count: number;
  status: string;
  processing_error_message: string | null;
  created_at: string;
};
type KnowledgeArea = { id: string; name: string };

export default async function DocumentDetailPage({
  params,
  searchParams,
}: {
  params: Promise<{ workspaceId: string; documentId: string }>;
  searchParams: Promise<{ page?: string }>;
}) {
  const [{ workspaceId, documentId }, query] = await Promise.all([params, searchParams]);
  const workspacePath = `/workspaces/${encodeURIComponent(workspaceId)}`;
  const documentPath = `${workspacePath}/documents/${encodeURIComponent(documentId)}`;
  const [workspaceResponse, documentResponse, areaResponse] = await Promise.all([
    apiFetch(workspacePath),
    apiFetch(documentPath),
    apiFetch(`${workspacePath}/knowledge-areas`),
  ]);
  requireApiSuccess(workspaceResponse);
  requireApiSuccess(documentResponse);
  requireApiSuccess(areaResponse);
  const workspace = (await workspaceResponse.json()) as Workspace;
  const document = (await documentResponse.json()) as Document;
  const areas = (await areaResponse.json()) as KnowledgeArea[];
  const { canManageDocuments } = getWorkspaceCapabilities(workspace.role);
  const area = areas.find((item) => item.id === document.knowledge_area_id);
  const contentPath = `/api${documentPath}/content`;
  const requestedPage = Number(query.page);
  const page = Number.isInteger(requestedPage) && requestedPage > 0
    ? Math.min(requestedPage, document.page_count)
    : null;

  return (
    <div className="page-content page-content-wide">
        <Link className="back-link" href={`${workspacePath}/documents`}>← All documents</Link>
        <p className="eyebrow">{area?.name ?? "Document"}</p>
        <h1 className="page-title document-detail-title">{document.original_filename}</h1>
        <p className="page-intro">{document.page_count} pages · {(document.byte_size / (1024 * 1024)).toFixed(2)} MiB · <span className={`status-pill status-${document.status.toLowerCase()}`}>{getDocumentStatusLabel(document.status)}</span></p>
        {["UPLOADED", "PROCESSING"].includes(document.status) ? <p className="notice notice-neutral">This document is being processed and will become searchable when it is Ready.</p> : null}
        {document.processing_error_message ? <p className="notice notice-error" role="status">{document.processing_error_message}</p> : null}
        <section className="panel viewer-panel" aria-label="PDF document">
          <div className="viewer-toolbar"><span>Private workspace document{page ? ` · Page ${page}` : ""}</span><div className="document-actions"><a className="button button-secondary" href={`${contentPath}?download=true`}>Download PDF</a>{canManageDocuments ? <form action={deleteDocument}><input type="hidden" name="workspace_id" value={workspaceId} /><input type="hidden" name="document_id" value={document.id} /><ConfirmSubmit label="Delete document" confirmation={`Delete ${document.original_filename}? Access is revoked immediately.`} danger className="button button-danger" /></form> : null}</div></div>
          <iframe className="pdf-frame" title={document.original_filename} src={page ? `${contentPath}#page=${page}` : contentPath} />
        </section>
    </div>
  );
}
