"use client";

export function TableWrap({ children }: { children: React.ReactNode }) {
  return (
    <div
      className="overflow-hidden rounded-lg border"
      style={{
        backgroundColor: "var(--bg-card)",
        borderColor: "var(--border-color)",
      }}
    >
      {children}
    </div>
  );
}

export function Th({
  children,
  right,
  onClick,
  active,
}: {
  children: React.ReactNode;
  right?: boolean;
  onClick?: () => void;
  active?: boolean;
}) {
  return (
    <th
      onClick={onClick}
      className={`px-4 py-3 text-[11px] font-medium uppercase tracking-wider ${right ? "text-right" : "text-left"} ${onClick ? "cursor-pointer select-none transition-colors hover:text-[var(--text-primary)]" : ""}`}
      style={{ color: active ? "var(--text-primary)" : "var(--text-secondary)" }}
    >
      {children}
    </th>
  );
}

export function Td({
  children,
  right,
  mono,
  bold,
  color,
  secondary,
  className: extraClass,
}: {
  children: React.ReactNode;
  right?: boolean;
  mono?: boolean;
  bold?: boolean;
  color?: string;
  secondary?: boolean;
  className?: string;
}) {
  return (
    <td
      className={`px-4 py-3 ${right ? "text-right" : "text-left"} ${mono ? "font-mono" : ""} ${bold ? "font-medium" : ""} ${extraClass ?? ""}`}
      style={{
        fontVariantNumeric: mono ? "tabular-nums" : undefined,
        color: color ?? (secondary ? "var(--text-secondary)" : undefined),
      }}
    >
      {children}
    </td>
  );
}

export function TRow({
  children,
  header,
  onClick,
  style: extraStyle,
}: {
  children: React.ReactNode;
  header?: boolean;
  onClick?: () => void;
  style?: React.CSSProperties;
}) {
  return (
    <tr
      onClick={onClick}
      className={`border-b last:border-b-0 ${!header ? "transition-colors hover:bg-[var(--bg-hover)]" : ""} ${onClick ? "cursor-pointer" : ""}`}
      style={{ borderColor: "var(--border-color)", ...extraStyle }}
    >
      {children}
    </tr>
  );
}
