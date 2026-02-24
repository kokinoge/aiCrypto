"use client";

import { Card } from "@/components/ui/Card";
import { formatCurrency, formatPercent } from "@/lib/formatters";
import type { DashboardData } from "@/lib/types";

const pnlColor = (v: number) =>
  v >= 0 ? "var(--accent-green)" : "var(--accent-red)";
const pnlText = (v: number, prefix = "") =>
  `${v >= 0 ? "+" : "-"}${prefix}${formatCurrency(Math.abs(v))}`;

export function StatCards({ data }: { data: DashboardData }) {
  return (
    <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
      <Card label="Equity" value={`$${formatCurrency(data.equity)}`} />
      <Card
        label="PnL"
        value={pnlText(data.total_pnl, "$")}
        valueColor={pnlColor(data.total_pnl)}
      />
      <Card
        label="Return"
        value={formatPercent(data.return_pct)}
        valueColor={pnlColor(data.return_pct)}
      />
      <Card
        label="Win Rate"
        value={formatPercent(data.win_rate.win_rate, 1)}
        sub={`${data.win_rate.wins}W / ${data.win_rate.losses}L`}
      />
    </div>
  );
}
