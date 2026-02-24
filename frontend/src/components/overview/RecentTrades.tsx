"use client";

import { formatCurrency } from "@/lib/formatters";
import { EmptyState } from "@/components/ui/EmptyState";
import { SideBadge } from "@/components/ui/SideBadge";
import { TableWrap, TRow, Th, Td } from "@/components/ui/DataTable";
import type { ClosedTrade } from "@/lib/types";

const pnlColor = (v: number) =>
  v >= 0 ? "var(--accent-green)" : "var(--accent-red)";
const pnlText = (v: number) =>
  `${v >= 0 ? "+" : "-"}$${formatCurrency(Math.abs(v))}`;

export function RecentTrades({ trades }: { trades: ClosedTrade[] }) {
  return (
    <section>
      <h2
        className="mb-3 text-[11px] font-medium uppercase tracking-wider"
        style={{ color: "var(--text-secondary)" }}
      >
        Recent Trades
      </h2>
      {trades.length === 0 ? (
        <EmptyState>取引履歴なし</EmptyState>
      ) : (
        <TableWrap>
          <table className="w-full text-sm">
            <thead>
              <TRow header>
                <Th>Coin</Th>
                <Th>Side</Th>
                <Th right>PnL</Th>
                <Th>Reason</Th>
              </TRow>
            </thead>
            <tbody>
              {trades.slice(0, 10).map((t, i) => (
                <TRow key={i}>
                  <Td bold>{t.coin}</Td>
                  <Td><SideBadge side={t.side} /></Td>
                  <Td right mono color={pnlColor(t.pnl)}>{pnlText(t.pnl)}</Td>
                  <Td secondary>{t.reason}</Td>
                </TRow>
              ))}
            </tbody>
          </table>
        </TableWrap>
      )}
    </section>
  );
}
