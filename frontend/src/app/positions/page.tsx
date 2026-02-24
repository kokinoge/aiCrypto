"use client";

import { useDashboard } from "@/hooks/useDashboard";
import { PageHeader } from "@/components/ui/PageHeader";
import { PositionsTable } from "@/components/positions/PositionsTable";

export default function PositionsPage() {
  const { data, isLoading } = useDashboard();

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-20 text-sm" style={{ color: "var(--text-muted)" }}>
        読み込み中...
      </div>
    );
  }

  const positions = data?.open_positions ?? [];

  return (
    <div className="space-y-4">
      <PageHeader title="ポジション" count={`${positions.length} 件`} />
      <PositionsTable positions={positions} />
    </div>
  );
}
