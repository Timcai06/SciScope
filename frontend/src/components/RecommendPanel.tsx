"use client";

import { FormEvent, useState } from "react";
import { fetchRecommendations } from "@/api/client";
import type { RecommendResponse } from "@/types";

export function RecommendPanel() {
  const [paperId, setPaperId] = useState("");
  const [data, setData] = useState<RecommendResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const normalized = paperId.trim();
    if (!normalized || isLoading) {
      return;
    }
    try {
      setIsLoading(true);
      setError(null);
      setData(await fetchRecommendations(normalized));
    } catch (recError) {
      setError(recError instanceof Error ? recError.message : "Failed to load recommendations");
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <section className="border border-line bg-panel/90 p-4 sm:p-5">
      <div className="border-b border-line pb-4">
        <p className="text-xs font-medium uppercase tracking-[0.2em] text-cyanSoft">Paper Recommendations</p>
        <h2 className="mt-2 text-base font-semibold text-silver">Explainable related work</h2>
      </div>

      <form className="mt-4 flex gap-2" onSubmit={handleSubmit}>
        <input
          className="min-w-0 flex-1 border border-line bg-graphite px-3 py-2 text-sm text-silver outline-none focus:border-cyanSoft/60"
          onChange={(event) => setPaperId(event.target.value)}
          placeholder="Seed paper id (e.g. W1987576086)"
          value={paperId}
        />
        <button
          className="border border-cyanSoft/50 bg-cyanSoft/10 px-4 py-2 text-sm text-cyanSoft disabled:opacity-50"
          disabled={isLoading}
          type="submit"
        >
          {isLoading ? "..." : "Recommend"}
        </button>
      </form>

      {error ? <p className="mt-4 border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-xs text-amber-300">{error}</p> : null}

      <ul className="mt-4 space-y-3">
        {data?.recommendations.map((rec) => (
          <li className="border border-line bg-graphite/60 p-3" key={rec.paper_id}>
            <div className="flex items-start justify-between gap-3">
              <span className="text-sm font-medium text-silver">{rec.title || rec.paper_id}</span>
              <span className="shrink-0 text-[11px] text-silver/45">{rec.year ?? "—"}</span>
            </div>
            <div className="mt-2 flex flex-wrap gap-2 text-[10px] text-silver/55">
              <span className="border border-cyanSoft/30 px-1.5 py-0.5 text-cyanSoft">sim {rec.semantic_similarity.toFixed(3)}</span>
              {Object.entries(rec.factors).map(([name, value]) => (
                <span className="border border-line px-1.5 py-0.5" key={name}>
                  {name} {value.toFixed(3)}
                </span>
              ))}
            </div>
            {rec.shared_keywords.length > 0 ? (
              <p className="mt-2 text-[11px] text-silver/45">shared: {rec.shared_keywords.join(", ")}</p>
            ) : null}
          </li>
        ))}
      </ul>
    </section>
  );
}
