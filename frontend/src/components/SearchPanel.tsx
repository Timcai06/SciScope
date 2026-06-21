"use client";

import { FormEvent, useState } from "react";
import { searchPapers } from "@/api/client";
import type { SearchResponse } from "@/types";

const DEFAULT_QUERY = "graph neural network materials";

export function SearchPanel() {
  const [query, setQuery] = useState(DEFAULT_QUERY);
  const [response, setResponse] = useState<SearchResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const normalized = query.trim();
    if (!normalized || isLoading) {
      return;
    }
    try {
      setIsLoading(true);
      setError(null);
      setResponse(await searchPapers(normalized));
    } catch (searchError) {
      setError(searchError instanceof Error ? searchError.message : "Failed to search");
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <section className="border border-line bg-panel/90 p-4 sm:p-5">
      <div className="border-b border-line pb-4">
        <p className="text-xs font-medium uppercase tracking-[0.2em] text-cyanSoft">Hybrid Search</p>
        <h2 className="mt-2 text-base font-semibold text-silver">FTS + vector retrieval (RRF)</h2>
      </div>

      <form className="mt-4 flex gap-2" onSubmit={handleSubmit}>
        <input
          className="min-w-0 flex-1 border border-line bg-graphite px-3 py-2 text-sm text-silver outline-none focus:border-cyanSoft/60"
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Search the corpus..."
          value={query}
        />
        <button
          className="border border-cyanSoft/50 bg-cyanSoft/10 px-4 py-2 text-sm text-cyanSoft disabled:opacity-50"
          disabled={isLoading}
          type="submit"
        >
          {isLoading ? "Searching..." : "Search"}
        </button>
      </form>

      {error ? <p className="mt-4 border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-xs text-amber-300">{error}</p> : null}

      <ul className="mt-4 space-y-3">
        {response?.results.map((item) => (
          <li className="border border-line bg-graphite/60 p-3" key={item.paper_id}>
            <div className="flex items-start justify-between gap-3">
              <span className="text-sm font-medium text-silver">{item.title || item.paper_id}</span>
              <span className="shrink-0 text-[11px] text-silver/45">{item.year ?? "—"}</span>
            </div>
            <p className="mt-1 line-clamp-2 text-xs text-silver/55">{item.snippet}</p>
            <div className="mt-2 flex flex-wrap gap-2 text-[10px] uppercase tracking-wide text-cyanSoft/80">
              {item.matched_by.map((arm) => (
                <span className="border border-cyanSoft/30 px-1.5 py-0.5" key={arm}>{arm}</span>
              ))}
              <span className="text-silver/40">score {item.score.toFixed(4)}</span>
            </div>
          </li>
        ))}
      </ul>
      {response && response.results.length === 0 ? (
        <p className="mt-4 text-xs text-silver/50">No matches found.</p>
      ) : null}
    </section>
  );
}
