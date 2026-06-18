"use client";

import { useEffect, useMemo, useState } from "react";
import { fetchDashboardOverview } from "@/api/client";
import type { DashboardOverview as DashboardOverviewType } from "@/types";
import { KeywordPanel } from "./KeywordPanel";
import { MetricTile } from "./MetricTile";
import { TrendChart } from "./TrendChart";

const EMPTY_OVERVIEW: DashboardOverviewType = {
  total_papers: 0,
  year_range: {
    start: null,
    end: null
  },
  publication_trend: [],
  field_distribution: [],
  top_keywords: [],
  collaboration_edges: []
};

function formatYearRange(overview: DashboardOverviewType): string {
  const { start, end } = overview.year_range;

  if (start === null || end === null) {
    return "Unknown";
  }

  return start === end ? String(start) : `${start}-${end}`;
}

function DashboardSkeleton() {
  return (
    <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_360px]">
      <div className="space-y-4">
        <div className="grid gap-4 md:grid-cols-3">
          {[0, 1, 2].map((item) => (
            <div className="h-36 animate-pulse border border-line bg-panel/70" key={item} />
          ))}
        </div>
        <div className="h-[25rem] animate-pulse border border-line bg-panel/70" />
      </div>
      <div className="space-y-4">
        <div className="h-80 animate-pulse border border-line bg-panel/70" />
        <div className="h-56 animate-pulse border border-line bg-panel/70" />
      </div>
    </div>
  );
}

type FieldDistributionProps = {
  fields: DashboardOverviewType["field_distribution"];
};

function FieldDistribution({ fields }: FieldDistributionProps) {
  const max = Math.max(...fields.map((item) => item.count), 1);

  return (
    <section className="border border-line bg-panel/90 p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.04)] sm:p-5">
      <div className="border-b border-line pb-4">
        <h2 className="text-base font-semibold text-silver">Field Distribution</h2>
        <p className="mt-1 text-xs text-silver/45">Disciplinary spread for loaded papers.</p>
      </div>

      {fields.length > 0 ? (
        <div className="mt-5 space-y-4">
          {fields.map((item) => {
            const width = Math.max((item.count / max) * 100, 10);

            return (
              <div className="grid gap-2" key={item.field}>
                <div className="flex items-center justify-between gap-4 text-sm">
                  <span className="min-w-0 truncate text-silver/75" title={item.field}>
                    {item.field}
                  </span>
                  <span className="font-semibold text-signal">{item.count}</span>
                </div>
                <div className="h-1.5 bg-graphite">
                  <div className="h-full bg-signal/85" style={{ width: `${width}%` }} />
                </div>
              </div>
            );
          })}
        </div>
      ) : (
        <div className="mt-5 flex min-h-32 items-center justify-center border border-dashed border-line bg-graphite/40 text-sm text-silver/45">
          No field distribution
        </div>
      )}
    </section>
  );
}

type CollaborationPreviewProps = {
  edgeCount: number;
};

function CollaborationPreview({ edgeCount }: CollaborationPreviewProps) {
  return (
    <section className="border border-line bg-panel/90 p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.04)] sm:p-5">
      <p className="text-xs font-medium uppercase tracking-[0.2em] text-silver/55">Collaboration Graph</p>
      <div className="mt-5 grid grid-cols-[auto_1fr] gap-4">
        <div className="flex h-16 w-16 items-center justify-center border border-line bg-graphite text-2xl font-semibold text-signal">
          {edgeCount}
        </div>
        <div>
          <h2 className="text-base font-semibold text-silver">Author edges detected</h2>
          <p className="mt-2 text-sm leading-6 text-silver/50">
            Network detail is ready for the next visualization layer without blocking this dashboard.
          </p>
        </div>
      </div>
    </section>
  );
}

export function DashboardOverview() {
  const [overview, setOverview] = useState<DashboardOverviewType>(EMPTY_OVERVIEW);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let isMounted = true;

    async function loadOverview() {
      try {
        setIsLoading(true);
        setError(null);
        const dashboardOverview = await fetchDashboardOverview();

        if (isMounted) {
          setOverview(dashboardOverview);
        }
      } catch (loadError) {
        if (isMounted) {
          setOverview(EMPTY_OVERVIEW);
          setError(loadError instanceof Error ? loadError.message : "Failed to load dashboard overview");
        }
      } finally {
        if (isMounted) {
          setIsLoading(false);
        }
      }
    }

    void loadOverview();

    return () => {
      isMounted = false;
    };
  }, []);

  const yearRange = useMemo(() => formatYearRange(overview), [overview]);

  if (isLoading) {
    return <DashboardSkeleton />;
  }

  return (
    <div className="space-y-4">
      {error ? (
        <section className="border border-signal/50 bg-signal/10 p-4 text-sm leading-6 text-silver/80">
          <span className="font-semibold text-signal">Dashboard API unavailable.</span>{" "}
          Showing an empty command-center state until the backend is running. {error}
        </section>
      ) : null}

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_360px]">
        <div className="space-y-4">
          <div className="grid gap-4 md:grid-cols-3">
            <MetricTile
              helper="Papers currently indexed for analytics and evidence retrieval."
              label="Papers"
              value={String(overview.total_papers)}
            />
            <MetricTile helper="Coverage window detected from publication metadata." label="Years" value={yearRange} accent="silver" />
            <MetricTile
              helper="Weighted author links available for graph exploration."
              label="Collaborations"
              value={String(overview.collaboration_edges.length)}
              accent="signal"
            />
          </div>
          <TrendChart data={overview.publication_trend} />
        </div>

        <div className="space-y-4">
          <KeywordPanel keywords={overview.top_keywords} />
          <FieldDistribution fields={overview.field_distribution} />
          <CollaborationPreview edgeCount={overview.collaboration_edges.length} />
        </div>
      </div>
    </div>
  );
}
