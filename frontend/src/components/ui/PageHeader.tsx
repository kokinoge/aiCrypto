"use client";

export function PageHeader({
  title,
  count,
  children,
}: {
  title: string;
  count?: number | string;
  children?: React.ReactNode;
}) {
  return (
    <div className="flex items-center justify-between gap-4">
      <div className="flex items-baseline gap-3">
        <h1 className="text-lg font-semibold tracking-tight">{title}</h1>
        {count !== undefined && (
          <span
            className="text-xs font-mono"
            style={{ color: "var(--text-muted)" }}
          >
            {count}
          </span>
        )}
      </div>
      {children}
    </div>
  );
}
