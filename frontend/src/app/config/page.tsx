"use client";

import { useDashboard } from "@/hooks/useDashboard";
import { formatCurrency } from "@/lib/formatters";
import { PageHeader } from "@/components/ui/PageHeader";
import { ConfigSection, ConfigRow } from "@/components/config/ConfigSection";

export default function ConfigPage() {
  const { data, isLoading } = useDashboard();

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-20 text-sm" style={{ color: "var(--text-muted)" }}>
        読み込み中...
      </div>
    );
  }

  const config = data?.config;

  if (!config) {
    return (
      <div className="flex items-center justify-center py-20 text-sm" style={{ color: "var(--text-muted)" }}>
        設定データなし
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <PageHeader title="設定" />
      <div className="grid gap-4 lg:grid-cols-2">
        <ConfigSection title="モード">
          <ConfigRow label="Trading Mode" value={config.mode} />
          <ConfigRow label="Paper Balance" value={`$${formatCurrency(config.paper_balance)}`} mono />
        </ConfigSection>

        <ConfigSection title="リスク設定">
          <ConfigRow label="Risk per Trade" value={`${config.risk_per_trade.toFixed(1)}%`} mono />
          <ConfigRow label="Stop Loss" value={`${config.stop_loss.toFixed(1)}%`} mono />
          <ConfigRow label="Take Profit" value={`${config.take_profit.toFixed(1)}%`} mono />
          <ConfigRow label="Max Drawdown" value={`${config.max_drawdown.toFixed(1)}%`} mono />
        </ConfigSection>

        <ConfigSection title="シグナル設定">
          <ConfigRow label="Max Positions" value={String(config.max_positions)} mono />
          <ConfigRow label="Max Leverage" value={`${config.max_leverage}x`} mono />
          <ConfigRow label="Min Confidence" value={`${(config.min_confidence * 100).toFixed(0)}%`} mono />
          <ConfigRow label="Cooldown" value={`${config.cooldown_minutes} min`} mono />
        </ConfigSection>

        <ConfigSection title="Trading Pairs">
          <div className="flex flex-wrap gap-2 px-4 py-3">
            {config.trading_pairs.length === 0 ? (
              <span className="text-sm" style={{ color: "var(--text-muted)" }}>設定なし</span>
            ) : (
              config.trading_pairs.map((pair) => (
                <span
                  key={pair}
                  className="inline-flex rounded px-2 py-1 text-xs font-mono font-medium"
                  style={{ backgroundColor: "var(--bg-hover)", color: "var(--text-primary)" }}
                >
                  {pair}
                </span>
              ))
            )}
          </div>
        </ConfigSection>
      </div>
    </div>
  );
}
