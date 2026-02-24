"use client";

import { useState } from "react";
import { useCoins } from "@/hooks/useCoins";
import { useDashboard } from "@/hooks/useDashboard";
import { PageHeader } from "@/components/ui/PageHeader";
import { CoinTable } from "@/components/coins/CoinTable";

export default function CoinsPage() {
  const { coins, total, toggleBlacklist } = useCoins();
  const { data } = useDashboard();
  const [search, setSearch] = useState("");

  return (
    <div className="space-y-4">
      <PageHeader title="通貨管理" count={`${total} 通貨`}>
        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="検索..."
          className="w-48 rounded-md border px-3 py-1.5 text-sm outline-none transition-colors"
          style={{
            backgroundColor: "var(--bg-card)",
            borderColor: "var(--border-color)",
            color: "var(--text-primary)",
          }}
        />
      </PageHeader>
      <CoinTable
        coins={coins}
        trades={data?.closed_trades ?? []}
        search={search}
        onToggleBlacklist={toggleBlacklist}
      />
    </div>
  );
}
