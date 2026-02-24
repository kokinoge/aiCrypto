"use client";

export function EmptyState({ children }: { children: React.ReactNode }) {
  return (
    <div
      className="rounded-lg border py-12 text-center text-sm"
      style={{
        backgroundColor: "var(--bg-card)",
        borderColor: "var(--border-color)",
        color: "var(--text-muted)",
      }}
    >
      {children}
    </div>
  );
}
