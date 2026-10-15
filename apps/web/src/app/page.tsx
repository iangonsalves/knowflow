import { withAuth } from "@workos-inc/authkit-nextjs";
import { redirect } from "next/navigation";

export default async function Home() {
  const { user } = await withAuth();
  if (user) redirect("/workspaces");

  return (
    <main className="shell">
      <section className="status-card" aria-labelledby="page-title">
        <p className="eyebrow">Business knowledge workspace</p>
        <h1 id="page-title">KnowFlow</h1>
        <p className="description">
          Organize private business documents, then ask questions and explore the source passages
          with page citations. KnowFlow finds evidence from your documents without generating or
          paraphrasing answers.
        </p>
        <div className="button-row">
          <a className="button button-primary" href="/sign-in">Sign in</a>
          <a className="button button-secondary" href="/sign-up">Create account</a>
        </div>
      </section>
    </main>
  );
}
