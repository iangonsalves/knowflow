import Link from "next/link";
import { notFound } from "next/navigation";

import { deleteDocument, signOutAction } from "@/app/actions";
import { apiFetch } from "@/lib/api";

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
}: {
  params: Promise<{ workspaceId: string; documentId: string }>;
}) {
  const { workspaceId, documentId } = await params;
  const workspacePath = `/workspaces/${encodeURIComponent(workspaceId)}`;
  const documentPath = `${workspacePath}/documents/${encodeURIComponent(documentId)}`;
  const [workspaceResponse, documentResponse, areaResponse] = await Promise.all([
    apiFetch(workspacePath),
    apiFetch(documentPath),
    apiFetch(`${workspacePath}/knowledge-areas`),
  ]);
  if (workspaceResponse.status === 404 || documentResponse.status === 404) notFound();
  if (!workspaceResponse.ok || !documentResponse.ok || !areaResponse.ok) notFound();
  const workspace = (await workspaceResponse.json()) as Workspace;
  const document = (await documentResponse.json()) as Document;
  const areas = (await areaResponse.json()) as KnowledgeArea[];
  const area = areas.find((item) => item.id === document.knowledge_area_id);
  const contentPath = `/api${documentPath}/content`;

  return (
    <main className="app-shell">
      <header className="topbar">
        <Link className="brand" href="/workspaces">KnowFlow</Link>
        <div className="user-menu"><span>{workspace.role === "OWNER" ? "Owner" : "Member"}</span><form action={signOutAction}><button className="button button-quiet" type="submit">Sign out</button></form></div>
      </header>
      <div className="content-wrap content-wide">
        <Link className="back-link" href={`${workspacePath}/documents`}>← All documents</Link>
        <p className="eyebrow">{area?.name ?? "Document"}</p>
        <h1 className="page-title document-detail-title">{document.original_filename}</h1>
        <p className="page-intro">{document.page_count} pages · {(document.byte_size / (1024 * 1024)).toFixed(2)} MiB · {document.status}</p>
        {document.processing_error_message ? <p className="notice notice-error" role="status">{document.processing_error_message}</p> : null}
        <section className="panel viewer-panel" aria-label="PDF document">
          <div className="viewer-toolbar"><span>Private workspace document</span><div className="document-actions"><a className="button button-secondary" href={`${contentPath}?download=true`}>Download PDF</a>{workspace.role === "OWNER" ? <form action={deleteDocument}><input type="hidden" name="workspace_id" value={workspaceId} /><input type="hidden" name="document_id" value={document.id} /><button className="button button-danger" type="submit">Delete document</button></form> : null}</div></div>
          <iframe className="pdf-frame" title={document.original_filename} src={contentPath} />
        </section>
      </div>
    </main>
  );
}
