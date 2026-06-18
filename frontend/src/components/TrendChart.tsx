import type { TrendPoint } from "@/types";

type TrendChartProps = {
  data: TrendPoint[];
};

export function TrendChart({ data }: TrendChartProps) {
  const max = Math.max(...data.map((item) => item.count), 1);

  return (
    <section className="border border-line bg-panel/90 p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.04)] sm:p-5">
      <div className="flex flex-col gap-2 border-b border-line pb-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h2 className="text-base font-semibold text-silver">Publication Trend</h2>
          <p className="mt-1 text-xs text-silver/45">Annual paper volume in the active corpus.</p>
        </div>
        <span className="text-xs uppercase tracking-[0.22em] text-cyanSoft/80">Temporal Rail</span>
      </div>

      {data.length > 0 ? (
        <div className="mt-6 flex h-64 items-end gap-2 overflow-x-auto pb-1 sm:gap-3">
          {data.map((item) => {
            const height = Math.max((item.count / max) * 100, 8);

            return (
              <div className="flex min-w-12 flex-1 flex-col items-center gap-3" key={item.year}>
                <div className="flex h-52 w-full items-end border-b border-line/80 bg-graphite/50">
                  <div
                    aria-label={`${item.year}: ${item.count} papers`}
                    className="w-full bg-cyanSoft/85 shadow-[0_0_20px_rgba(107,214,214,0.16)] transition-colors hover:bg-cyanSoft"
                    style={{ height: `${height}%` }}
                    title={`${item.year}: ${item.count}`}
                  />
                </div>
                <div className="text-center">
                  <p className="text-xs font-medium text-silver/70">{item.year}</p>
                  <p className="mt-1 text-[11px] text-cyanSoft/70">{item.count}</p>
                </div>
              </div>
            );
          })}
        </div>
      ) : (
        <div className="mt-6 flex h-64 items-center justify-center border border-dashed border-line bg-graphite/40 text-sm text-silver/45">
          No publication trend data
        </div>
      )}
    </section>
  );
}
