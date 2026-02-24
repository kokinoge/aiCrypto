"use client";

import { useDashboard } from "@/hooks/useDashboard";
import { PageHeader } from "@/components/ui/PageHeader";
import { TradesTable } from "@/components/history/TradesTable";

export default function HistoryPage() {
  const { data, isLoading } = useDashboard();

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-20 text-sm" style={{ color: "var(--text-muted)" }}>
        読み込み中...
      </div>
    );
  }

  const trades = data?.closed_trades ?? [];

  return (
    <div className="space-y-4">
      <PageHeader title="取引履歴" count={`${trades.length} 件`} />
      <TradesTable trades={trades} />
    </div>
  );
}
