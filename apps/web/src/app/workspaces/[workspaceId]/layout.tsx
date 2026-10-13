import Link from "next/link";

import { signOutAction } from "@/app/actions";
import { apiFetch } from "@/lib/api";
import { requireApiSuccess } from "@/lib/require-api-success";

import WorkspaceNavigation, { MobileWorkspaceMenu } from "./WorkspaceNavigation";

type Workspace = { id: string; name: string; role: "OWNER" | "MEMBER" };

export default async function WorkspaceLayout({ children, params }: Readonly<{
  children: React.ReactNode;
  params: Promise<{ workspaceId: string }>;
}>) {
  const { workspaceId } = await params;
  const response = requireApiSuccess(await apiFetch(`/workspaces/${encodeURIComponent(workspaceId)}`));
  const workspace = (await response.json()) as Workspace;
  const isOwner = workspace.role === "OWNER";

  return (
    <div className="app-shell">
      <header className="topbar">
        <Link className="brand" href="/workspaces">KnowFlow</Link>
        <MobileWorkspaceMenu workspaceId={workspaceId} />
        <div className="topbar-context">
          <span className="workspace-context-name" title={workspace.name}>{workspace.name}</span>
          <span className={`role-pill${isOwner ? " role-owner" : ""}`}>{isOwner ? "Owner" : "Member"}</span>
        </div>
        <div className="user-menu">
          <Link className="workspace-switch" href="/workspaces">Switch workspace</Link>
          <form action={signOutAction}><button className="button button-quiet" type="submit">Sign out</button></form>
        </div>
      </header>
      <div className="workspace-layout">
        <WorkspaceNavigation workspaceId={workspaceId} />
        <main className="workspace-main">{children}</main>
      </div>
    </div>
  );
}
