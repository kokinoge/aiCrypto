"use client";

export function StreakBadge({ streak }: { streak: [string, number] }) {
  return (
    <div
      className="inline-flex items-center gap-3 rounded-lg border px-4 py-3"
      style={{
        backgroundColor: "var(--bg-card)",
        borderColor: "var(--border-color)",
      }}
    >
      <span
        className="text-2xl font-semibold font-mono"
        style={{
          fontVariantNumeric: "tabular-nums",
          color: streak[0] === "win" ? "var(--accent-green)" : "var(--accent-red)",
        }}
      >
        {streak[1]}
      </span>
      <span
        className="text-xs font-medium uppercase tracking-wider"
        style={{ color: "var(--text-secondary)" }}
      >
        {streak[0] === "win" ? "連勝" : "連敗"}ストリーク
      </span>
    </div>
  );
}
