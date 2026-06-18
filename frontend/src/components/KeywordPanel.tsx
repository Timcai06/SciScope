import type { KeywordCount } from "@/types";

type KeywordPanelProps = {
  keywords: KeywordCount[];
};

export function KeywordPanel({ keywords }: KeywordPanelProps) {
  const max = Math.max(...keywords.map((item) => item.count), 1);

  return (
    <section className="border border-line bg-panel/90 p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.04)] sm:p-5">
      <div className="border-b border-line pb-4">
        <h2 className="text-base font-semibold text-silver">Rising Signals</h2>
        <p className="mt-1 text-xs text-silver/45">Keyword concentration across the current corpus.</p>
      </div>

      {keywords.length > 0 ? (
        <div className="mt-5 space-y-3">
          {keywords.map((item) => {
            const width = Math.max((item.count / max) * 100, 12);

            return (
              <div className="grid gap-2" key={item.keyword}>
                <div className="flex items-center justify-between gap-4 text-sm">
                  <span className="min-w-0 truncate text-silver/78" title={item.keyword}>
                    {item.keyword}
                  </span>
                  <span className="text-xs font-semibold text-cyanSoft">{item.count}</span>
                </div>
                <div className="h-1.5 bg-graphite">
                  <div className="h-full bg-cyanSoft/80" style={{ width: `${width}%` }} />
                </div>
              </div>
            );
          })}
        </div>
      ) : (
        <div className="mt-5 flex min-h-40 items-center justify-center border border-dashed border-line bg-graphite/40 text-sm text-silver/45">
          No keyword signals
        </div>
      )}
    </section>
  );
}
