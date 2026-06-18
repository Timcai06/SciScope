import type { ReactNode } from "react";

const navItems = ["Research Radar", "Evidence Chat", "Knowledge Graph", "Collaboration Map", "Report Studio"];

export function AppShell({ children }: { children: ReactNode }) {
  return (
    <main className="min-h-screen bg-graphite text-silver">
      <div className="grid min-h-screen lg:grid-cols-[16rem_minmax(0,1fr)]">
        <aside className="border-b border-line bg-[#15181d] px-5 py-5 lg:border-b-0 lg:border-r">
          <div className="flex items-center justify-between gap-4 lg:block">
            <div>
              <div className="text-lg font-semibold tracking-wide text-silver">SciScope</div>
              <p className="mt-2 max-w-52 text-xs leading-5 text-silver/50">Research literature intelligence workspace</p>
            </div>
            <div className="border border-cyanSoft/30 px-2 py-1 text-[11px] uppercase tracking-[0.18em] text-cyanSoft lg:mt-6 lg:inline-block">
              Local Lab
            </div>
          </div>

          <nav aria-label="SciScope workspace" className="mt-6 flex gap-2 overflow-x-auto lg:mt-8 lg:block lg:space-y-2">
            {navItems.map((item, index) => (
              <div
                className={`whitespace-nowrap border px-3 py-2 text-sm ${
                  index === 0 ? "border-cyanSoft/50 bg-cyanSoft/10 text-cyanSoft" : "border-line text-silver/62"
                }`}
                key={item}
              >
                {item}
              </div>
            ))}
          </nav>
        </aside>

        <section className="min-w-0 px-4 py-5 sm:px-6 lg:px-8 lg:py-8">
          <header className="mb-6 flex flex-col gap-4 border-b border-line pb-5 md:flex-row md:items-end md:justify-between">
            <div>
              <p className="text-xs font-medium uppercase tracking-[0.22em] text-cyanSoft">Research Command Center</p>
              <h1 className="mt-3 text-2xl font-semibold leading-tight text-silver sm:text-3xl">Literature Intelligence Dashboard</h1>
            </div>
            <div className="grid grid-cols-2 gap-2 text-xs text-silver/50 sm:flex sm:text-right">
              <span className="border border-line px-3 py-2">DeepSeek-ready</span>
              <span className="border border-line px-3 py-2">Evidence-first</span>
            </div>
          </header>
          {children}
        </section>
      </div>
    </main>
  );
}
