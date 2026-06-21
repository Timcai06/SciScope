"use client";

import { useEffect, useState } from "react";
import { fetchTrends } from "@/api/client";
import type { TrendsResponse } from "@/types";

function pct(value: number | null): string {
  if (value === null || Number.isNaN(value)) {
    return "—";
  }
  return value.toFixed(4);
}

export function TrendsPanel() {
  const [data, setData] = useState<TrendsResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    fetchTrends()
      .then((response) => {
        if (active) {
          setData(response);
        }
      })
      .catch((trendError: unknown) => {
        if (active) {
          setError(trendError instanceof Error ? trendError.message : "Failed to load trends");
        }
      });
    return () => {
      active = false;
    };
  }, []);

  return (
    <section className="border border-line bg-panel/90 p-4 sm:p-5">
      <div className="border-b border-line pb-4">
        <p className="text-xs font-medium uppercase tracking-[0.2em] text-cyanSoft">Trend Forecast</p>
        <h2 className="mt-2 text-base font-semibold text-silver">Emerging research fronts</h2>
        {data ? (
          <p className="mt-1 text-[11px] text-silver/45">
            Fit {data.fit_years.join("–")} · forecast {data.forecast_year ?? "—"}
          </p>
        ) : null}
      </div>

      {error ? (
        <p className="mt-4 border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-xs text-amber-300">{error}</p>
      ) : null}

      <ul className="mt-4 space-y-2">
        {data?.top_emerging.slice(0, 12).map((item) => (
          <li className="flex items-center justify-between gap-3 border border-line bg-graphite/60 px-3 py-2" key={item.keyword}>
            <div className="min-w-0">
              <span className="block truncate text-sm text-silver">{item.keyword}</span>
              <span className="text-[10px] uppercase tracking-wide text-silver/40">{item.lifecycle_stage ?? ""}</span>
            </div>
            <div className="shrink-0 text-right text-[11px] text-silver/55">
              <span className="text-cyanSoft">slope {pct(item.trend_slope)}</span>
              <br />
              <span>→ {pct(item.forecast_normalized_df)}</span>
            </div>
          </li>
        ))}
      </ul>

      {data ? <p className="mt-4 text-[10px] leading-4 text-silver/40">{data.uncertainty_note}</p> : null}
    </section>
  );
}
