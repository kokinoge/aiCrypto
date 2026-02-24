"use client";

import { formatCurrency } from "@/lib/formatters";
import { EmptyState } from "@/components/ui/EmptyState";
import { SideBadge } from "@/components/ui/SideBadge";
import { TableWrap, TRow, Th, Td } from "@/components/ui/DataTable";
import type { Position } from "@/lib/types";

const pnlColor = (v: number) =>
  v >= 0 ? "var(--accent-green)" : "var(--accent-red)";
const pnlText = (v: number) =>
  `${v >= 0 ? "+" : "-"}$${formatCurrency(Math.abs(v))}`;

export function PositionsPreview({ positions }: { positions: Position[] }) {
  return (
    <section>
      <h2
        className="mb-3 text-[11px] font-medium uppercase tracking-wider"
        style={{ color: "var(--text-secondary)" }}
      >
        Open Positions
      </h2>
      {positions.length === 0 ? (
        <EmptyState>ポジションなし</EmptyState>
      ) : (
        <TableWrap>
          <table className="w-full text-sm">
            <thead>
              <TRow header>
                <Th>Coin</Th>
                <Th>Side</Th>
                <Th right>Size</Th>
                <Th right>Unrealized PnL</Th>
              </TRow>
            </thead>
            <tbody>
              {positions.slice(0, 5).map((p, i) => (
                <TRow key={i}>
                  <Td bold>{p.coin}</Td>
                  <Td><SideBadge side={p.side} /></Td>
                  <Td right mono>${formatCurrency(p.size)}</Td>
                  <Td right mono color={pnlColor(p.unrealized_pnl)}>
                    {pnlText(p.unrealized_pnl)}
                  </Td>
                </TRow>
              ))}
            </tbody>
          </table>
        </TableWrap>
      )}
    </section>
  );
}
