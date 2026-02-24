const API_BASE = process.env.NEXT_PUBLIC_API_URL || "";

async function fetchJSON<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, init);
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

export const api = {
  getDashboard: () => fetchJSON<import("./types").DashboardData>("/api/dashboard"),
  getCoins: () => fetchJSON<{ coins: import("./types").CoinData[]; total: number }>("/api/coins"),
  getBlacklist: () => fetchJSON<{ blacklist: import("./types").BlacklistEntry[] }>("/api/coins/blacklist"),
  addToBlacklist: (coin: string, reason?: string) =>
    fetchJSON<{ success: boolean }>("/api/coins/blacklist", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ coin, reason }),
    }),
  removeFromBlacklist: (coin: string) =>
    fetchJSON<{ success: boolean }>(`/api/coins/blacklist/${coin}`, { method: "DELETE" }),
};
