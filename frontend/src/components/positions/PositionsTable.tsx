"use client";

import { formatCurrency } from "@/lib/formatters";
import { EmptyState } from "@/components/ui/EmptyState";
import { SideBadge } from "@/components/ui/SideBadge";
import { TableWrap, TRow, Th, Td } from "@/components/ui/DataTable";
import type { Position } from "@/lib/types";

const pnlColor = (v: number) =>
  v >= 0 ? "var(--accent-green)" : "var(--accent-red)";

export function PositionsTable({ positions }: { positions: Position[] }) {
  if (positions.length === 0) {
    return <EmptyState>オープンポジションなし</EmptyState>;
  }

  return (
    <TableWrap>
      <table className="w-full text-sm">
        <thead>
          <TRow header>
            <Th>Coin</Th>
            <Th>Side</Th>
            <Th right>Entry Price</Th>
            <Th right>Current Price</Th>
            <Th right>Size</Th>
            <Th right>Unrealized PnL</Th>
            <Th right>Leverage</Th>
          </TRow>
        </thead>
        <tbody>
          {positions.map((p, i) => (
            <TRow key={i}>
              <Td bold>{p.coin}</Td>
              <Td><SideBadge side={p.side} /></Td>
              <Td right mono>${formatCurrency(p.entry_price)}</Td>
              <Td right mono>${formatCurrency(p.current_price)}</Td>
              <Td right mono>${formatCurrency(p.size)}</Td>
              <Td right mono color={pnlColor(p.unrealized_pnl)}>
                {p.unrealized_pnl >= 0 ? "+" : "-"}${formatCurrency(Math.abs(p.unrealized_pnl))}
              </Td>
              <Td right mono>{p.leverage}x</Td>
            </TRow>
          ))}
        </tbody>
      </table>
    </TableWrap>
  );
}
