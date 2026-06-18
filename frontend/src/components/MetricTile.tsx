type MetricTileProps = {
  label: string;
  value: string;
  helper?: string;
  accent?: "cyan" | "signal" | "silver";
};

const accentClass = {
  cyan: "text-cyanSoft",
  signal: "text-signal",
  silver: "text-silver"
};

export function MetricTile({ label, value, helper, accent = "cyan" }: MetricTileProps) {
  return (
    <section className="min-h-36 border border-line bg-panel/90 p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.04)]">
      <div className="flex h-full flex-col justify-between gap-6">
        <p className="text-xs font-medium uppercase tracking-[0.2em] text-silver/55">{label}</p>
        <div>
          <p className={`text-3xl font-semibold leading-none sm:text-4xl ${accentClass[accent]}`}>{value}</p>
          {helper ? <p className="mt-3 text-xs leading-5 text-silver/45">{helper}</p> : null}
        </div>
      </div>
    </section>
  );
}
