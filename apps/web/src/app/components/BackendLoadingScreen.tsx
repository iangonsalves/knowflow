export default function BackendLoadingScreen() {
  return (
    <main className="shell">
      <section className="status-card" aria-labelledby="backend-loading-title">
        <p className="eyebrow">KnowFlow portfolio demo</p>
        <h1 id="backend-loading-title">Starting demo environment…</h1>
        <p className="description" role="status" aria-live="polite">
          The backend may be waking up. KnowFlow will continue automatically when it is ready.
        </p>
        <div className="status-row"><span className="status-dot" aria-hidden="true" />Connecting securely to KnowFlow</div>
      </section>
    </main>
  );
}
