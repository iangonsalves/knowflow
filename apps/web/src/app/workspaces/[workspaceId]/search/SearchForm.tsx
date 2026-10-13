"use client";

import { FormEvent, useState } from "react";
import Link from "next/link";
import { safeAskErrorMessage } from "@/lib/ui-helpers.mjs";

type EvidenceItem = {
  chunk_id: string;
  document_id: string;
  document_title: string;
  text: string;
  page_start: number;
  page_end: number;
  source_path: string;
  retrieval_rank: number;
};

type AskResponse = {
  question: string;
  evidence_state: "evidence_found" | "weak_evidence" | "no_evidence";
  message: string;
  best_evidence: EvidenceItem | null;
  supporting_evidence: EvidenceItem[];
  related_evidence: EvidenceItem[];
};

export default function SearchForm({ workspaceId, hasReadyDocuments }: { workspaceId: string; hasReadyDocuments: boolean }) {
  const [question, setQuestion] = useState("");
  const [response, setResponse] = useState<AskResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const normalized = question.trim();
    if (!normalized || loading) return;
    setLoading(true);
    setError(null);
    setResponse(null);
    try {
      const result = await fetch(
        `/api/workspaces/${encodeURIComponent(workspaceId)}/ask`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ query: normalized }),
          cache: "no-store",
        },
      );
      const body = (await result.json()) as AskResponse & {
        message?: string;
        error?: { message?: string };
      };
      if (!result.ok) {
        setError(safeAskErrorMessage(result.status));
        return;
      }
      setResponse(body);
    } catch {
      setError("Ask KnowFlow is temporarily unavailable. Try again shortly.");
    } finally {
      setLoading(false);
    }
  }

  function evidenceCard(item: EvidenceItem, label: string) {
    const pageLabel = item.page_start === item.page_end
      ? `Page ${item.page_start}`
      : `Pages ${item.page_start}–${item.page_end}`;
    return (
      <article className="evidence-card" key={item.chunk_id}>
        <p className="evidence-label">{label}</p>
        <blockquote>{item.text}</blockquote>
        <div className="evidence-source">
          <span><strong>{item.document_title}</strong><span className="page-reference">{pageLabel}</span></span>
          <Link className="button button-secondary" href={item.source_path}>Open source</Link>
        </div>
      </article>
    );
  }

  return (
    <>
      <section className="panel ask-panel" aria-labelledby="ask-title">
        <form onSubmit={submit} className="search-form" aria-busy={loading}>
          <h2 id="ask-title">What would you like to know?</h2>
          <label className="field-label" htmlFor="ask-question">Your question</label>
          <div className="input-row">
            <input
              id="ask-question"
              name="question"
              type="text"
              maxLength={2000}
              required
              value={question}
              onChange={(event) => setQuestion(event.currentTarget.value)}
              placeholder="Ask about a policy, process, or requirement…"
              aria-describedby="ask-help ask-count"
            />
            <button className="button button-primary" type="submit" disabled={loading || !question.trim()}>
              {loading ? "Finding evidence…" : "Ask KnowFlow"}
            </button>
          </div>
          <div className="ask-helper-row"><p id="ask-help" className="workspace-meta">KnowFlow retrieves source passages. It does not generate or paraphrase answers.</p><span id="ask-count" className="workspace-meta">{question.length}/2000</span></div>
        </form>
      </section>

      {!response && !loading && hasReadyDocuments ? <section className="example-prompts" aria-label="Example questions"><p className="workspace-meta">Try a question such as</p><ul><li>What does our policy say about remote access?</li><li>When should incidents be reported?</li><li>What approvals are required?</li></ul></section> : null}

      {error ? <p className="notice notice-error" role="alert">{error}</p> : null}
      {response ? <section className="panel evidence-results" aria-live="polite" aria-labelledby="evidence-title">
        <div className="panel-heading">
          <div>
            <p className="eyebrow">Question</p>
            <h2 id="evidence-title">{response.question}</h2>
            <p>{response.message}</p>
          </div>
        </div>
        {response.evidence_state === "evidence_found" && response.best_evidence ? <>
          {evidenceCard(response.best_evidence, "Best matching evidence")}
          {response.supporting_evidence.length ? <div className="supporting-evidence">
            <h3>Supporting evidence</h3>
            {response.supporting_evidence.map((item) => evidenceCard(item, "Relevant passage"))}
          </div> : null}
        </> : response.evidence_state === "weak_evidence" ? <>
          {response.related_evidence.length ? <div className="supporting-evidence">
            <h3>Potentially related passages</h3>
            {response.related_evidence.map((item) => evidenceCard(item, "Potentially related"))}
          </div> : <p className="empty-state">No substantive related passages are available.</p>}
        </> : <p className="empty-state">No relevant passages are available. Check that documents in this workspace have finished processing.</p>}
      </section> : null}
    </>
  );
}
