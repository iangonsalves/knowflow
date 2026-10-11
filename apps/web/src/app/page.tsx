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
          Organize company knowledge in workspaces. This M2 preview demonstrates secure sign-in,
          workspace ownership, and member access.
        </p>
        <div className="button-row">
          <a className="button button-primary" href="/sign-in">Sign in</a>
          <a className="button button-secondary" href="/sign-up">Create account</a>
        </div>
      </section>
    </main>
  );
}
