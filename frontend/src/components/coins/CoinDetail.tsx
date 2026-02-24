"use client";

import { formatCurrency, formatPercent, formatNumber } from "@/lib/formatters";
import type { CoinData, ClosedTrade } from "@/lib/types";

const pnlColor = (v: number | null) =>
  v === null ? undefined : v >= 0 ? "var(--accent-green)" : "var(--accent-red)";

export function CoinDetail({
  coin,
  trades,
  onClose,
}: {
  coin: CoinData;
  trades: ClosedTrade[];
  onClose: () => void;
}) {
  const coinTrades = trades.filter(
    (t) => t.coin.toUpperCase() === coin.coin.toUpperCase(),
  );

  return (
    <tr>
      <td
        colSpan={8}
        className="px-0 py-0"
        style={{ backgroundColor: "var(--bg-secondary)" }}
      >
        <div className="px-6 py-5 space-y-5">
          {/* Header */}
          <div className="flex items-center justify-between">
            <h3 className="text-base font-semibold tracking-tight">
              {coin.coin}{" "}
              <span
                className="text-xs font-normal"
                style={{ color: "var(--text-muted)" }}
              >
                詳細分析
              </span>
            </h3>
            <button
              onClick={onClose}
              className="text-xs px-3 py-1 rounded-md transition-colors"
              style={{
                backgroundColor: "var(--bg-hover)",
                color: "var(--text-secondary)",
              }}
            >
              閉じる
            </button>
          </div>

          {/* Market Data Cards */}
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <MiniCard label="Price" value={`$${formatCurrency(coin.mark_price, coin.mark_price < 1 ? 6 : 2)}`} />
            <MiniCard
              label="Funding Rate"
              value={formatPercent(coin.funding_rate * 100, 4)}
              color={pnlColor(coin.funding_rate)}
            />
            <MiniCard label="Open Interest" value={`$${formatNumber(coin.open_interest)}`} />
            <MiniCard
              label="Confidence Adj."
              value={coin.confidence_adjustment !== 0 ? `${coin.confidence_adjustment > 0 ? "+" : ""}${(coin.confidence_adjustment * 100).toFixed(1)}%` : "0.0%"}
              color={pnlColor(coin.confidence_adjustment)}
            />
          </div>

          {/* Trading Stats */}
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <MiniCard label="Trades" value={String(coin.trade_count)} />
            <MiniCard
              label="Win Rate"
              value={coin.win_rate !== null ? formatPercent(coin.win_rate * 100, 1) : "N/A"}
              color={coin.win_rate !== null ? pnlColor(coin.win_rate - 0.5) : undefined}
            />
            <MiniCard
              label="Total PnL"
              value={coin.total_pnl !== null ? `${coin.total_pnl >= 0 ? "+" : ""}$${formatCurrency(Math.abs(coin.total_pnl))}` : "N/A"}
              color={pnlColor(coin.total_pnl)}
            />
            <MiniCard
              label="Status"
              value={coin.blacklisted ? "ブラックリスト" : "有効"}
              color={coin.blacklisted ? "var(--accent-red)" : "var(--accent-green)"}
            />
          </div>

          {/* Trade History for this coin */}
          {coinTrades.length > 0 ? (
            <div>
              <p
                className="mb-2 text-[11px] font-medium uppercase tracking-wider"
                style={{ color: "var(--text-secondary)" }}
              >
                取引履歴 ({coinTrades.length}件)
              </p>
              <div
                className="overflow-hidden rounded-lg border"
                style={{
                  backgroundColor: "var(--bg-card)",
                  borderColor: "var(--border-color)",
                }}
              >
                <table className="w-full text-xs">
                  <thead>
                    <tr
                      className="border-b"
                      style={{ borderColor: "var(--border-color)" }}
                    >
                      {["Side", "Entry", "Exit", "Size", "PnL", "Reason"].map((h, i) => (
                        <th
                          key={h}
                          className={`px-3 py-2 text-[10px] font-medium uppercase tracking-wider ${i >= 1 && i <= 4 ? "text-right" : "text-left"}`}
                          style={{ color: "var(--text-muted)" }}
                        >
                          {h}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {coinTrades.slice(0, 10).map((t, i) => (
                      <tr
                        key={i}
                        className="border-b last:border-b-0"
                        style={{ borderColor: "var(--border-color)" }}
                      >
                        <td className="px-3 py-2">
                          <span
                            className="inline-flex rounded px-1.5 py-0.5 text-[10px] font-medium"
                            style={{
                              backgroundColor: t.side === "long" ? "rgba(0,212,170,0.12)" : "rgba(255,68,102,0.12)",
                              color: t.side === "long" ? "var(--accent-green)" : "var(--accent-red)",
                            }}
                          >
                            {t.side.toUpperCase()}
                          </span>
                        </td>
                        <td className="px-3 py-2 text-right font-mono" style={{ fontVariantNumeric: "tabular-nums" }}>
                          ${formatCurrency(t.entry)}
                        </td>
                        <td className="px-3 py-2 text-right font-mono" style={{ fontVariantNumeric: "tabular-nums" }}>
                          ${formatCurrency(t.exit)}
                        </td>
                        <td className="px-3 py-2 text-right font-mono" style={{ fontVariantNumeric: "tabular-nums" }}>
                          ${formatCurrency(t.size)}
                        </td>
                        <td className="px-3 py-2 text-right font-mono" style={{ fontVariantNumeric: "tabular-nums", color: pnlColor(t.pnl) }}>
                          {t.pnl >= 0 ? "+" : "-"}${formatCurrency(Math.abs(t.pnl))}
                        </td>
                        <td className="px-3 py-2" style={{ color: "var(--text-muted)" }}>
                          {t.reason}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          ) : (
            <p
              className="text-xs"
              style={{ color: "var(--text-muted)" }}
            >
              この通貨の取引履歴はまだありません
            </p>
          )}
        </div>
      </td>
    </tr>
  );
}

function MiniCard({
  label,
  value,
  color,
}: {
  label: string;
  value: string;
  color?: string;
}) {
  return (
    <div
      className="rounded-md border px-3 py-2.5"
      style={{
        backgroundColor: "var(--bg-card)",
        borderColor: "var(--border-color)",
      }}
    >
      <p
        className="text-[10px] font-medium uppercase tracking-wider"
        style={{ color: "var(--text-muted)" }}
      >
        {label}
      </p>
      <p
        className="mt-1 text-sm font-semibold font-mono"
        style={{ fontVariantNumeric: "tabular-nums", color }}
      >
        {value}
      </p>
    </div>
  );
}
