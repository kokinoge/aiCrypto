"use client";

import useSWR from "swr";
import { useEffect } from "react";
import { useWebSocket } from "./useWebSocket";
import type { DashboardData } from "@/lib/types";

const fetcher = (url: string) => fetch(url).then((r) => r.json());

export function useDashboard() {
  const { connected, subscribe } = useWebSocket();

  const { data, error, mutate } = useSWR<DashboardData>(
    "/api/dashboard",
    fetcher,
    { refreshInterval: connected ? 0 : 30000, revalidateOnFocus: false }
  );

  useEffect(() => {
    // initial_state sends { dashboard: {...}, coins: [...], blacklist: [...] }
    const unsub1 = subscribe("initial_state", (d) => {
      const payload = d as Record<string, unknown>;
      if (payload?.dashboard) {
        mutate(payload.dashboard as DashboardData, { revalidate: false });
      }
    });
    // dashboard_update sends DashboardData directly
    const unsub2 = subscribe("dashboard_update", (d) =>
      mutate(d as DashboardData, { revalidate: false })
    );
    return () => {
      unsub1();
      unsub2();
    };
  }, [subscribe, mutate]);

  return { data, error, isLoading: !data && !error, connected };
}
