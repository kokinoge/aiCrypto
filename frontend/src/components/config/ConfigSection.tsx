"use client";

export function ConfigSection({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div
      className="overflow-hidden rounded-lg border"
      style={{
        backgroundColor: "var(--bg-card)",
        borderColor: "var(--border-color)",
      }}
    >
      <div
        className="border-b px-4 py-3"
        style={{ borderColor: "var(--border-color)" }}
      >
        <h2
          className="text-[11px] font-medium uppercase tracking-wider"
          style={{ color: "var(--text-secondary)" }}
        >
          {title}
        </h2>
      </div>
      {children}
    </div>
  );
}

export function ConfigRow({
  label,
  value,
  mono,
}: {
  label: string;
  value: string;
  mono?: boolean;
}) {
  return (
    <div
      className="flex items-center justify-between border-b px-4 py-3 last:border-b-0"
      style={{ borderColor: "var(--border-color)" }}
    >
      <span className="text-sm" style={{ color: "var(--text-secondary)" }}>
        {label}
      </span>
      <span
        className={`text-sm ${mono ? "font-mono" : ""}`}
        style={{ fontVariantNumeric: mono ? "tabular-nums" : undefined }}
      >
        {value}
      </span>
    </div>
  );
}
