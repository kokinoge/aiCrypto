"use client";

import { EmptyState } from "@/components/ui/EmptyState";
import { TableWrap, TRow, Th, Td } from "@/components/ui/DataTable";

type Rule = {
  id: string;
  description: string;
  type: string;
  action: string;
  triggered: number;
  correct: number;
  source: string;
};

export function RuleTable({ rules }: { rules: Rule[] }) {
  if (rules.length === 0) {
    return <EmptyState>ルールなし</EmptyState>;
  }

  return (
    <TableWrap>
      <table className="w-full text-sm">
        <thead>
          <TRow header>
            <Th>Description</Th>
            <Th>Type</Th>
            <Th>Action</Th>
            <Th right>Triggered</Th>
            <Th right>Correct</Th>
            <Th>Source</Th>
          </TRow>
        </thead>
        <tbody>
          {rules.map((r) => (
            <TRow key={r.id}>
              <Td className="max-w-xs truncate">{r.description}</Td>
              <Td>
                <span
                  className="inline-flex rounded px-2 py-0.5 text-[11px] font-medium"
                  style={{
                    backgroundColor: "rgba(68,136,255,0.12)",
                    color: "var(--accent-blue)",
                  }}
                >
                  {r.type}
                </span>
              </Td>
              <Td secondary className="text-xs">{r.action}</Td>
              <Td right mono>{r.triggered}</Td>
              <Td right mono>{r.correct}</Td>
              <Td secondary className="text-xs">{r.source}</Td>
            </TRow>
          ))}
        </tbody>
      </table>
    </TableWrap>
  );
}
