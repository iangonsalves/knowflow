"use client";

import { FormEvent, useState } from "react";
import Link from "next/link";

type SearchResult = {
  chunk_id: string;
  document_id: string;
  document_filename: string;
  chunk_index: number;
  text: string;
  page_start: number;
  page_end: number;
  rank: number;
  rrf_score: number;
  keyword_rank: number | null;
  vector_rank: number | null;
};

export default function SearchForm({ workspaceId }: { workspaceId: string }) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SearchResult[]>([]);
  const [submittedQuery, setSubmittedQuery] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const normalized = query.trim();
    if (!normalized) return;
    setLoading(true);
    setError(null);
    setSubmittedQuery(normalized);
    try {
      const response = await fetch(
        `/api/workspaces/${encodeURIComponent(workspaceId)}/search`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ query: normalized }),
          cache: "no-store",
        },
      );
      const body = (await response.json()) as {
        results?: SearchResult[];
        message?: string;
        detail?: { message?: string };
      };
      if (!response.ok) {
        setResults([]);
        setError(
          response.status === 503
            ? "Search is unavailable until the embedding provider is configured."
            : body.detail?.message ?? body.message ?? "Search could not be completed.",
        );
        return;
      }
      setResults(body.results ?? []);
    } catch {
      setResults([]);
      setError("Search is temporarily unavailable. Try again shortly.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <>
      <section className="panel" aria-labelledby="search-title">
        <form onSubmit={submit} className="search-form">
          <label className="field-label" htmlFor="search-query">What are you looking for?</label>
          <div className="input-row">
            <input
              id="search-query"
              name="q"
              type="search"
              maxLength={10000}
              required
              value={query}
              onChange={(event) => setQuery(event.currentTarget.value)}
              placeholder="How much annual leave do employees receive?"
            />
            <button className="button button-primary" type="submit" disabled={loading}>
              {loading ? "Searching…" : "Search"}
            </button>
          </div>
        </form>
      </section>
      {error ? <p className="notice notice-error" role="alert">{error}</p> : null}
      {submittedQuery ? <section className="panel" aria-labelledby="results-title">
        <div className="panel-heading"><div><h2 id="results-title">Results</h2><p>{results.length} matching {results.length === 1 ? "passage" : "passages"} for “{submittedQuery}”</p></div></div>
        {results.length ? <ol className="search-results">{results.map((result) => (
          <li key={result.chunk_id} className="search-result">
            <div className="search-result-heading"><span className="search-rank">{result.rank}</span><Link className="document-title" href={`/workspaces/${encodeURIComponent(workspaceId)}/documents/${result.document_id}`}>{result.document_filename}</Link><span className="page-reference">Page{result.page_start === result.page_end ? ` ${result.page_start}` : `s ${result.page_start}–${result.page_end}`}</span></div>
            <p className="search-result-text">{result.text}</p>
            <p className="workspace-meta">Hybrid score {result.rrf_score.toFixed(4)} · Keyword rank {result.keyword_rank ?? "—"} · Semantic rank {result.vector_rank ?? "—"}</p>
          </li>
        ))}</ol> : <p className="empty-state">No matching passages were found in ready documents in this workspace.</p>}
      </section> : null}
    </>
  );
}
