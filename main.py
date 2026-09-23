"""
V400 — AUTO-INCREMENT BOT STEP & WIN RESET SCRIPT
=================================================
- Features:
  * Bot Step automatically increments on losses/steps.
  * Bot Step immediately resets to 1x upon any Win.
  * Reverses prediction signals (Big <-> Small) and keeps exact Telegram layouts.
"""

from __future__ import annotations
import math
import time
import os
import requests
import threading
from collections import deque
from dataclasses import dataclass
from typing import Optional, Tuple
from flask import Flask, jsonify

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
CHAT_ID = os.environ.get("CHAT_ID", "")
LOTTERY_AUTH = os.environ.get("LOTTERY_AUTH", "")

CONFIG = {
    "api_url": "https://6lotteryapi.com/api/webapi/GetNoaverageEmerdList",
    "payout_rate": 0.96,
    "profit_reset_threshold": 100000,
    "poll_interval": 3.0,
    "warmup_target": 15,
}

LEVEL_TABLE = {
    1:  {"bet1": 1000,  "bet2": 2000},
    2:  {"bet1": 1000,  "bet2": 2000},
    3:  {"bet1": 2000,  "bet2": 4000},
    4:  {"bet1": 2000,  "bet2": 4000},
    5:  {"bet1": 3000,  "bet2": 6000},
    6:  {"bet1": 4000,  "bet2": 8000},
    7:  {"bet1": 6000,  "bet2": 12000},
    8:  {"bet1": 8000,  "bet2": 16000},
    9:  {"bet1": 10000, "bet2": 20000},
    10: {"bet1": 14000, "bet2": 28000},
    11: {"bet1": 19000, "bet2": 38000},
    12: {"bet1": 25000, "bet2": 50000},
    13: {"bet1": 34000, "bet2": 68000},
    14: {"bet1": 46000, "bet2": 92000},
    15: {"bet1": 62000, "bet2": 124000},
}

def get_level_bet(level: int):
    if level in LEVEL_TABLE:
        return LEVEL_TABLE[level]
    a = LEVEL_TABLE[14]["bet1"]
    b = LEVEL_TABLE[15]["bet1"]
    for _ in range(level - 15):
        a, b = b, a + b
    return {"bet1": b, "bet2": b * 2}

def clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, float(x)))

class BettingManager:
    def __init__(self):
        self.reset_all()

    def reset_all(self):
        self.level = 1
        self.level_state = "WAITING_BET1"
        self.bot_step = 1
        self.total_signals = 0
        self.total_wins = 0
        self.total_losses = 0
        self.total_profit = 0.0
        self.total_loss_amount = 0.0
        self.current_profit = 0.0
        self.max_loss_amount = 0.0
        self.max_level_reached = 1
        self.cycles_completed = 0

    def reset_milestone(self):
        self.current_profit = 0.0
        self.max_loss_amount = 0.0
        self.max_level_reached = 1
        self.level = 1
        self.level_state = "WAITING_BET1"
        self.bot_step = 1

    def get_current_bet(self):
        info = get_level_bet(self.level)
        if self.level_state == "WAITING_BET1":
            return info["bet1"], "BET1"
        return info["bet2"], "BET2"

    def get_wr(self):
        total = self.total_wins + self.total_losses
        return (self.total_wins / total * 100) if total > 0 else 0.0

    def on_result(self, won: bool):
        old_level = self.level
        if self.level_state == "WAITING_BET1":
            if won:
                self.level_state = "WAITING_BET2"
                self.bot_step = 1  # နိုင်လျှင် 1x ပြန်စမည်
                return "BET1_WIN", old_level
            else:
                self.level += 1
                self.level_state = "WAITING_BET1"
                self.bot_step += 1  # ရှုံးလျှင် Bot Step တက်မည်
                self.max_level_reached = max(self.max_level_reached, self.level)
                return "BET1_LOSE", old_level
        else:
            if won:
                self.level = 1
                self.level_state = "WAITING_BET1"
                self.bot_step = 1  # နိုင်လျှင် 1x ပြန်စမည်
                self.cycles_completed += 1
                return "RESET", old_level
            else:
                self.level += 1
                self.level_state = "WAITING_BET1"
                self.bot_step += 1  # ရှုံးလျှင် Bot Step တက်မည်
                self.max_level_reached = max(self.max_level_reached, self.level)
                return "BET2_LOSE", old_level

    def apply_result(self, won: bool):
        bet_amount, bet_type = self.get_current_bet()
        if won:
            profit = bet_amount * CONFIG["payout_rate"]
            self.total_profit += profit
            self.current_profit += profit
            self.total_wins += 1
        else:
            profit = -bet_amount
            self.total_loss_amount += bet_amount
            self.current_profit -= bet_amount
            self.total_losses += 1

        self.max_loss_amount = min(self.max_loss_amount, self.current_profit)
        action, old_level = self.on_result(won)
        target_hit = self.current_profit >= CONFIG["profit_reset_threshold"]

        return {
            "bet_amount": bet_amount, "bet_type": bet_type, "profit": profit,
            "action": action, "old_level": old_level, "new_level": self.level,
            "target_hit": target_hit,
        }

