"use client";

export function Toggle({
  blocked,
  onToggle,
}: {
  blocked: boolean;
  onToggle: () => void;
}) {
  return (
    <button
      onClick={(e) => {
        e.stopPropagation();
        onToggle();
      }}
      className="relative inline-flex h-5 w-9 shrink-0 cursor-pointer items-center rounded-full transition-colors"
      style={{
        backgroundColor: blocked
          ? "rgba(255,68,102,0.3)"
          : "rgba(0,212,170,0.3)",
      }}
      aria-label={blocked ? "ブラックリスト解除" : "ブラックリストに追加"}
    >
      <span
        className="inline-block h-3.5 w-3.5 rounded-full transition-transform"
        style={{
          backgroundColor: blocked
            ? "var(--accent-red)"
            : "var(--accent-green)",
          transform: blocked ? "translateX(18px)" : "translateX(2px)",
        }}
      />
    </button>
  );
}
