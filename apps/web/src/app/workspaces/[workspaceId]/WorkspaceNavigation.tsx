"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useRef, useState } from "react";

import { getWorkspaceNavigationItems } from "@/lib/ui-helpers.mjs";

type Props = { workspaceId: string };

function NavigationLinks({ workspaceId, pathname, onNavigate }: {
  workspaceId: string;
  pathname: string;
  onNavigate?: () => void;
}) {
  const items = getWorkspaceNavigationItems(workspaceId, pathname);
  return items.map((item) => (
    <Link key={item.href} href={item.href} className={`workspace-nav-link${item.active ? " active" : ""}`} aria-current={item.active ? "page" : undefined} onClick={onNavigate}>
      {item.label}
    </Link>
  ));
}

export default function WorkspaceNavigation({ workspaceId }: Props) {
  const pathname = usePathname();
  return (
    <nav className="workspace-nav workspace-nav-desktop" aria-label="Workspace navigation">
      <p className="workspace-nav-label">Workspace</p>
      <NavigationLinks workspaceId={workspaceId} pathname={pathname} />
    </nav>
  );
}

export function MobileWorkspaceMenu({ workspaceId }: Props) {
  const pathname = usePathname();
  const items = getWorkspaceNavigationItems(workspaceId, pathname);
  const activeItem = items.find((item) => item.active) ?? items[0];
  const [isOpen, setIsOpen] = useState(false);
  const toggleRef = useRef<HTMLButtonElement>(null);

  function closeOnEscape(event: React.KeyboardEvent<HTMLElement>) {
    if (event.key === "Escape") {
      setIsOpen(false);
      toggleRef.current?.focus();
    }
  }

  return (
    <div className="mobile-header-navigation" onKeyDown={closeOnEscape}>
      <button
        ref={toggleRef}
        type="button"
        className="mobile-header-menu-toggle"
        aria-label={`${isOpen ? "Close" : "Open"} workspace navigation. Current section: ${activeItem.label}`}
        aria-expanded={isOpen}
        aria-controls="mobile-workspace-navigation-links"
        onClick={() => setIsOpen((open) => !open)}
      >
        <span className={`mobile-menu-icon${isOpen ? " is-open" : ""}`} aria-hidden="true"><span /><span /><span /></span>
        <span className="mobile-header-menu-label">Menu</span>
      </button>
      <nav id="mobile-workspace-navigation-links" className="mobile-header-menu-panel" aria-label="Workspace navigation" hidden={!isOpen}>
        <p className="mobile-header-menu-current">Current section: <strong>{activeItem.label}</strong></p>
        <NavigationLinks workspaceId={workspaceId} pathname={pathname} onNavigate={() => setIsOpen(false)} />
      </nav>
    </div>
  );
}
