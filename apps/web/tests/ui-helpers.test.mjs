import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import { getDocumentStatusLabel, getWorkspaceCapabilities, getWorkspaceNavigationItems, safeAskErrorMessage } from "../src/lib/ui-helpers.mjs";
import {
  BACKEND_STARTUP_MAX_ATTEMPTS,
  BACKEND_STARTUP_RETRY_DELAY_MS,
  shouldRetryBackendStartup,
} from "../src/lib/backend-readiness.mjs";

test("workspace UI capabilities reflect Owner and Member roles", () => {
  assert.deepEqual(getWorkspaceCapabilities("OWNER"), {
    canManageKnowledgeAreas: true,
    canManageDocuments: true,
    canManageMembers: true,
  });
  assert.deepEqual(getWorkspaceCapabilities("MEMBER"), {
    canManageKnowledgeAreas: false,
    canManageDocuments: false,
    canManageMembers: false,
  });
});

test("document statuses have readable labels without color dependence", () => {
  assert.equal(getDocumentStatusLabel("UPLOADED"), "Uploaded");
  assert.equal(getDocumentStatusLabel("PROCESSING"), "Processing");
  assert.equal(getDocumentStatusLabel("READY"), "Ready");
  assert.equal(getDocumentStatusLabel("FAILED"), "Failed");
  assert.equal(getDocumentStatusLabel("DELETING"), "Deleting");
  assert.equal(getDocumentStatusLabel("unexpected"), "Unknown status");
});

test("Ask errors use safe status-specific messages rather than backend internals", () => {
  assert.match(safeAskErrorMessage(404), /no longer available/);
  assert.match(safeAskErrorMessage(422), /check your question/);
  assert.match(safeAskErrorMessage(503), /temporarily unavailable/);
  assert.doesNotMatch(safeAskErrorMessage(500), /SQL|traceback|object storage/i);
});

test("workspace navigation exposes all five destinations and marks the current section", () => {
  const items = getWorkspaceNavigationItems("team 1", "/workspaces/team%201/documents/123");
  assert.deepEqual(items.map(({ label }) => label), [
    "Overview", "Ask KnowFlow", "Knowledge areas", "Documents", "Members",
  ]);
  assert.deepEqual(items.filter(({ active }) => active).map(({ label }) => label), ["Documents"]);
  assert.equal(items[0].href, "/workspaces/team%201");
});

test("workspace overview is active only at the workspace root", () => {
  const overview = getWorkspaceNavigationItems("abc", "/workspaces/abc");
  const documents = getWorkspaceNavigationItems("abc", "/workspaces/abc/documents");
  assert.equal(overview[0].active, true);
  assert.equal(documents[0].active, false);
});

test("backend cold-start retries are bounded and paced without keep-alive traffic", () => {
  assert.equal(BACKEND_STARTUP_MAX_ATTEMPTS, 24);
  assert.equal(BACKEND_STARTUP_RETRY_DELAY_MS, 5_000);
  assert.equal(shouldRetryBackendStartup(1), true);
  assert.equal(shouldRetryBackendStartup(23), true);
  assert.equal(shouldRetryBackendStartup(24), false);
  assert.equal(shouldRetryBackendStartup(1.5), false);
  assert.equal(shouldRetryBackendStartup(-1), false);
});

test("readiness proxy and liveness routes keep backend credentials server-side", async () => {
  const readyRoute = await readFile(new URL("../src/app/api/health/ready/route.ts", import.meta.url), "utf8");
  const liveRoute = await readFile(new URL("../src/app/api/health/live/route.ts", import.meta.url), "utf8");
  const workspaceLoading = await readFile(new URL("../src/app/workspaces/loading.tsx", import.meta.url), "utf8");
  const documentLoading = await readFile(new URL("../src/app/workspaces/[workspaceId]/loading.tsx", import.meta.url), "utf8");
  assert.match(readyRoute, /process\.env\.API_INTERNAL_BASE_URL/);
  assert.match(readyRoute, /AbortSignal\.timeout/);
  assert.match(readyRoute, /Cache-Control.*no-store/);
  assert.match(liveRoute, /status: "alive"/);
  assert.match(workspaceLoading, /BackendLoadingScreen/);
  assert.match(documentLoading, /BackendLoadingScreen/);
});

test("Next Server Action boundary and document UI use the 8 MiB portfolio limit", async () => {
  const nextConfig = await readFile(new URL("../next.config.ts", import.meta.url), "utf8");
  const documentsPage = await readFile(new URL("../src/app/workspaces/[workspaceId]/documents/page.tsx", import.meta.url), "utf8");
  assert.match(nextConfig, /bodySizeLimit: "9mb"/);
  assert.match(documentsPage, /up to 8 MiB and 250 pages/);
});

test("mobile workspace menu is mounted in the header and exposes accessible open/close navigation", async () => {
  const component = await readFile(new URL("../src/app/workspaces/[workspaceId]/WorkspaceNavigation.tsx", import.meta.url), "utf8");
  const layout = await readFile(new URL("../src/app/workspaces/[workspaceId]/layout.tsx", import.meta.url), "utf8");
  const styles = await readFile(new URL("../src/app/globals.css", import.meta.url), "utf8");

  assert.match(layout, /<header className="topbar">[\s\S]*<MobileWorkspaceMenu workspaceId=\{workspaceId\} \/>/);
  assert.match(component, /aria-expanded=\{isOpen\}/);
  assert.match(component, /aria-controls="mobile-workspace-navigation-links"/);
  assert.match(component, /aria-current=\{item\.active \? "page" : undefined\}/);
  assert.match(component, /hidden=\{!isOpen\}/);
  assert.match(component, /onNavigate=\{\(\) => setIsOpen\(false\)\}/);
  assert.match(component, /event\.key === "Escape"/);
  assert.match(styles, /@media \(max-width: 820px\)[\s\S]*\.mobile-header-navigation\s*\{\s*position: static;\s*display: block;/);
  assert.match(styles, /\.mobile-header-menu-panel\s*\{[^}]*left: 12px;[^}]*box-sizing: border-box;/);
});
