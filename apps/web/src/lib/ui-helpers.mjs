export function getWorkspaceCapabilities(role) {
  const isOwner = role === "OWNER";
  return {
    canManageKnowledgeAreas: isOwner,
    canManageDocuments: isOwner,
    canManageMembers: isOwner,
  };
}

export function getDocumentStatusLabel(status) {
  const labels = {
    UPLOADED: "Uploaded",
    PROCESSING: "Processing",
    READY: "Ready",
    FAILED: "Failed",
    DELETING: "Deleting",
  };
  return labels[status] ?? "Unknown status";
}

export function safeAskErrorMessage(status) {
  if (status === 404) return "This workspace or its documents are no longer available.";
  if (status === 422) return "Please check your question and try again.";
  if (status >= 500) return "Ask KnowFlow is temporarily unavailable. Try again shortly.";
  return "Your question could not be processed. Check your workspace access and try again.";
}

export function getWorkspaceNavigationItems(workspaceId, pathname) {
  const base = `/workspaces/${encodeURIComponent(workspaceId)}`;
  const items = [
    { href: base, label: "Overview", exact: true },
    { href: `${base}/search`, label: "Ask KnowFlow" },
    { href: `${base}/knowledge-areas`, label: "Knowledge areas" },
    { href: `${base}/documents`, label: "Documents" },
    { href: `${base}/members`, label: "Members" },
  ];
  return items.map((item) => ({
    ...item,
    active: item.exact
      ? pathname === item.href
      : pathname === item.href || pathname.startsWith(`${item.href}/`),
  }));
}
