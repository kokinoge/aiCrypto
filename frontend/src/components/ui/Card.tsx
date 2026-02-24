"use client";

export function Card({
  label,
  value,
  valueColor,
  sub,
}: {
  label: string;
  value: string;
  valueColor?: string;
  sub?: string;
}) {
  return (
    <div
      className="rounded-lg border p-4"
      style={{
        backgroundColor: "var(--bg-card)",
        borderColor: "var(--border-color)",
      }}
    >
      <p
        className="text-[11px] font-medium uppercase tracking-wider"
        style={{ color: "var(--text-secondary)" }}
      >
        {label}
      </p>
      <p
        className="mt-2 text-2xl font-semibold font-mono"
        style={{ fontVariantNumeric: "tabular-nums", color: valueColor }}
      >
        {value}
      </p>
      {sub && (
        <p
          className="mt-1 text-[11px]"
          style={{ color: "var(--text-muted)" }}
        >
          {sub}
        </p>
      )}
    </div>
  );
}
