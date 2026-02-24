"use client";

import { formatCurrency } from "@/lib/formatters";
import { EmptyState } from "@/components/ui/EmptyState";
import { SideBadge } from "@/components/ui/SideBadge";
import { TableWrap, TRow, Th, Td } from "@/components/ui/DataTable";
import type { ClosedTrade } from "@/lib/types";

const pnlColor = (v: number) =>
  v >= 0 ? "var(--accent-green)" : "var(--accent-red)";

function formatTime(ts: number): string {
  return new Date(ts * 1000).toLocaleString("ja-JP", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function TradesTable({ trades }: { trades: ClosedTrade[] }) {
  const sorted = [...trades].sort((a, b) => b.closed_at - a.closed_at);

  if (sorted.length === 0) {
    return <EmptyState>取引履歴なし</EmptyState>;
  }

  return (
    <TableWrap>
      <table className="w-full text-sm">
        <thead>
          <TRow header>
            <Th>Coin</Th>
            <Th>Side</Th>
            <Th right>Entry</Th>
            <Th right>Exit</Th>
            <Th right>Size</Th>
            <Th right>PnL</Th>
            <Th>Reason</Th>
            <Th>Time</Th>
          </TRow>
        </thead>
        <tbody>
          {sorted.map((t, i) => (
            <TRow key={i}>
              <Td bold>{t.coin}</Td>
              <Td><SideBadge side={t.side} /></Td>
              <Td right mono>${formatCurrency(t.entry)}</Td>
              <Td right mono>${formatCurrency(t.exit)}</Td>
              <Td right mono>${formatCurrency(t.size)}</Td>
              <Td right mono color={pnlColor(t.pnl)}>
                {t.pnl >= 0 ? "+" : "-"}${formatCurrency(Math.abs(t.pnl))}
              </Td>
              <Td secondary className="text-xs">{t.reason}</Td>
              <Td secondary className="text-xs font-mono whitespace-nowrap">{formatTime(t.closed_at)}</Td>
            </TRow>
          ))}
        </tbody>
      </table>
    </TableWrap>
  );
}
