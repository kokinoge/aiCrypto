"use client";

export function SideBadge({ side }: { side: "long" | "short" }) {
  const isLong = side === "long";
  return (
    <span
      className="inline-flex rounded px-2 py-0.5 text-[11px] font-medium"
      style={{
        backgroundColor: isLong
          ? "rgba(0,212,170,0.12)"
          : "rgba(255,68,102,0.12)",
        color: isLong ? "var(--accent-green)" : "var(--accent-red)",
      }}
    >
      {side.toUpperCase()}
    </span>
  );
}
