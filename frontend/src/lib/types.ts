export interface Position {
  coin: string;
  side: "long" | "short";
  entry_price: number;
  current_price: number;
  size: number;
  unrealized_pnl: number;
  leverage: number;
}

export interface ClosedTrade {
  coin: string;
  side: "long" | "short";
  entry: number;
  exit: number;
  size: number;
  pnl: number;
  reason: string;
  closed_at: number;
}

export interface DashboardData {
  status: string;
  mode: string;
  equity: number;
  cash: number;
  initial_balance: number;
  total_pnl: number;
  return_pct: number;
  open_positions: Position[];
  closed_trades: ClosedTrade[];
  win_rate: { total: number; wins: number; losses: number; win_rate: number };
  active_rules: number;
  streak: [string, number];
  position_size_modifier: number;
  lessons: string[];
  agent_accuracy: Record<string, { total: number; correct: number; accuracy: number }>;
  rules: Array<{ id: string; description: string; type: string; action: string; triggered: number; correct: number; source: string }>;
  coin_stats: Record<string, { total: number; wins: number; losses: number; win_rate: number; total_pnl: number; avg_pnl: number }>;
  coin_adjustments: Record<string, number>;
  config: DashboardConfig;
  last_updated?: string;
}

export interface DashboardConfig {
  mode: string;
  paper_balance: number;
  risk_per_trade: number;
  stop_loss: number;
  take_profit: number;
  max_positions: number;
  max_drawdown: number;
  max_leverage: number;
  min_confidence: number;
  cooldown_minutes: number;
  trading_pairs: string[];
}

export interface CoinData {
  coin: string;
  mark_price: number;
  funding_rate: number;
  open_interest: number;
  trade_count: number;
  win_rate: number | null;
  total_pnl: number | null;
  confidence_adjustment: number;
  blacklisted: boolean;
}

export interface BlacklistEntry {
  coin: string;
  added_at: string;
  reason: string;
}

export interface WSEvent {
  type: string;
  data: unknown;
  timestamp?: string;
}
