import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import { getDocumentStatusLabel, getWorkspaceCapabilities, getWorkspaceNavigationItems, safeAskErrorMessage } from "../src/lib/ui-helpers.mjs";

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