@dataclass
class V400Decision:
    signal: str
    confidence: float
    tactical_mode: str
    elite_type: Optional[str] = None
    super_signal_text: Optional[str] = None

class PredictionEngineV400:
    def __init__(self, max_history: int = 150):
        self.history_digits = deque(maxlen=max_history)
        self.history_binary = deque(maxlen=max_history)
        self.locked_plan: Optional[Tuple[str, str]] = None
        self.adaptive_penalty_memory = 0.0

    def resolve(self, digit: int):
        self.history_digits.append(digit)
        self.history_binary.append(1 if digit >= 5 else 0)

    def record_outcome(self, won: bool):
        if not won:
            self.adaptive_penalty_memory = min(0.25, self.adaptive_penalty_memory + 0.05)
        else:
            self.adaptive_penalty_memory = max(0.0, self.adaptive_penalty_memory - 0.02)

    def _autonomous_neural_quantum_matrix(self, window: int = 25) -> Tuple[str, float, float, str]:
        b = list(self.history_binary)
        if len(b) < window:
            return "Neutral", 0.0, 0.5, "NORMAL"
        sub_b = b[-window:]

        mean_b = sum(sub_b) / len(sub_b)
        entropy = - (mean_b * math.log2(max(0.01, mean_b)) + (1 - mean_b) * math.log2(max(0.01, 1 - mean_b)))
        chaos_factor = clamp(entropy / 1.0, 0.0, 1.0)

        w_tensor = clamp(0.70 - chaos_factor * 0.2, 0.40, 0.70)
        w_macro = 1.0 - w_tensor

        c0, c1 = 0, 0
        for i in range(len(sub_b) - 2):
            if sub_b[i] == sub_b[-2] and sub_b[i+1] == sub_b[-1]:
                if sub_b[i+2] == 1: c1 += 2
                else: c0 += 2
            elif sub_b[i+1] == sub_b[-1]:
                if sub_b[i+2] == 1: c1 += 1
                else: c0 += 1

        p_tensor = (c1 / (c0 + c1)) if (c0 + c1) > 0 else 0.5
        p_final = (w_tensor * p_tensor + w_macro * mean_b) - self.adaptive_penalty_memory
        
        edge = abs(p_final - 0.50)
        side = "Big" if p_final >= 0.50 else "Small"

        elite_type = "NORMAL_HYPER_FLOW"
        if chaos_factor < 0.35 and edge >= 0.04:
            elite_type = "QUANTUM_GOLDEN"
        elif self.adaptive_penalty_memory == 0.0 and edge >= 0.03:
            elite_type = "CLEARED_RECOVERY"
        elif b[-1] != b[-2] and edge >= 0.025:
            elite_type = "ZERO_LAG_REVERSAL"

        return side, edge, p_final, elite_type

    def predict(self, current_level: int, current_state: str) -> V400Decision:
        b = list(self.history_binary)
        if len(b) < CONFIG["warmup_target"]:
            return V400Decision("WAIT", 0.0, "WARMUP", "WARMUP", None)

        if current_state == "WAITING_BET2":
            if self.locked_plan is not None:
                step1_side, step2_side = self.locked_plan
                step2_side = "Small" if step2_side == "Big" else "Big"
                return V400Decision(step2_side, 0.99, "V400_AUTONOMOUS_WW_LOCK", "ELITE_WW", None)
            else:
                side = "Small" if b[-1] == 1 else "Big"
                return V400Decision(side, 0.95, "FALLBACK", "NORMAL", None)

        side1, edge, p_final, elite_type = self._autonomous_neural_quantum_matrix(window=25)

        if edge >= 0.001:
            streak = 1
            for k in range(len(b)-2, -1, -1):
                if b[k] == b[-1]: streak += 1
                else: break

            if streak >= 2:
                side2 = side1
            else:
                side2 = side1 if p_final >= 0.502 else ("Small" if side1 == "Big" else "Big")

            # Reverse Signal
            final_side1 = "Small" if side1 == "Big" else "Big"
            final_side2 = "Small" if side2 == "Big" else "Big"

            self.locked_plan = (final_side1, final_side2)
            conf = clamp(0.90 + edge * 2.5, 0.90, 0.99)
            return V400Decision(final_side1, conf, "V400_NEURAL_FLOW", elite_type, None)

        self.locked_plan = None
        return V400Decision("WAIT", 0.0, "DEADBAND", "DEAFBAND_SKIP", None)

