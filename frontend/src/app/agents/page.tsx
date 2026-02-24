"use client";

import { useDashboard } from "@/hooks/useDashboard";
import { PageHeader } from "@/components/ui/PageHeader";
import { EmptyState } from "@/components/ui/EmptyState";
import { AgentCard } from "@/components/agents/AgentCard";

export default function AgentsPage() {
  const { data, isLoading } = useDashboard();

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-20 text-sm" style={{ color: "var(--text-muted)" }}>
        読み込み中...
      </div>
    );
  }

  const agents = data?.agent_accuracy ? Object.entries(data.agent_accuracy) : [];

  return (
    <div className="space-y-4">
      <PageHeader title="エージェント精度" />
      {agents.length === 0 ? (
        <EmptyState>エージェントデータなし</EmptyState>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {agents.map(([name, stats]) => (
            <AgentCard key={name} name={name} stats={stats} />
          ))}
        </div>
      )}
    </div>
  );
}
