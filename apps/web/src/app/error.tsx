"use client";

import Link from "next/link";

export default function ErrorPage({ reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return (
    <main className="shell">
      <section className="status-card" aria-labelledby="error-title">
        <p className="eyebrow">Temporary issue</p>
        <h1 id="error-title" className="page-title">We couldn’t load this page</h1>
        <p className="description">Your access and documents are unchanged. Try again in a moment.</p>
        <div className="button-row">
          <button className="button button-primary" type="button" onClick={reset}>Try again</button>
          <Link className="button button-secondary" href="/workspaces">Workspace selection</Link>
        </div>
      </section>
    </main>
  );
}
