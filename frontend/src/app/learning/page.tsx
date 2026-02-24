"use client";

import { useDashboard } from "@/hooks/useDashboard";
import { PageHeader } from "@/components/ui/PageHeader";
import { StreakBadge } from "@/components/learning/StreakBadge";
import { RuleTable } from "@/components/learning/RuleTable";
import { LessonList } from "@/components/learning/LessonList";

export default function LearningPage() {
  const { data, isLoading } = useDashboard();

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-20 text-sm" style={{ color: "var(--text-muted)" }}>
        読み込み中...
      </div>
    );
  }

  const rules = data?.rules ?? [];
  const lessons = data?.lessons ?? [];
  const streak = data?.streak;

  return (
    <div className="space-y-6">
      <PageHeader title="学習状況" />
      {streak && <StreakBadge streak={streak} />}

      <section>
        <h2
          className="mb-3 text-[11px] font-medium uppercase tracking-wider"
          style={{ color: "var(--text-secondary)" }}
        >
          ルール一覧
        </h2>
        <RuleTable rules={rules} />
      </section>

      <section>
        <h2
          className="mb-3 text-[11px] font-medium uppercase tracking-wider"
          style={{ color: "var(--text-secondary)" }}
        >
          レッスン
        </h2>
        <LessonList lessons={lessons} />
      </section>
    </div>
  );
}
