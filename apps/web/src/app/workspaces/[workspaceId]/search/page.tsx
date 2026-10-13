import Link from "next/link";
import { notFound } from "next/navigation";

import { signOutAction } from "@/app/actions";
import { apiFetch } from "@/lib/api";

import SearchForm from "./SearchForm";

type Workspace = { id: string; name: string; role: "OWNER" | "MEMBER" };

export default async function SearchPage({
  params,
}: {
  params: Promise<{ workspaceId: string }>;
}) {
  const { workspaceId } = await params;
  const workspacePath = `/workspaces/${encodeURIComponent(workspaceId)}`;
  const workspaceResponse = await apiFetch(workspacePath);
  if (!workspaceResponse.ok) notFound();
  const workspace = (await workspaceResponse.json()) as Workspace;

  return (
    <main className="app-shell">
      <header className="topbar">
        <Link className="brand" href="/workspaces">KnowFlow</Link>
        <div className="user-menu"><span>{workspace.role === "OWNER" ? "Owner" : "Member"}</span><form action={signOutAction}><button className="button button-quiet" type="submit">Sign out</button></form></div>
      </header>
      <div className="content-wrap">
        <Link className="back-link" href={workspacePath}>← {workspace.name}</Link>
        <p className="eyebrow">Workspace knowledge</p>
        <h1 className="page-title">Ask KnowFlow</h1>
        <p className="page-intro">Ask a question in your own words and review the source passages that best match it.</p>
        <nav className="section-nav" aria-label="Workspace sections">
          <Link className="button button-secondary" href={`${workspacePath}/knowledge-areas`}>Knowledge areas</Link>
          <Link className="button button-secondary" href={`${workspacePath}/documents`}>Documents</Link>
        </nav>
        <SearchForm workspaceId={workspaceId} />
      </div>
    </main>
  );
}
