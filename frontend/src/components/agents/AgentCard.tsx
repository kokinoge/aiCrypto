"use client";

import { formatPercent } from "@/lib/formatters";

export function AgentCard({
  name,
  stats,
}: {
  name: string;
  stats: { total: number; correct: number; accuracy: number };
}) {
  const pct = stats.total > 0 ? stats.accuracy * 100 : 0;
  const barColor =
    pct >= 70
      ? "var(--accent-green)"
      : pct >= 50
        ? "var(--accent-yellow)"
        : "var(--accent-red)";

  return (
    <div
      className="rounded-lg border p-4"
      style={{
        backgroundColor: "var(--bg-card)",
        borderColor: "var(--border-color)",
      }}
    >
      <p className="text-sm font-medium truncate">{name}</p>
      <div className="mt-3 flex items-baseline justify-between">
        <span
          className="text-2xl font-semibold font-mono"
          style={{ fontVariantNumeric: "tabular-nums", color: barColor }}
        >
          {formatPercent(pct, 1)}
        </span>
      </div>
      <div
        className="mt-3 h-1.5 w-full overflow-hidden rounded-full"
        style={{ backgroundColor: "var(--bg-hover)" }}
      >
        <div
          className="h-full rounded-full transition-all"
          style={{
            width: `${Math.min(pct, 100)}%`,
            backgroundColor: barColor,
          }}
        />
      </div>
      <div
        className="mt-3 flex justify-between text-[11px] font-mono"
        style={{ color: "var(--text-muted)", fontVariantNumeric: "tabular-nums" }}
      >
        <span>Total {stats.total}</span>
        <span>Correct {stats.correct}</span>
      </div>
    </div>
  );
}
