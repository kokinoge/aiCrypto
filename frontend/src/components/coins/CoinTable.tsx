"use client";

import { useState, useMemo, useCallback } from "react";
import { formatCurrency, formatPercent, formatNumber } from "@/lib/formatters";
import type { CoinData, ClosedTrade } from "@/lib/types";
import { TableWrap, TRow, Th, Td } from "@/components/ui/DataTable";
import { Toggle } from "./Toggle";
import { CoinDetail } from "./CoinDetail";

type SortKey = keyof CoinData;
type SortDir = "asc" | "desc";

const pnlColor = (v: number | null) =>
  v === null ? undefined : v >= 0 ? "var(--accent-green)" : "var(--accent-red)";

const columns: { key: SortKey; label: string; right?: boolean }[] = [
  { key: "coin", label: "Coin" },
  { key: "mark_price", label: "Price", right: true },
  { key: "funding_rate", label: "Funding Rate", right: true },
  { key: "open_interest", label: "OI", right: true },
  { key: "trade_count", label: "Trades", right: true },
  { key: "win_rate", label: "Win Rate", right: true },
  { key: "total_pnl", label: "PnL", right: true },
  { key: "blacklisted", label: "Status" },
];

export function CoinTable({
  coins,
  trades,
  search,
  onToggleBlacklist,
}: {
  coins: CoinData[];
  trades: ClosedTrade[];
  search: string;
  onToggleBlacklist: (coin: string, blacklisted: boolean) => void;
}) {
  const [sortKey, setSortKey] = useState<SortKey>("coin");
  const [sortDir, setSortDir] = useState<SortDir>("asc");
  const [selectedCoin, setSelectedCoin] = useState<string | null>(null);

  const handleSort = useCallback(
    (key: SortKey) => {
      if (sortKey === key) {
        setSortDir((d) => (d === "asc" ? "desc" : "asc"));
      } else {
        setSortKey(key);
        setSortDir("asc");
      }
    },
    [sortKey],
  );

  const filtered = useMemo(() => {
    const q = search.toLowerCase();
    const list = coins.filter((c) => c.coin.toLowerCase().includes(q));

    list.sort((a, b) => {
      const av = a[sortKey];
      const bv = b[sortKey];
      if (av === null || av === undefined) return 1;
      if (bv === null || bv === undefined) return -1;
      if (typeof av === "string" && typeof bv === "string") {
        return sortDir === "asc" ? av.localeCompare(bv) : bv.localeCompare(av);
      }
      if (typeof av === "boolean" && typeof bv === "boolean") {
        return sortDir === "asc" ? Number(av) - Number(bv) : Number(bv) - Number(av);
      }
      return sortDir === "asc"
        ? (av as number) - (bv as number)
        : (bv as number) - (av as number);
    });

    return list;
  }, [coins, search, sortKey, sortDir]);

  if (filtered.length === 0) {
    return (
      <div
        className="rounded-lg border py-12 text-center text-sm"
        style={{
          backgroundColor: "var(--bg-card)",
          borderColor: "var(--border-color)",
          color: "var(--text-muted)",
        }}
      >
        データなし
      </div>
    );
  }

  return (
    <TableWrap>
      <table className="w-full text-sm">
        <thead>
          <TRow header>
            {columns.map((col) => (
              <Th
                key={col.key}
                right={col.right}
                onClick={() => handleSort(col.key)}
                active={sortKey === col.key}
              >
                <span className="inline-flex items-center gap-1">
                  {col.label}
                  {sortKey === col.key && (
                    <span className="text-[10px]">
                      {sortDir === "asc" ? "▲" : "▼"}
                    </span>
                  )}
                </span>
              </Th>
            ))}
          </TRow>
        </thead>
        <tbody>
          {filtered.map((c) => (
            <>
              <TRow
                key={c.coin}
                onClick={() =>
                  setSelectedCoin(selectedCoin === c.coin ? null : c.coin)
                }
                style={{ opacity: c.blacklisted ? 0.4 : 1 }}
              >
                <Td bold>{c.coin}</Td>
                <Td right mono>
                  ${formatCurrency(c.mark_price, c.mark_price < 1 ? 6 : 2)}
                </Td>
                <Td right mono color={pnlColor(c.funding_rate)}>
                  {formatPercent(c.funding_rate * 100, 4)}
                </Td>
                <Td right mono>
                  ${formatNumber(c.open_interest)}
                </Td>
                <Td right mono>
                  {c.trade_count}
                </Td>
                <Td
                  right
                  mono
                  color={c.win_rate !== null ? pnlColor(c.win_rate - 0.5) : undefined}
                >
                  {c.win_rate !== null ? formatPercent(c.win_rate * 100, 1) : "—"}
                </Td>
                <Td right mono color={pnlColor(c.total_pnl)}>
                  {c.total_pnl !== null
                    ? `${c.total_pnl >= 0 ? "+" : "-"}$${formatCurrency(Math.abs(c.total_pnl))}`
                    : "—"}
                </Td>
                <Td>
                  <Toggle
                    blocked={c.blacklisted}
                    onToggle={() => onToggleBlacklist(c.coin, c.blacklisted)}
                  />
                </Td>
              </TRow>
              {selectedCoin === c.coin && (
                <CoinDetail
                  key={`${c.coin}-detail`}
                  coin={c}
                  trades={trades}
                  onClose={() => setSelectedCoin(null)}
                />
              )}
            </>
          ))}
        </tbody>
      </table>
    </TableWrap>
  );
}
