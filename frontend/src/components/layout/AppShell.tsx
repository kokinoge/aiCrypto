"use client";

import { useState, useEffect } from "react";
import { WebSocketProvider } from "@/contexts/WebSocketContext";
import { Sidebar } from "./Sidebar";

export function AppShell({ children }: { children: React.ReactNode }) {
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);

  if (!mounted) {
    return <div className="flex min-h-screen" />;
  }

  return (
    <WebSocketProvider>
      <div className="flex min-h-screen">
        <Sidebar />
        <main className="flex-1 ml-56 p-6">{children}</main>
      </div>
    </WebSocketProvider>
  );
}
