import { AppShell } from "@/components/AppShell";
import { DashboardOverview } from "@/components/DashboardOverview";
import { EvidenceChat } from "@/components/EvidenceChat";

export default function HomePage() {
  return (
    <AppShell>
      <div className="space-y-4">
        <DashboardOverview />
        <EvidenceChat />
      </div>
    </AppShell>
  );
}
