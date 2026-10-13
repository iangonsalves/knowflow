import { apiFetch } from "@/lib/api";
import { requireApiSuccess } from "@/lib/require-api-success";

import SearchForm from "./SearchForm";

export default async function SearchPage({
  params,
}: {
  params: Promise<{ workspaceId: string }>;
}) {
  const { workspaceId } = await params;
  const workspacePath = `/workspaces/${encodeURIComponent(workspaceId)}`;
  const documentsResponse = await apiFetch(`${workspacePath}/documents`);
  requireApiSuccess(documentsResponse);
  const documents = (await documentsResponse.json()) as Array<{ status: string }>;
  const readyCount = documents.filter((document) => document.status === "READY").length;

  return (
    <div className="page-content">
        <p className="eyebrow">Workspace knowledge</p>
        <h1 className="page-title">Ask KnowFlow</h1>
        <p className="page-intro">Search workspace documents and inspect relevant source passages. KnowFlow presents retrieved evidence; it does not generate answers.</p>
        {readyCount === 0 ? <p className="notice notice-neutral" role="status">No documents are Ready to search yet. Documents become searchable after processing completes.</p> : null}
        <SearchForm workspaceId={workspaceId} hasReadyDocuments={readyCount > 0} />
    </div>
  );
}
