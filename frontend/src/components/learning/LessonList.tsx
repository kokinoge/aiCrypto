"use client";

import { EmptyState } from "@/components/ui/EmptyState";

export function LessonList({ lessons }: { lessons: string[] }) {
  if (lessons.length === 0) {
    return <EmptyState>レッスンなし</EmptyState>;
  }

  return (
    <div className="space-y-2">
      {lessons.map((lesson, i) => (
        <div
          key={i}
          className="flex items-start gap-3 rounded-lg border px-4 py-3 text-sm"
          style={{
            backgroundColor: "var(--bg-card)",
            borderColor: "var(--border-color)",
          }}
        >
          <span
            className="mt-0.5 text-[11px] font-mono"
            style={{ color: "var(--text-muted)" }}
          >
            {String(i + 1).padStart(2, "0")}
          </span>
          <span>{lesson}</span>
        </div>
      ))}
    </div>
  );
}