class V400LiveBot:
    def __init__(self):
        self.lock = threading.Lock()
        self.engine = PredictionEngineV400()
        self.betting = BettingManager()
        self.last_decision: Optional[V400Decision] = None
        self.last_processed_period = None

    def send_telegram_sync(self, message: str):
        if not TELEGRAM_TOKEN or not CHAT_ID:
            print(f"[TG-LOCAL]\n{message}", flush=True)
            return
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {"chat_id": CHAT_ID, "text": message, "parse_mode": "HTML"}
        try:
            res = requests.post(url, json=payload, timeout=6)
            print(f"[TG-RES] Status: {res.status_code}", flush=True)
        except Exception as e:
            print(f"[TG-ERR] {e}", flush=True)

    def process_round(self, period: str, digit: int):
        with self.lock:
            actual_big = 1 if digit >= 5 else 0
            if self.last_decision and self.last_decision.signal in ["Big", "Small"]:
                last_won = ((1 if self.last_decision.signal == "Big" else 0) == actual_big)
                self.engine.record_outcome(last_won)
                settle = self.betting.apply_result(last_won)

                if last_won:
                    if settle['action'] == 'RESET':
                        win_msg = (
                            f"🔥 WIN ✅ (+{settle['profit']:,.0f})\n"
                            f"🎉 BET2 WIN → Level 1 RESET\n"
                            f"🔄 Level {settle['old_level']} → Level 1"
                        )
                    else:
                        win_msg = (
                            f"🔥 WIN ✅ (+{settle['profit']:,.0f})\n"
                            f"🎯 Bet1 Win → Bet2 \n"
                            f"🎮 Level: {self.betting.level} | BET2"
                        )
                    self.send_telegram_sync(win_msg)
                    
                    if settle.get("target_hit", False):
                        milestone_msg = (
                            f"🏆 <b>TARGET +100,000 REACHED! MILESTONE RESET.</b>\n"
                            f"━━━━━━━━━━━━━━━━━\n"
                            f"📊 <b>Cycle Statistics:</b>\n"
                            f"📉 <b>Max Drawdown (Max DD):</b> {self.betting.max_loss_amount:+,.0f} MMK\n"
                            f"📈 <b>Max Level Reached:</b> Level {self.betting.max_level_reached}\n"
                            f"💵 <b>Total Cycle Profit:</b> +100,000 MMK\n"
                            f"👑 <i>Status: Fresh State Initialized (Cycle Restored)</i>"
                        )
                        self.send_telegram_sync(milestone_msg)
                        self.betting.reset_milestone()
                        self.engine.locked_plan = None
                else:
                    self.engine.locked_plan = None

            self.engine.resolve(digit)
            try:
                period_str = str(int(period) + 1)[-3:]
            except Exception:
                period_str = str(period)[-3:]

            decision = self.engine.predict(self.betting.level, self.betting.level_state)
            self.last_decision = decision

            if decision.signal == "WAIT":
                self.send_telegram_sync(f"💤  Period {period_str} SKIP  💤")
            else:
                bet_amt, b_type = self.betting.get_current_bet()
                self.betting.total_signals += 1
                max_lvl = self.betting.max_level_reached

                if decision.elite_type in ["QUANTUM_GOLDEN", "ZERO_LAG_REVERSAL", "CLEARED_RECOVERY"]:
                    msg = (
                        f"🚨 === VIP ELITE GOD-TIER SIGNAL === 🚨\n"
                        f"💖 Period {period_str}\n"
                        f"🎯 SIGNAL → {decision.signal.upper()}\n"
                        f"📊 Conf: {decision.confidence*100:.1f}%\n"
                        f"━━━━━━━━━━━━━━━━━\n"
                        f"🤖 Bot Step: {self.betting.bot_step}x\n"
                        f"🎮 Level: {self.betting.level} | {b_type}\n"
                        f"💰 Bet: {bet_amt:,}\n"
                        f"━━━━━━━━━━━━━━━━━\n"
                        f"🏆 Max Level: {max_lvl}\n"
                        f"📉 Max DD: {self.betting.max_loss_amount:,.0f}\n"
                        f"💵 Profit: {self.betting.current_profit:+,.0f}\n"
                        f"📊 WR: {self.betting.get_wr():.1f}%"
                    )
                else:
                    msg = (
                        f"💖 Period {period_str}\n"
                        f"🎯 SIGNAL → {decision.signal.upper()}\n"
                        f"📊 Conf: {decision.confidence*100:.1f}%\n"
                        f"━━━━━━━━━━━━━━━━━\n"
                        f"🤖 Bot Step: {self.betting.bot_step}x\n"
                        f"🎮 Level: {self.betting.level} | {b_type}\n"
                        f"💰 Bet: {bet_amt:,}\n"
                        f"━━━━━━━━━━━━━━━━━\n"
                        f"🏆 Max Level: {max_lvl}\n"
                        f"📉 Max DD: {self.betting.max_loss_amount:,.0f}\n"
                        f"💵 Profit: {self.betting.current_profit:+,.0f}\n"
                        f"📊 WR: {self.betting.get_wr():.1f}%"
                    )
                self.send_telegram_sync(msg)

    def start_polling_loop(self):
        def worker():
            print("[V400] Polling worker started...", flush=True)
            headers = {
                "accept": "application/json, text/plain, */*",
                "authorization": f"Bearer {LOTTERY_AUTH}" if not LOTTERY_AUTH.startswith("Bearer") else LOTTERY_AUTH,
                "content-type": "application/json;charset=UTF-8",
                "origin": "https://6win598.com",
                "referer": "https://6win598.com/",
                "user-agent": "Mozilla/5.0",
            }
            while True:
                try:
                    payload = {
                        "pageSize": 10, "pageNo": 1, "typeId": 30, "language": 7,
                        "random": "036263f367384d418be07465793c8da8",
                        "signature": "55F4FD150F15F090B943374F3C9BE78B",
                        "timestamp": int(time.time()),
                    }
                    res = requests.post(CONFIG["api_url"], json=payload, headers=headers, timeout=5)
                    if res.status_code == 200:
                        data = res.json()
                        list_data = data.get("data", {}).get("list", [])
                        if list_data:
                            latest = list_data[0]
                            period = str(latest.get("issueNumber"))
                            digit = int(latest.get("number"))
                            if period != self.last_processed_period:
                                self.last_processed_period = period
                                self.process_round(period, digit)
                                time.sleep(1.5)
                except Exception as e:
                    print(f"[Polling Error] {e}", flush=True)
                time.sleep(CONFIG["poll_interval"])

        t = threading.Thread(target=worker, daemon=True)
        t.start()

app = Flask(__name__)
GLOBAL_BOT: Optional[V400LiveBot] = None

@app.route("/")
def index():
    return "V400 BotStep-Reset Engine Active!", 200

@app.route("/health")
def health():
    return jsonify({"status": "healthy"}), 200

if __name__ == "__main__":
    GLOBAL_BOT = V400LiveBot()
    GLOBAL_BOT.start_polling_loop()
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
