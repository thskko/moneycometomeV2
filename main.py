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
    "warmup_target": 100,
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

class AdaptiveBettingManager:
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

    def on_result(self, won: bool, is_adaptive_streak: bool):
        old_level = self.level
        if self.level_state == "WAITING_BET1":
            if won:
                self.level_state = "WAITING_BET2"
                self.bot_step += 1
                return "BET1_WIN_LOCK_BET2", old_level
            else:
                self.level += 1
                self.level_state = "WAITING_BET1"
                self.bot_step += 1
                self.max_level_reached = max(self.max_level_reached, self.level)
                return "BET1_LOSE_NEXT_LEVEL_BET1", old_level
        else:
            if won or is_adaptive_streak:
                reset_from = self.level
                self.level = 1
                self.level_state = "WAITING_BET1"
                self.bot_step = 1
                self.cycles_completed += 1
                return f"ADAPTIVE_WW_STREAK_RESET_FROM_{reset_from}", old_level
            else:
                self.level += 1
                self.level_state = "WAITING_BET1"
                self.bot_step += 1
                self.max_level_reached = max(self.max_level_reached, self.level)
                return "BET2_LOSE_NEXT_LEVEL_BET1", old_level

    def apply_result(self, won: bool, is_adaptive_streak: bool):
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
        action, old_level = self.on_result(won, is_adaptive_streak)
        target_hit = self.current_profit >= CONFIG["profit_reset_threshold"]

        return {
            "bet_amount": bet_amount, "bet_type": bet_type, "profit": profit,
            "action": action, "old_level": old_level, "new_level": self.level,
            "target_hit": target_hit,
        }

@dataclass
class AdaptiveDecision:
    signal: str
    confidence: float
    tactical_mode: str
    is_adaptive_streak: bool
    is_noise_filtered: bool
    elite_type: Optional[str] = None

class PredictionEngineAdaptive:
    def __init__(self, macro_window=100, micro_window=20):
        self.macro_buffer = deque(maxlen=macro_window)
        self.micro_buffer = deque(maxlen=micro_window)
        self.cumulative_price = 0
        self.last_confirmed_bias = "BIG"

    def resolve(self, digit: int):
        outcome = "BIG" if digit >= 5 else "SMALL"
        price_step = 1 if outcome == "BIG" else -1
        self.cumulative_price += price_step
        
        record = {"digit": digit, "outcome": outcome, "price": self.cumulative_price}
        self.macro_buffer.append(record)
        self.micro_buffer.append(record)

    def record_outcome(self, won: bool):
        pass

    def predict(self, current_level: int, current_state: str) -> AdaptiveDecision:
        if len(self.macro_buffer) < CONFIG["warmup_target"]:
            return AdaptiveDecision("WAIT", 0.0, "WARMUP", False, False, "WARMUP")

        macro_prices = [item["price"] for item in self.macro_buffer]
        micro_prices = [item["price"] for item in self.micro_buffer]

        macro_slope = macro_prices[-1] - macro_prices[0] if len(macro_prices) > 1 else 0
        micro_slope = micro_prices[-1] - micro_prices[0] if len(micro_prices) > 1 else 0

        # Dynamic Noise Gate Check (Filtering Sideways Chop)
        if abs(micro_slope) < 2.0:
            return AdaptiveDecision(
                self.last_confirmed_bias, 0.50, "NOISE_FILTERED_PAUSE", False, True, "SIDEWAYS_NOISE_GATE"
            )

        adaptive_vector = (macro_slope * 1.5) + (micro_slope * 2.8)

        is_adaptive_streak = False
        elite_tag = "ADAPTIVE_FLOW"

        if abs(macro_slope) >= 8 and ((macro_slope > 0 and micro_slope > 0) or (macro_slope < 0 and micro_slope < 0)):
            is_adaptive_streak = True
            elite_tag = "GOD_TIER_RESONANCE_ALIGNMENT"
        elif abs(micro_slope) >= 3.0 and current_state == "WAITING_BET2":
            is_adaptive_streak = True
            elite_tag = "GOD_TIER_BET2_STREAK_MASTERY"

        if adaptive_vector >= 0.01:
            self.last_confirmed_bias = "BIG"
        elif adaptive_vector <= -0.01:
            self.last_confirmed_bias = "SMALL"

        return AdaptiveDecision(
            self.last_confirmed_bias, 
            0.9999 if is_adaptive_streak else 0.985, 
            "ADAPTIVE_ACTIVE" if is_adaptive_streak else "FLOW", 
            is_adaptive_streak, 
            False,
            elite_tag
        )

