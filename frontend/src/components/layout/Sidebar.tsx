"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useWebSocket } from "@/hooks/useWebSocket";

const navItems = [
  { href: "/", label: "概要", icon: "📊" },
  { href: "/positions", label: "ポジション", icon: "📈" },
  { href: "/history", label: "取引履歴", icon: "📋" },
  { href: "/agents", label: "エージェント", icon: "🤖" },
  { href: "/coins", label: "通貨管理", icon: "🪙" },
  { href: "/learning", label: "学習状況", icon: "🧠" },
  { href: "/config", label: "設定", icon: "⚙️" },
];

export function Sidebar() {
  const pathname = usePathname();
  const { connected } = useWebSocket();

  return (
    <aside
      className="fixed left-0 top-0 h-full w-56 border-r flex flex-col"
      style={{
        backgroundColor: "var(--bg-secondary)",
        borderColor: "var(--border-color)",
      }}
    >
      <div
        className="p-5 border-b"
        style={{ borderColor: "var(--border-color)" }}
      >
        <h1
          className="text-lg font-semibold"
          style={{ color: "var(--accent-green)" }}
        >
          AI Crypto Bot
        </h1>
        <div
          className="flex items-center gap-2 mt-2 text-xs"
          style={{ color: "var(--text-secondary)" }}
        >
          <span
            className="inline-block w-2 h-2 rounded-full"
            style={{
              backgroundColor: connected
                ? "var(--accent-green)"
                : "var(--accent-red)",
            }}
          />
          {connected ? "接続中" : "切断"}
        </div>
      </div>
      <nav className="flex-1 py-3">
        {navItems.map((item) => {
          const isActive = pathname === item.href;
          return (
            <Link
              key={item.href}
              href={item.href}
              className="flex items-center gap-3 px-5 py-2.5 text-sm transition-colors"
              style={{
                color: isActive
                  ? "var(--accent-green)"
                  : "var(--text-secondary)",
                backgroundColor: isActive ? "var(--bg-hover)" : "transparent",
              }}
            >
              <span>{item.icon}</span>
              <span>{item.label}</span>
            </Link>
          );
        })}
      </nav>
    </aside>
  );
}
