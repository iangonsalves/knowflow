export type WorkspaceRole = "OWNER" | "MEMBER";
export type WorkspaceCapabilities = {
  canManageKnowledgeAreas: boolean;
  canManageDocuments: boolean;
  canManageMembers: boolean;
};

export function getWorkspaceCapabilities(role: WorkspaceRole): WorkspaceCapabilities;
export function getDocumentStatusLabel(status: string): string;
export function safeAskErrorMessage(status: number): string;
export type WorkspaceNavigationItem = { href: string; label: string; exact?: boolean; active: boolean };
export function getWorkspaceNavigationItems(workspaceId: string, pathname: string): WorkspaceNavigationItem[];