class AdaptiveLiveBot:
    def __init__(self):
        self.lock = threading.Lock()
        self.engine = PredictionEngineAdaptive()
        self.betting = AdaptiveBettingManager()
        self.last_decision: Optional[AdaptiveDecision] = None
        self.last_processed_period = None

    def send_telegram_sync(self, message: str):
        if not TELEGRAM_TOKEN or not CHAT_ID:
            print(f"[TG-LOCAL]\n{message}", flush=True)
            return
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {"chat_id": CHAT_ID, "text": message, "parse_mode": "HTML"}
        try:
            requests.post(url, json=payload, timeout=6)
        except Exception as e:
            print(f"[TG-ERR] {e}", flush=True)

    def process_round(self, period: str, digit: int):
        with self.lock:
            try:
                raw_int_period = int(period)
                current_period_str = str(raw_int_period)[-3:]
                next_period_str = str(raw_int_period + 1)[-3:]
            except Exception:
                current_period_str = str(period)[-3:]
                next_period_str = "NXT"

            if len(self.engine.macro_buffer) < CONFIG["warmup_target"]:
                self.engine.resolve(digit)
                current_count = len(self.engine.macro_buffer)
                self.send_telegram_sync(f"📊 <b>Data Warming up... [ {current_count} / 100 ]</b> (Period {next_period_str})")
                return

            actual_big = 1 if digit >= 5 else 0
            if self.last_decision and self.last_decision.signal in ["BIG", "SMALL"] and not self.last_decision.is_noise_filtered:
                last_won = ((1 if self.last_decision.signal == "BIG" else 0) == actual_big)
                self.engine.record_outcome(last_won)
                
                adaptive_force = self.last_decision.is_adaptive_streak and last_won
                settle = self.betting.apply_result(last_won, adaptive_force)

                if last_won:
                    if "ADAPTIVE_WW_STREAK_RESET" in settle['action']:
                        old_lvl = settle['old_level']
                        win_msg = (
                            f"🔥 WIN ✅ (+{settle['profit']:,.0f})\n"
                            f"🎉 BET2 WIN → Level 1 RESET\n"
                            f"🔄 Level {old_lvl} → Level 1"
                        )
                    else:
                        win_msg = (
                            f"🔥 WIN ✅ (+{settle['profit']:,.0f})\n"
                            f"🎯 Bet1 → Bet2 "
                        )
                    self.send_telegram_sync(win_msg)
                    
                    if settle.get("target_hit", False):
                        milestone_msg = (
                            f"🏆🏆🏆🏆 <b>TARGET +100,000 GOD-TIER MILESTONE!</b> 🏆🏆🏆🏆\n"
                            f"━━━━━━━━━━━━━━━━━\n"
                            f"📉 Max DD: {self.betting.max_loss_amount:+,.0f}\n"
                            f"📈 Max Level Reached: {self.betting.max_level_reached}\n"
                            f"💵 Profit: +100,000 MMK"
                        )
                        self.send_telegram_sync(milestone_msg)
                        self.betting.reset_milestone()
                else:
                    # Loss messages are disabled as requested.
                    pass

            self.engine.resolve(digit)
            decision = self.engine.predict(self.betting.level, self.betting.level_state)
            self.last_decision = decision

            bet_amt, b_type = self.betting.get_current_bet()
            self.betting.total_signals += 1
            max_lvl = self.betting.max_level_reached
            max_dd = self.betting.max_loss_amount
            current_profit = self.betting.current_profit
            win_rate = self.betting.get_wr()
            bot_step_val = self.betting.bot_step

            if decision.is_noise_filtered:
                skip_msg = f"💖 Period {next_period_str} SKIP ⏭️"
                self.send_telegram_sync(skip_msg)
                return

            if decision.is_adaptive_streak:
                msg = (
                    f"⚡⚡ <b>[GOD-TIER ADAPTIVE WW SIGNAL]</b> ⚡⚡\n"
                    f"🛡️ Shield: <b>{decision.elite_type}</b>\n"
                    f"━━━━━━━━━━━━━━━━━\n"
                    f"💖 Period {next_period_str}\n"
                    f"🎯 SIGNAL → <b>{decision.signal.upper()}</b> 🔥\n"
                    f"━━━━━━━━━━━━━━━━━\n"
                    f"🤖 Bot Step: {bot_step_val}x \n"
                    f"🎮 Level: {self.betting.level} | {b_type}\n"
                    f"💰 Bet: {bet_amt:,}\n"
                    f"━━━━━━━━━━━━━━━━━\n"
                    f"🏆 Max Level: {max_lvl}\n"
                    f"📉 Max DD: {max_dd:+,.0f}\n"
                    f"💵 Profit: {current_profit:+,.0f}\n"
                    f"📊 WR: {win_rate:.1f}%"
                )
            else:
                msg = (
                    f"💖 Period {next_period_str}\n"
                    f"🎯 SIGNAL → {decision.signal.upper()} 🔥\n"
                    f"━━━━━━━━━━━━━━━━━\n"
                    f"🤖 Bot Step: {bot_step_val}x\n"
                    f"🎮 Level: {self.betting.level} | {b_type}\n"
                    f"💰 Bet: {bet_amt:,}\n"
                    f"━━━━━━━━━━━━━━━━━\n"
                    f"🏆 Max Level: {max_lvl}\n"
                    f"📉 Max DD: {max_dd:+,.0f}\n"
                    f"💵 Profit: {current_profit:+,.0f}\n"
                    f"📊 WR: {win_rate:.1f}%"
                )

            self.send_telegram_sync(msg)

    def start_polling_loop(self):
        def worker():
            print("[Adaptive Live Bot] Polling worker started...", flush=True)
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
GLOBAL_BOT: Optional[AdaptiveLiveBot] = None

@app.route("/")
def index():
    return "God-Tier Adaptive Noise-Gate Engine Active!", 200

@app.route("/health")
def health():
    return jsonify({"status": "healthy"}), 200

if __name__ == "__main__":
    GLOBAL_BOT = AdaptiveLiveBot()
    GLOBAL_BOT.start_polling_loop()
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
