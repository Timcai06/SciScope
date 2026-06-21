import { AppShell } from "@/components/AppShell";
import { DashboardOverview } from "@/components/DashboardOverview";
import { EvidenceChat } from "@/components/EvidenceChat";
import { GraphPanel } from "@/components/GraphPanel";
import { RecommendPanel } from "@/components/RecommendPanel";
import { SearchPanel } from "@/components/SearchPanel";
import { TrendsPanel } from "@/components/TrendsPanel";

export default function HomePage() {
  return (
    <AppShell>
      <div className="space-y-4">
        <DashboardOverview />
        <EvidenceChat />
        <div className="grid gap-4 xl:grid-cols-2">
          <SearchPanel />
          <TrendsPanel />
        </div>
        <div className="grid gap-4 xl:grid-cols-2">
          <RecommendPanel />
          <GraphPanel />
        </div>
      </div>
    </AppShell>
  );
}
