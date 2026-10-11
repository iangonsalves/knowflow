export default function Home() {
  return (
    <main className="shell">
      <section className="status-card" aria-labelledby="page-title">
        <p className="eyebrow">Development foundation</p>
        <h1 id="page-title">KnowFlow</h1>
        <p className="description">
          The application foundation is running. Product workflows will be added in approved milestones.
        </p>
        <div className="status-row">
          <span className="status-dot" aria-hidden="true" />
          <span>Frontend online</span>
        </div>
      </section>
    </main>
  );
}
