"use client";

import { useDashboard } from "@/hooks/useDashboard";
import { StatCards } from "@/components/overview/StatCards";
import { PositionsPreview } from "@/components/overview/PositionsPreview";
import { RecentTrades } from "@/components/overview/RecentTrades";

export default function OverviewPage() {
  const { data, isLoading } = useDashboard();

  if (isLoading) {
    return (
      <div
        className="flex items-center justify-center py-20 text-sm"
        style={{ color: "var(--text-muted)" }}
      >
        読み込み中...
      </div>
    );
  }

  if (!data) {
    return (
      <div
        className="flex items-center justify-center py-20 text-sm"
        style={{ color: "var(--text-muted)" }}
      >
        データなし
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <StatCards data={data} />
      <PositionsPreview positions={data.open_positions} />
      <RecentTrades trades={data.closed_trades} />
    </div>
  );
}
