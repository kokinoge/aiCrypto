"use client";

import useSWR from "swr";
import { useEffect, useCallback } from "react";
import { useWebSocket } from "./useWebSocket";
import type { CoinData } from "@/lib/types";

const fetcher = (url: string) => fetch(url).then((r) => r.json());

export function useCoins() {
  const { subscribe } = useWebSocket();

  const { data, error, mutate } = useSWR<{ coins: CoinData[]; total: number }>(
    "/api/coins",
    fetcher,
    { refreshInterval: 60000 }
  );

  useEffect(() => {
    const unsub = subscribe("blacklist_updated", () => mutate());
    return unsub;
  }, [subscribe, mutate]);

  const toggleBlacklist = useCallback(
    async (coin: string, blacklisted: boolean) => {
      if (blacklisted) {
        await fetch(`/api/coins/blacklist/${coin}`, { method: "DELETE" });
      } else {
        await fetch("/api/coins/blacklist", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ coin }),
        });
      }
      mutate();
    },
    [mutate]
  );

  return {
    coins: data?.coins ?? [],
    total: data?.total ?? 0,
    error,
    toggleBlacklist,
  };
}
