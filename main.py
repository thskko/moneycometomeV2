"""
🚀 V20.0 — Hybrid Bot (Chart Priority + Rare Skip)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Features:
  1. Chart Priority (Trend Strong → Chart Override)
  2. Conflict Detection (Chart vs Pattern)
  3. Rare Skip (15-25% only)
  4. Smart Combine (Agree/Override)
  5. 3000 Candles (SQLite)
  6. Auto Reactivate
  7. Telegram Commands
  8. Level State Machine
  9. Profit Reset
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import requests
import time
import os
import threading
import math
import sqlite3
import numpy as np
from collections import deque, Counter
from datetime import datetime
from flask import Flask

# ==========================================
# 🔑 CREDENTIALS
# ==========================================
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "8913070806:AAF3rP0zKJtofE-5KVesqcdoHzn7Go0avho")
CHAT_ID = os.environ.get("CHAT_ID", "-1004402480797")
LOTTERY_AUTH = os.environ.get("LOTTERY_AUTH", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpYXQiOiIxNzg3OTgxNTA5IiwibmJmIjoiMTc4Nzk4MTUwOSIsImV4cCI6IjE3ODc5ODMzMDkiLCJodHRwOi8vc2NoZW1hcy5taWNyb3NvZnQuY29tL3dzLzIwMDgvMDYvaWRlbnRpdHkvY2xhaW1zL2V4cGlyYXRpb24iOiI4LzI5LzIwMjYgMTI6MzE2NDkgUE0iLCJodHRwOi8vc2NoZW1hcy5taWNyb3NvZnQuY29tL3dzLzIwMDgvMDYvaWRlbnRpdHkvY2xhaW1zL3JvbGUiOiJBY2Nlc3NfVG9rZW4iLCJVc2VySWQiOiIxMDEyMjEzIiwiVXNlck5hbWUiOiI5NTk3NDA5MzkzNzAiLCJVc2VyUGhvdG8iOiI5IiwiTmlja05hbWUiOiJUaGVrR3lpIiwiQW1vdW50IjoiODcuMzAiLCJJbnRlZ3JhbCI6IjAiLCJMb2dpbk1hcmsiOiJINSIsImxvZ2luVGltZSI6IjcvMjkvMjAyNiAxMjowMTo0OSBQTSIsImxvZ2luSVBBZGRyZXNzIjoiNDUuNDEuMTA0LjI0MCIsImRiTnVtYmVyIjoiMCIsIklzdmFsaWRhdG9yIjoiMCIsIktleUNvZGUiOiIzMjMzMiIsImRva2VuVHlwZSI6IjJBY2Nlc3NfVG9rZW4iLCJob25lVHlwZSI6IjAiLCJVc2VyVHlwZSI6IjAiLCJVc2VyTmFtZ2UiOiIuIiwiaXNzIjoiand0SXNzdWVyIiwiYXVkIjoibG90dGVyeVRpY2tldCJ9.ZL0Y9gexUTCsKwWeZhCLAAw8AABEYJt0GnIzIviMG4g")

COLOUR_MAP = {
    0: "Violet+Red", 1: "Green", 2: "Red", 3: "Green", 4: "Red",
    5: "Violet+Green", 6: "Red", 7: "Green", 8: "Red", 9: "Green",
}

# ==========================================
# ⚙️ CONFIG
# ==========================================
CONFIG = {
    "window_size": 60,
    "candle_max_size": 3000,
    "candle_db_path": "candles.db",
    "min_data_before_signal": 30,
    "adaptive_base_threshold": 0.55,
    "min_margin": 0.08,
    "min_agents_for_signal": 1,
    "min_agent_wr": 0.50,
    "reactivate_wr": 0.55,
    "suspend_wr": 0.45,
    "min_sample": 30,
    "chart_weight": 0.60,
    "pattern_weight": 0.40,
    "conflict_threshold": 0.05,
    "api_url": "https://6lotteryapi.com/api/webapi/GetNoaverageEmerdList",
    "payout_rate": 0.96,
    "profit_reset_threshold": 100000,
    "max_level": 15,
}

# ==========================================
# 📊 LEVEL TABLE
# ==========================================
LEVEL_TABLE = {
    1:  {"bet1": 1000,    "bet2": 2000},
    2:  {"bet1": 1000,    "bet2": 2000},
    3:  {"bet1": 2000,    "bet2": 4000},
    4:  {"bet1": 2000,    "bet2": 4000},
    5:  {"bet1": 3000,    "bet2": 6000},
    6:  {"bet1": 4000,    "bet2": 8000},
    7:  {"bet1": 6000,    "bet2": 12000},
    8:  {"bet1": 8000,    "bet2": 16000},
    9:  {"bet1": 10000,   "bet2": 20000},
    10: {"bet1": 14000,   "bet2": 28000},
    11: {"bet1": 19000,   "bet2": 38000},
    12: {"bet1": 25000,   "bet2": 50000},
    13: {"bet1": 34000,   "bet2": 68000},
    14: {"bet1": 46000,   "bet2": 92000},
    15: {"bet1": 62000,   "bet2": 124000},
    16: {"bet1": 83000,   "bet2": 166000},
    17: {"bet1": 112000,  "bet2": 224000},
    18: {"bet1": 151000,  "bet2": 302000},
    19: {"bet1": 203000,  "bet2": 406000},
    20: {"bet1": 274000,  "bet2": 548000},
}


def get_level_bet(level):
    if level in LEVEL_TABLE:
        return LEVEL_TABLE[level]
    a = LEVEL_TABLE[19]["bet1"]
    b = LEVEL_TABLE[20]["bet1"]
    for _ in range(level - 20):
        a, b = b, a + b
    return {"bet1": b, "bet2": b * 2}


app = Flask(__name__)
global_agent = None


# ==========================================
# 📈 DFA
# ==========================================
def calculate_dfa(series, min_scale=6, max_scale=None):
    try:
        data = np.asarray(series, dtype=np.float64)
        N = len(data)
        if N < 16:
            return 0.5
        if max_scale is None:
            max_scale = N // 3
        if max_scale <= min_scale:
            return 0.5
        y = np.cumsum(data - np.mean(data))
        scales = np.unique(np.logspace(np.log10(min_scale), np.log10(max_scale), num=6).astype(int))
        fluctuations, valid_scales = [], []
        for s in scales:
            num_segments = N // s
            if num_segments < 2:
                continue
            segment_rms = []
            x_axis = np.arange(s)
            for i in range(num_segments):
                segment = y[i * s : (i + 1) * s]
                poly = np.polyfit(x_axis, segment, 1)
                trend = np.polyval(poly, x_axis)
                segment_rms.append(np.mean((segment - trend) ** 2))
            if segment_rms:
                f_s = np.sqrt(np.mean(segment_rms))
                if f_s > 1e-6:
                    fluctuations.append(f_s)
                    valid_scales.append(s)
        if len(valid_scales) < 2:
            return 0.5
        alpha, _ = np.polyfit(np.log(valid_scales), np.log(fluctuations), 1)
        return float(np.clip(alpha, 0.1, 1.4))
    except Exception:
        return 0.5


# ==========================================
# 🧠 FEATURE ENGINEER
# ==========================================
class FeatureEngineer:
    @staticmethod
    def encode(r):
        return 1 if r == "Big" else 0

    @staticmethod
    def streak(encoded):
        if not encoded:
            return 0
        count = 1
        for i in range(len(encoded) - 2, -1, -1):
            if encoded[i] == encoded[-1]:
                count += 1
            else:
                break
        return count

    @staticmethod
    def alternating_streak(encoded):
        if len(encoded) < 2:
            return 0
        count = 1
        for i in range(len(encoded) - 2, -1, -1):
            if encoded[i] != encoded[i + 1]:
                count += 1
            else:
                break
        return count

    @staticmethod
    def entropy(encoded, window=20):
        if len(encoded) < window:
            return 0.5
        recent = encoded[-window:]
        p_big = sum(recent) / window
        p_small = 1 - p_big
        if p_big == 0 or p_small == 0:
            return 0.0
        return -(p_big * math.log2(p_big) + p_small * math.log2(p_small))

    @staticmethod
    def std(lst):
        if len(lst) < 2:
            return 0.0
        mean = sum(lst) / len(lst)
        return math.sqrt(sum((x - mean) ** 2 for x in lst) / len(lst))

    @staticmethod
    def flip_rate(encoded):
        if len(encoded) < 2:
            return 0.0
        flips = sum(1 for i in range(len(encoded) - 1) if encoded[i] != encoded[i + 1])
        return flips / (len(encoded) - 1)


# ==========================================
# 📊 CANDLE DB (SQLite — 3000 Candles)
# ==========================================
class CandleDB:
    def __init__(self, db_path="candles.db", max_size=3000):
        self.db_path = db_path
        self.max_size = max_size
        self.lock = threading.Lock()
        self.candles = deque(maxlen=max_size)
        self.prev_close = 5.0
        self.last_period = None
        self._init_db()
        self._load_recent()

    def _init_db(self):
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS candles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    period TEXT UNIQUE,
                    digit INTEGER,
                    open REAL,
                    high REAL,
                    low REAL,
                    close REAL,
                    color TEXT,
                    big_small TEXT,
                    timestamp INTEGER
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_period ON candles(period)")
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"DB Init Error: {e}", flush=True)

    def _load_recent(self):
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("""
                SELECT period, digit, open, high, low, close, color, big_small, timestamp
                FROM candles ORDER BY id DESC LIMIT ?
            """, (self.max_size,))
            rows = cursor.fetchall()
            conn.close()

            for row in reversed(rows):
                self.candles.append({
                    "period": row[0],
                    "digit": row[1],
                    "open": row[2],
                    "high": row[3],
                    "low": row[4],
                    "close": row[5],
                    "color": row[6],
                    "big_small": row[7],
                    "timestamp": row[8],
                })
                self.prev_close = row[5]
                self.last_period = row[0]

            print(f"✅ Loaded {len(self.candles)} candles from DB", flush=True)
        except Exception as e:
            print(f"Load Error: {e}", flush=True)

    def add(self, digit, period=None):
        try:
            if period == self.last_period:
                return None

            open_price = self.prev_close
            close_price = float(digit)
            high_price = max(open_price, close_price) + 0.5
            low_price = min(open_price, close_price) - 0.5

            candle = {
                "period": period or str(int(time.time())),
                "digit": digit,
                "open": open_price,
                "high": high_price,
                "low": low_price,
                "close": close_price,
                "color": "green" if digit >= 5 else "red",
                "big_small": "Big" if digit >= 5 else "Small",
                "timestamp": int(time.time()),
            }

            with self.lock:
                self.candles.append(candle)
                self.prev_close = close_price
                self.last_period = candle["period"]

                try:
                    conn = sqlite3.connect(self.db_path)
                    cursor = conn.cursor()
                    cursor.execute("""
                        INSERT OR REPLACE INTO candles
                        (period, digit, open, high, low, close, color, big_small, timestamp)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        candle["period"], candle["digit"],
                        candle["open"], candle["high"],
                        candle["low"], candle["close"],
                        candle["color"], candle["big_small"],
                        candle["timestamp"]
                    ))
                    conn.commit()
                    conn.close()
                except Exception as e:
                    print(f"DB Insert Error: {e}", flush=True)

                self._prune()

            return candle
        except Exception as e:
            print(f"Candle Add Error: {e}", flush=True)
            return None

    def _prune(self):
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("""
                DELETE FROM candles WHERE id NOT IN (
                    SELECT id FROM candles ORDER BY id DESC LIMIT ?
                )
            """, (self.max_size,))
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"Prune Error: {e}", flush=True)

    def get_candles(self):
        with self.lock:
            return list(self.candles)

    def get_count(self):
        return len(self.candles)

    def get_closes(self):
        return [c["close"] for c in self.candles]

    def get_highs(self):
        return [c["high"] for c in self.candles]

    def get_lows(self):
        return [c["low"] for c in self.candles]


# ==========================================
# 📊 CHART WEB STYLE ANALYZER
# ==========================================
class ChartWebAnalyzer:
    """Chart Web ကအတိုင်း Analyze"""

    def analyze(self, candles):
        try:
            if len(candles) < 20:
                return None, 0, "Warming"

            closes = [c["close"] for c in candles]
            highs = [c["high"] for c in candles]
            lows = [c["low"] for c in candles]

            # 1. Trend Detection
            recent_highs = highs[-10:]
            recent_lows = lows[-10:]

            hh = all(recent_highs[i] <= recent_highs[i + 1] for i in range(len(recent_highs) - 1))
            hl = all(recent_lows[i] <= recent_lows[i + 1] for i in range(len(recent_lows) - 1))
            lh = all(recent_highs[i] >= recent_highs[i + 1] for i in range(len(recent_highs) - 1))
            ll = all(recent_lows[i] >= recent_lows[i + 1] for i in range(len(recent_lows) - 1))

            if hh and hl:
                return "Big", 0.65, "📈 Uptrend"

            if lh and ll:
                return "Small", 0.65, "📉 Downtrend"

            # 2. S/R Detection
            resistance = max(highs[-20:])
            support = min(lows[-20:])
            current = closes[-1]

            range_size = resistance - support
            if range_size == 0:
                range_size = 1.0

            position = (current - support) / range_size

            if position > 0.85:
                return "Small", 0.60, "🔴 Resistance"

            if position < 0.15:
                return "Big", 0.60, "🟢 Support"

            # 3. EMA
            ema9 = self._ema(closes, 9)
            ema21 = self._ema(closes, 21)
            ema50 = self._ema(closes, 50)

            if ema9 > ema21 > ema50:
                return "Big", 0.60, "📈 EMA Up"

            if ema9 < ema21 < ema50:
                return "Small", 0.60, "📉 EMA Down"

            # 4. Momentum
            if len(closes) >= 5:
                momentum = closes[-1] - closes[-5]

                if momentum > 1.5:
                    return "Big", 0.58, "🚀 Momentum Up"

                if momentum < -1.5:
                    return "Small", 0.58, "💥 Momentum Down"

            # 5. Trend Line (Regression)
            if len(closes) >= 20:
                x = np.arange(len(closes[-20:]))
                y = np.array(closes[-20:])
                slope, _ = np.polyfit(x, y, 1)

                if slope > 0.10:
                    return "Big", 0.56, "📈 Trend Line Up"

                if slope < -0.10:
                    return "Small", 0.56, "📉 Trend Line Down"

            return None, 0, "Neutral"

        except Exception as e:
            print(f"ChartAnalyzer Error: {e}", flush=True)
            return None, 0, "Error"

    def _ema(self, prices, period):
        try:
            if len(prices) < period:
                return prices[-1] if prices else 0
            alpha = 2 / (period + 1)
            ema = prices[0]
            for p in prices[1:]:
                ema = (p * alpha) + (ema * (1 - alpha))
            return ema
        except Exception:
            return 0


# ==========================================
# 🎯 PATTERN AGENTS
# ==========================================
class MeanReversionAgent:
    NAME = "mean_rev"

    def predict(self, encoded, window):
        try:
            if len(encoded) < 15:
                return None, 0
            short_mom = sum(encoded[-5:]) / 5
            long_ma = sum(encoded[-20:]) / 20 if len(encoded) >= 20 else sum(encoded) / len(encoded)
            deviation = short_mom - long_ma
            alpha = calculate_dfa(encoded)
            if 0.42 <= alpha <= 0.58:
                if deviation > 0.25:
                    return "Small", 0.58 + min(deviation * 0.3, 0.12)
                elif deviation < -0.25:
                    return "Big", 0.58 + min(abs(deviation) * 0.3, 0.12)
            if abs(deviation) > 0.35:
                pred = 0 if deviation > 0 else 1
                return ("Big" if pred == 1 else "Small"), 0.60
            return None, 0
        except Exception:
            return None, 0


class MarkovAgent:
    NAME = "markov"

    def predict(self, encoded, window):
        try:
            if len(encoded) < 10:
                return ("Big" if encoded[-1] == 1 else "Small"), 0.52
            order = 2
            history = list(encoded)
            transitions = {}
            for i in range(len(history) - order):
                state = tuple(history[i:i + order])
                next_val = history[i + order]
                if state not in transitions:
                    transitions[state] = [0, 0]
                transitions[state][next_val] += 1
            curr_state = tuple(history[-order:])
            if curr_state in transitions:
                zeros, ones = transitions[curr_state]
                total = zeros + ones
                if total > 0:
                    p_one = ones / total
                    if p_one >= 0.5:
                        return "Big", min(0.50 + (p_one - 0.5) * 0.4, 0.78)
                    else:
                        return "Small", min(0.50 + (0.5 - p_one) * 0.4, 0.78)
            return ("Big" if history[-1] == 1 else "Small"), 0.51
        except Exception:
            return None, 0


class KNNAgent:
    NAME = "knn"

    def predict(self, encoded, window, k=4):
        try:
            if len(encoded) < 25:
                return ("Big" if encoded[-1] == 1 else "Small"), 0.51
            target = list(encoded[-k:])
            matches = []
            for i in range(len(encoded) - k - 1):
                if list(encoded[i:i + k]) == target:
                    matches.append(encoded[i + k])
            if not matches:
                return ("Big" if encoded[-1] == 1 else "Small"), 0.51
            big_c = sum(matches)
            small_c = len(matches) - big_c
            if big_c >= small_c:
                return "Big", min(0.50 + (big_c / len(matches)) * 0.25, 0.75)
            else:
                return "Small", min(0.50 + (small_c / len(matches)) * 0.25, 0.75)
        except Exception:
            return None, 0


class RunsTestAgent:
    NAME = "runs_test"

    def predict(self, encoded, window):
        try:
            if len(encoded) < 16:
                return ("Big" if encoded[-1] == 1 else "Small"), 0.51
            seq = list(encoded[-24:])
            n1 = sum(seq)
            n2 = len(seq) - n1
            if n1 == 0 or n2 == 0:
                return ("Big" if encoded[-1] == 1 else "Small"), 0.55
            runs = 1 + sum(1 for i in range(len(seq) - 1) if seq[i] != seq[i + 1])
            mu = (2 * n1 * n2) / (n1 + n2) + 1
            variance = (2 * n1 * n2 * (2 * n1 * n2 - n1 - n2)) / (((n1 + n2) ** 2) * (n1 + n2 - 1))
            if variance <= 0:
                return ("Big" if encoded[-1] == 1 else "Small"), 0.51
            z = (runs - mu) / math.sqrt(variance)
            last = encoded[-1]
            if z < -1.0:
                return ("Big" if last == 1 else "Small"), 0.58
            elif z > 1.0:
                return ("Small" if last == 1 else "Big"), 0.58
            return ("Big" if last == 1 else "Small"), 0.51
        except Exception:
            return None, 0


class FibonacciAgent:
    NAME = "fibonacci"

    def predict(self, encoded, window):
        try:
            if len(encoded) < 15:
                return None, 0
            fibs = [3, 5, 8, 13]
            votes = {0: 0.0, 1: 0.0}
            for fib in fibs:
                if len(encoded) < fib + 1:
                    continue
                if encoded[-1] == encoded[-(fib + 1)]:
                    votes[encoded[-(fib - 1)]] += 1.0 / fib
            total = votes[0] + votes[1]
            if total < 0.3:
                return None, 0
            pred = 1 if votes[1] > votes[0] else 0
            conf = max(votes.values()) / total
            return ("Big" if pred == 1 else "Small"), min(0.55 + conf * 0.25, 0.75)
        except Exception:
            return None, 0


class PatternAgent:
    NAME = "pattern"

    def predict(self, encoded, window):
        try:
            if len(encoded) < 8:
                return None, 0
            alt_streak = FeatureEngineer.alternating_streak(encoded)
            if alt_streak >= 3:
                pred = 1 - encoded[-1]
                conf = 0.58 + min((alt_streak - 3) * 0.03, 0.15)
                return ("Big" if pred == 1 else "Small"), conf
            streak = FeatureEngineer.streak(encoded)
            if streak >= 5:
                pred = 1 - encoded[-1]
                return ("Big" if pred == 1 else "Small"), 0.68
            elif streak >= 4:
                pred = encoded[-1]
                return ("Big" if pred == 1 else "Small"), 0.62
            return None, 0
        except Exception:
            return None, 0


class BreakoutAgent:
    NAME = "breakout"

    def predict(self, encoded, window):
        try:
            if len(encoded) < 8:
                return None, 0
            recent_std = FeatureEngineer.std(encoded[-5:])
            short_mom = sum(encoded[-3:]) / 3
            prev_mom = sum(encoded[-6:-3]) / 3 if len(encoded) >= 6 else 0.5
            accel = short_mom - prev_mom
            if abs(accel) > 0.25:
                pred = 1 if accel > 0 else 0
                conf = 0.56 + min(abs(accel) * 0.3, 0.15)
                return ("Big" if pred == 1 else "Small"), conf
            if recent_std > 0.48:
                pred = 1 - encoded[-1]
                return ("Big" if pred == 1 else "Small"), 0.55
            return None, 0
        except Exception:
            return None, 0


class TrendAgent:
    NAME = "trend"

    def predict(self, encoded, window):
        try:
            if len(encoded) < 15:
                return None, 0
            streak = FeatureEngineer.streak(encoded)
            if streak >= 3:
                pred = encoded[-1]
                conf = 0.62 + min(streak * 0.03, 0.18)
                return ("Big" if pred == 1 else "Small"), min(conf, 0.82)
            ma_short = sum(encoded[-10:]) / 10
            ma_long = sum(encoded[-30:]) / 30 if len(encoded) >= 30 else sum(encoded) / len(encoded)
            trend_strength = abs(ma_short - ma_long)
            alpha = calculate_dfa(encoded)
            if trend_strength > 0.15 and alpha > 0.52:
                pred = 1 if encoded[-1] == 1 else 0
                conf = 0.58 + min(trend_strength * 0.5, 0.15)
                return ("Big" if pred == 1 else "Small"), min(conf, 0.78)
            return None, 0
        except Exception:
            return None, 0


class DigitBiasAgent:
    NAME = "digit_bias"

    def predict(self, digit_history):
        try:
            if len(digit_history) < 15:
                return None, 0
            recent = list(digit_history)[-10:]
            avg_val = sum(recent) / len(recent)
            if avg_val > 5.5:
                return "Small", min(0.55 + (avg_val - 4.5) * 0.05, 0.70)
            elif avg_val < 3.5:
                return "Big", min(0.55 + (4.5 - avg_val) * 0.05, 0.70)
            last_d = digit_history[-1]
            return ("Big" if last_d >= 5 else "Small"), 0.52
        except Exception:
            return None, 0


class EMARibbonAgent:
    NAME = "ema_ribbon"

    def _calc_ema(self, data, span):
        alpha = 2 / (span + 1)
        ema = data[0]
        for val in data[1:]:
            ema = (val * alpha) + (ema * (1 - alpha))
        return ema

    def predict(self, encoded, window):
        try:
            if len(encoded) < 15:
                return ("Big" if encoded[-1] == 1 else "Small"), 0.51
            ema_fast = self._calc_ema(encoded[-5:], 3)
            ema_mid = self._calc_ema(encoded[-10:], 8)
            ema_slow = self._calc_ema(encoded[-15:], 15)
            if ema_fast > ema_mid > ema_slow:
                conf = 0.55 + min((ema_fast - 0.5) * 0.3, 0.20)
                return "Big", conf
            elif ema_fast < ema_mid < ema_slow:
                conf = 0.55 + min((0.5 - ema_fast) * 0.3, 0.20)
                return "Small", conf
            return ("Big" if ema_fast >= 0.5 else "Small"), 0.52
        except Exception:
            return None, 0


# ==========================================
# 🧠 MARKET DETECTOR
# ==========================================
class MarketDetector:
    def detect(self, encoded):
        try:
            if len(encoded) < 15:
                return "unknown", 0.5
            streak = FeatureEngineer.streak(encoded)
            if streak >= 4:
                return "trending", 0.65
            alpha = calculate_dfa(encoded)
            entropy = FeatureEngineer.entropy(encoded, 20)
            flip_rate = FeatureEngineer.flip_rate(encoded[-20:])
            short_mom = sum(encoded[-5:]) / 5
            long_mom = sum(encoded[-20:]) / 20 if len(encoded) >= 20 else 0.5
            momentum_shift = short_mom - long_mom
            std = FeatureEngineer.std(encoded[-10:])
            if alpha > 0.55 and abs(momentum_shift) > 0.22:
                return "trending", alpha
            if entropy > 0.90 and flip_rate > 0.60:
                return "choppy", entropy
            if alpha < 0.48 and abs(momentum_shift) < 0.18:
                return "sideway", 1 - alpha
            if std > 0.52:
                return "volatile", std
            return "neutral", 0.5
        except Exception:
            return "unknown", 0.5


# ==========================================
# 📊 CONFIDENCE CALIBRATOR
# ==========================================
class ConfidenceCalibrator:
    def __init__(self):
        self.buckets = {
            "50-55": {"wins": 0, "total": 0},
            "55-60": {"wins": 0, "total": 0},
            "60-65": {"wins": 0, "total": 0},
            "65-70": {"wins": 0, "total": 0},
            "70-80": {"wins": 0, "total": 0},
            "80+": {"wins": 0, "total": 0},
        }

    def get_bucket(self, conf):
        if conf < 0.55: return "50-55"
        elif conf < 0.60: return "55-60"
        elif conf < 0.65: return "60-65"
        elif conf < 0.70: return "65-70"
        elif conf < 0.80: return "70-80"
        else: return "80+"

    def record(self, conf, won):
        try:
            bucket = self.get_bucket(conf)
            self.buckets[bucket]["total"] += 1
            if won:
                self.buckets[bucket]["wins"] += 1
        except Exception:
            pass

    def calibrate(self, conf):
        try:
            bucket = self.get_bucket(conf)
            data = self.buckets[bucket]
            if data["total"] >= 20:
                return data["wins"] / data["total"]
            return conf
        except Exception:
            return conf


# ==========================================
# 🎯 META-AGENT (Chart Priority)
# ==========================================
class MetaAgent:
    def __init__(self):
        self.all_agents = {
            "mean_rev": MeanReversionAgent(),
            "markov": MarkovAgent(),
            "knn": KNNAgent(),
            "runs_test": RunsTestAgent(),
            "fibonacci": FibonacciAgent(),
            "pattern": PatternAgent(),
            "breakout": BreakoutAgent(),
            "trend": TrendAgent(),
            "digit_bias": DigitBiasAgent(),
            "ema_ribbon": EMARibbonAgent(),
        }

        self.chart_analyzer = ChartWebAnalyzer()

        self.active_agents = [
            "mean_rev", "markov", "knn", "runs_test",
            "fibonacci", "pattern"
        ]
        self.suspended_agents = [
            "breakout", "trend", "digit_bias", "ema_ribbon"
        ]

        self.thompson_stats = {k: {"a": 2, "b": 2} for k in self.all_agents.keys()}
        self.agent_acc = {k: deque(maxlen=50) for k in self.thompson_stats}
        self.pending_agents = {}

    def get_agent_wr(self, name):
        try:
            if len(self.agent_acc[name]) >= 20:
                return sum(self.agent_acc[name]) / len(self.agent_acc[name])
            return 0.50
        except Exception:
            return 0.50

    def get_active_agents(self, regime):
        try:
            base = {
                "trending": ["mean_rev", "markov", "knn", "fibonacci", "pattern", "trend", "ema_ribbon"],
                "sideway": ["mean_rev", "pattern", "fibonacci", "knn", "markov"],
                "choppy": ["pattern", "fibonacci", "mean_rev", "markov", "knn"],
                "volatile": ["markov", "knn", "mean_rev", "fibonacci", "runs_test", "breakout"],
                "neutral": ["mean_rev", "markov", "knn", "runs_test", "fibonacci", "pattern"],
                "unknown": ["mean_rev", "markov", "knn", "runs_test", "fibonacci", "pattern"],
            }
            candidates = base.get(regime, base["neutral"])
            filtered = []
            for name in candidates:
                if name in self.active_agents:
                    wr = self.get_agent_wr(name)
                    if wr >= CONFIG['min_agent_wr'] or len(self.agent_acc[name]) < CONFIG['min_sample']:
                        filtered.append(name)
            return filtered if filtered else candidates[:3]
        except Exception:
            return ["mean_rev", "markov", "knn"]

    def check_reactivation(self):
        try:
            reactivated = []
            for name in self.suspended_agents[:]:
                if len(self.agent_acc[name]) >= CONFIG['min_sample']:
                    wr = sum(self.agent_acc[name]) / len(self.agent_acc[name])
                    if wr >= CONFIG['reactivate_wr']:
                        self.suspended_agents.remove(name)
                        self.active_agents.append(name)
                        reactivated.append((name, wr))
            return reactivated
        except Exception:
            return []

    def check_suspension(self):
        try:
            suspended = []
            for name in self.active_agents[:]:
                if len(self.agent_acc[name]) >= CONFIG['min_sample']:
                    wr = sum(self.agent_acc[name]) / len(self.agent_acc[name])
                    if wr < CONFIG['suspend_wr']:
                        self.active_agents.remove(name)
                        self.suspended_agents.append(name)
                        suspended.append((name, wr))
            return suspended
        except Exception:
            return []

    def get_thompson_weight(self, name):
        try:
            stats = self.thompson_stats.get(name, {"a": 2, "b": 2})
            thompson = float(np.random.beta(stats["a"], stats["b"]))
            if len(self.agent_acc[name]) >= 20:
                acc = sum(self.agent_acc[name]) / len(self.agent_acc[name])
                return thompson * (acc ** 2) * 3
            return thompson
        except Exception:
            return 1.0

    def predict(self, encoded, window, regime, digit_history, candles):
        """✅ V20.0 — Chart Priority + Rare Skip"""
        try:
            # ==========================================
            # 1. Chart Analyze
            # ==========================================
            chart_pred, chart_conf, chart_mode = self.chart_analyzer.analyze(candles)

            # ==========================================
            # 2. Pattern Agents
            # ==========================================
            active = self.get_active_agents(regime)
            signals = {}

            agents_map = {
                "mean_rev": lambda: self.all_agents["mean_rev"].predict(encoded, window),
                "markov": lambda: self.all_agents["markov"].predict(encoded, window),
                "knn": lambda: self.all_agents["knn"].predict(encoded, window),
                "runs_test": lambda: self.all_agents["runs_test"].predict(encoded, window),
                "fibonacci": lambda: self.all_agents["fibonacci"].predict(encoded, window),
                "pattern": lambda: self.all_agents["pattern"].predict(encoded, window),
                "breakout": lambda: self.all_agents["breakout"].predict(encoded, window),
                "trend": lambda: self.all_agents["trend"].predict(encoded, window),
                "digit_bias": lambda: self.all_agents["digit_bias"].predict(digit_history),
                "ema_ribbon": lambda: self.all_agents["ema_ribbon"].predict(encoded, window),
            }

            for name in active:
                try:
                    result = agents_map[name]()
                    if result and result[0] and result[1] > 0:
                        signals[name] = result
                except Exception as e:
                    print(f"Agent {name} Error: {e}", flush=True)

            # Pattern Voting
            pattern_big = 0.0
            pattern_small = 0.0

            for name, (pred, conf) in signals.items():
                weight = self.get_thompson_weight(name)
                weighted = conf * weight
                if pred == "Big":
                    pattern_big += weighted
                else:
                    pattern_small += weighted

            pattern_total = pattern_big + pattern_small

            if pattern_total > 0:
                if pattern_big > pattern_small:
                    pattern_pred = "Big"
                    pattern_conf = pattern_big / pattern_total
                else:
                    pattern_pred = "Small"
                    pattern_conf = pattern_small / pattern_total
            else:
                pattern_pred = None
                pattern_conf = 0

            # ==========================================
            # 3. V20.0 — Smart Combine
            # ==========================================
            # Case 1: Chart ရှိ + Pattern ရှိ
            if chart_pred and pattern_pred:
                # Agree
                if chart_pred == pattern_pred:
                    confidence = max(chart_conf, pattern_conf)
                    return chart_pred, confidence, f"🎯 Chart+Pattern Agree [{len(signals)}]", regime

                # Conflict
                else:
                    # Chart Trend Priority
                    if chart_mode in ["📈 Uptrend", "📉 Downtrend"]:
                        return chart_pred, chart_conf, f"🎯 Chart Priority ({chart_mode})", regime

                    # Chart Confidence မြင့်ရင် Chart
                    if chart_conf > pattern_conf + CONFIG['conflict_threshold']:
                        return chart_pred, chart_conf, f"🎯 Chart Override", regime

                    # Pattern Confidence မြင့်ရင် Pattern
                    if pattern_conf > chart_conf + CONFIG['conflict_threshold']:
                        return pattern_pred, pattern_conf, f"🎯 Pattern Override", regime

                    # Weight-based Fallback
                    chart_score = chart_conf * CONFIG['chart_weight']
                    pattern_score = pattern_conf * CONFIG['pattern_weight']

                    if chart_score > pattern_score:
                        return chart_pred, chart_conf, f"🎯 Chart Weight Win", regime
                    else:
                        return pattern_pred, pattern_conf, f"🎯 Pattern Weight Win", regime

            # Case 2: Chart Only
            elif chart_pred:
                return chart_pred, chart_conf, f"🎯 Chart Only ({chart_mode})", regime

            # Case 3: Pattern Only
            elif pattern_pred:
                return pattern_pred, pattern_conf, f"🎯 Pattern Only [{len(signals)}]", regime

            # Case 4: Both None — Rare Skip
            else:
                return None, 0, "No Signal", regime

        except Exception as e:
            print(f"MetaAgent Error: {e}", flush=True)
            return None, 0, "Error", regime

    def update_accuracy(self, actual):
        try:
            for name, pred in self.pending_agents.items():
                is_correct = 1 if pred == actual else 0
                if name in self.agent_acc:
                    self.agent_acc[name].append(is_correct)
                if name in self.thompson_stats:
                    if is_correct:
                        self.thompson_stats[name]["a"] += 1
                    else:
                        self.thompson_stats[name]["b"] += 1
            self.pending_agents.clear()
        except Exception as e:
            print(f"update_accuracy Error: {e}", flush=True)

    def record_pending(self, encoded, window, regime, digit_history):
        try:
            all_names = list(self.all_agents.keys())
            agents_map = {
                "mean_rev": lambda: self.all_agents["mean_rev"].predict(encoded, window),
                "markov": lambda: self.all_agents["markov"].predict(encoded, window),
                "knn": lambda: self.all_agents["knn"].predict(encoded, window),
                "runs_test": lambda: self.all_agents["runs_test"].predict(encoded, window),
                "fibonacci": lambda: self.all_agents["fibonacci"].predict(encoded, window),
                "pattern": lambda: self.all_agents["pattern"].predict(encoded, window),
                "breakout": lambda: self.all_agents["breakout"].predict(encoded, window),
                "trend": lambda: self.all_agents["trend"].predict(encoded, window),
                "digit_bias": lambda: self.all_agents["digit_bias"].predict(digit_history),
                "ema_ribbon": lambda: self.all_agents["ema_ribbon"].predict(encoded, window),
            }
            self.pending_agents = {}
            for name in all_names:
                try:
                    result = agents_map[name]()
                    if result and result[0]:
                        self.pending_agents[name] = result[0]
                except Exception:
                    pass
        except Exception as e:
            print(f"record_pending Error: {e}", flush=True)


# ==========================================
# 🎯 V20.0 ENGINE
# ==========================================
class V20Engine:
    def __init__(self):
        global global_agent
        global_agent = self
        self.lock = threading.Lock()
        self.window = deque(maxlen=CONFIG['window_size'])
        self.digit_history = deque(maxlen=120)
        self.candle_db = CandleDB(
            db_path=CONFIG['candle_db_path'],
            max_size=CONFIG['candle_max_size']
        )

        self.active_prediction = None
        self.last_state = None
        self.last_digit = None
        self.last_bot_step = None
        self.last_conf = 0.5

        self.market_detector = MarketDetector()
        self.meta_agent = MetaAgent()
        self.calibrator = ConfidenceCalibrator()
        self.current_regime = "unknown"

        self.bot_step = 1

        self.level = 1
        self.level_state = "WAITING_BET1"
        self.current_bet = 0

        self.total_signals = 0
        self.total_wins = 0
        self.total_losses = 0
        self.recent_results = deque(maxlen=100)
        self.total_profit = 0.0
        self.total_loss_amount = 0.0
        self.current_profit = 0.0
        self.max_loss_amount = 0.0
        self.max_profit_seen = 0.0
        self.cycles_completed = 0
        self.max_level_reached = 1
        self.profit_resets = 0

    def send_telegram(self, message):
        if not TELEGRAM_TOKEN or not CHAT_ID:
            print(f"[TG-DISABLED] {message[:80]}...", flush=True)
            return
        def _send():
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
            for _ in range(3):
                try:
                    res = requests.post(url, json={"chat_id": CHAT_ID, "text": message, "parse_mode": "HTML"}, timeout=15)
                    if res.status_code == 200:
                        return
                except Exception:
                    time.sleep(2)
        threading.Thread(target=_send, daemon=True).start()

    def get_wr(self):
        total = self.total_wins + self.total_losses
        return (self.total_wins / total * 100) if total > 0 else 0.0

    def update_max_tracking(self):
        if self.current_profit < self.max_loss_amount:
            self.max_loss_amount = self.current_profit
        if self.current_profit > self.max_profit_seen:
            self.max_profit_seen = self.current_profit

    def get_current_bet(self):
        info = get_level_bet(self.level)
        if self.level_state == "WAITING_BET1":
            return info["bet1"], "BET1"
        else:
            return info["bet2"], "BET2"

    def on_result(self, won):
        old_level = self.level
        old_state = self.level_state

        if self.level_state == "WAITING_BET1":
            if won:
                self.level_state = "WAITING_BET2"
                return "BET1_WIN", old_level, old_state
            else:
                self.level += 1
                self.level_state = "WAITING_BET1"
                if self.level > self.max_level_reached:
                    self.max_level_reached = self.level
                return "BET1_LOSE", old_level, old_state
        else:
            if won:
                self.level = 1
                self.level_state = "WAITING_BET1"
                self.cycles_completed += 1
                return "RESET", old_level, old_state
            else:
                self.level += 1
                self.level_state = "WAITING_BET1"
                if self.level > self.max_level_reached:
                    self.max_level_reached = self.level
                return "BET2_LOSE", old_level, old_state

    def update_bot_step(self, bot_won):
        if bot_won:
            self.bot_step = 1
        else:
            self.bot_step += 1

    def check_profit_reset(self):
        if self.current_profit >= CONFIG['profit_reset_threshold']:
            old_max = self.max_level_reached
            report = (
                f"🎉 <b>PROFIT RESET</b>\n\n"
                f"💰 Net Profit: <b>+{self.current_profit:,.0f}</b>\n\n"
                f"━━━━━━━━━━━━━━━━━\n"
                f"📈 Total Profit: <b>+{self.total_profit:,.0f}</b>\n"
                f"📉 Total Loss: <b>-{self.total_loss_amount:,.0f}</b>\n"
                f"🔻 Max DD: <b>{self.max_loss_amount:,.0f}</b>\n\n"
                f"🏆 Max Level: <b>{old_max}</b>\n"
                f"🔄 Reset → Level 1"
            )
            self.total_profit = 0.0
            self.total_loss_amount = 0.0
            self.current_profit = 0.0
            self.max_loss_amount = 0.0
            self.max_profit_seen = 0.0
            self.level = 1
            self.level_state = "WAITING_BET1"
            self.bot_step = 1
            self.max_level_reached = 1
            self.cycles_completed = 0
            self.profit_resets += 1
            return report
        return None

    def get_threshold(self):
        base = CONFIG['adaptive_base_threshold']
        if len(self.recent_results) >= 20:
            recent_wr = sum(self.recent_results) / len(self.recent_results)
            if recent_wr >= 0.65: base -= 0.03
            elif recent_wr < 0.45: base += 0.03
        return max(0.50, min(base, 0.65))

    def get_consensus(self):
        try:
            encoded = [FeatureEngineer.encode(r) for r in self.window]
            candles = self.candle_db.get_candles()

            regime, _ = self.market_detector.detect(encoded)
            self.current_regime = regime

            pred, conf, mode, regime = self.meta_agent.predict(
                encoded, self.window, regime, self.digit_history, candles
            )

            if pred is None:
                return None, 0, mode, regime

            calib_conf = self.calibrator.calibrate(conf)
            threshold = self.get_threshold()
            if calib_conf < threshold:
                return None, 0, f"Low Conf {calib_conf:.1%}", regime

            return pred, calib_conf, mode, regime
        except Exception as e:
            print(f"get_consensus Error: {e}", flush=True)
            return None, 0, "Error", "unknown"

    def process_api_result(self, api_period, api_result, digit=None):
        with self.lock:
            self._process_internal(api_period, api_result, digit)

    def _process_internal(self, api_period, api_result, digit):
        try:
            api_period_int = int(api_period)
        except Exception:
            return
        notifications = []

        if digit is not None:
            self.last_digit = digit
            self.digit_history.append(digit)
            self.candle_db.add(digit, period=api_period)

        # Verify Previous
        if self.active_prediction is not None and self.last_state is not None:
            bot_won = (self.active_prediction == api_result)
            self.recent_results.append(1 if bot_won else 0)

            self.meta_agent.update_accuracy(api_result)
            self.calibrator.record(self.last_conf, bot_won)

            if bot_won:
                self.total_wins += 1
            else:
                self.total_losses += 1

            bet_amount, bet_type = self.get_current_bet()

            if bot_won:
                profit_amount = bet_amount * CONFIG['payout_rate']
                self.total_profit += profit_amount
                self.current_profit += profit_amount
            else:
                profit_amount = -bet_amount
                self.total_loss_amount += bet_amount
                self.current_profit -= bet_amount

            self.update_max_tracking()
            action, old_level, old_state = self.on_result(bot_won)

            if bot_won:
                if action == "RESET":
                    notifications.append(
                        f"🔥 <b>WIN ✅</b> (+{profit_amount:,.0f})\n"
                        f"🎉 <b>BET2 WIN → Level 1 RESET</b>\n"
                        f"🔄 Level {old_level} → Level 1\n\n"
                        f"💵 Profit: {self.current_profit:+,.0f}\n"
                        f"📊 WR: {self.get_wr():.1f}%"
                    )
                else:
                    notifications.append(
                        f"🔥 <b>WIN ✅</b> (+{profit_amount:,.0f})\n"
                        f"🎯 Bet1 Win → Bet2 စောင့်\n"
                        f"🎮 Level: {self.level} | BET2\n\n"
                        f"💵 Profit: {self.current_profit:+,.0f}\n"
                        f"📊 WR: {self.get_wr():.1f}%"
                    )

            if action in ("BET1_LOSE", "BET2_LOSE"):
                notifications.append(
                    f"📈 <b>LEVEL UP</b>\n"
                    f"🔄 Level {old_level} → Level {self.level}\n"
                    f"💰 Next Bet1: {get_level_bet(self.level)['bet1']:,}"
                )

            # Reactivation/Suspension
            reactivated = self.meta_agent.check_reactivation()
            for name, wr in reactivated:
                notifications.append(f"✅ <b>Agent Reactivated</b>\n{name}: {wr:.1%}")

            suspended = self.meta_agent.check_suspension()
            for name, wr in suspended:
                notifications.append(f"⏸️ <b>Agent Suspended</b>\n{name}: {wr:.1%}")

            self.update_bot_step(bot_won)
            self.active_prediction = None
            self.last_state = None
            self.last_bot_step = None

            reset_report = self.check_profit_reset()
            if reset_report:
                notifications.append(reset_report)

        else:
            self.meta_agent.update_accuracy(api_result)

        self.window.append(api_result)
        next_period_short = str(api_period_int + 1)[-3:]

        if len(self.window) < CONFIG['min_data_before_signal']:
            notifications.append(
                f"💖 Period {next_period_short}\n"
                f"⏳ Data: {len(self.window)}/{CONFIG['min_data_before_signal']}"
            )
        else:
            encoded = [FeatureEngineer.encode(r) for r in self.window]
            pred, conf, mode, regime = self.get_consensus()

            if pred is None:
                notifications.append(
                    f"💖 Period {next_period_short}\n"
                    f"⏭️ <b>SKIP</b> ({mode})"
                )
            else:
                self.active_prediction = pred
                self.last_state = "active"
                self.total_signals += 1
                self.last_bot_step = self.bot_step
                self.last_conf = conf

                self.meta_agent.record_pending(
                    encoded, self.window, regime, self.digit_history
                )

                bet_amount, bet_type = self.get_current_bet()

                notifications.append(
                    f"💖 <b>Period {next_period_short}</b>\n"
                    f"🎯 <b>SIGNAL → {pred.upper()}</b>\n"
                    f"📊 Conf: <b>{conf:.1%}</b>\n"
                    f"⚙️ {mode}\n"
                    f"━━━━━━━━━━━━━━━━━\n"
                    f"🤖 Bot Step: <b>{self.bot_step}x</b>\n"
                    f"🎮 Level: <b>{self.level}</b> | {bet_type}\n"
                    f"💰 Bet: <b>{bet_amount:,}</b>\n"
                    f"━━━━━━━━━━━━━━━━━\n"
                    f"🏆 Max Level: {self.max_level_reached}\n"
                    f"📉 Max DD: {self.max_loss_amount:,.0f}\n"
                    f"💵 Profit: {self.current_profit:+,.0f}\n"
                    f"📊 WR: {self.get_wr():.1f}%\n"
                    f"🎨 Last: {digit} ({COLOUR_MAP.get(digit, '?')})"
                )

        for msg in notifications:
            self.send_telegram(msg)
            time.sleep(0.3)


# ==========================================
# 📱 TELEGRAM COMMANDS
# ==========================================
def poll_telegram(agent):
    try:
        requests.get(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/deleteWebhook?drop_pending_updates=true",
            timeout=10
        )
    except Exception:
        pass

    offset = 0
    while True:
        try:
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates?offset={offset}&timeout=20"
            res = requests.get(url, timeout=25)
            if res.status_code == 200:
                for upd in res.json().get("result", []):
                    offset = upd["update_id"] + 1
                    msg = upd.get("message", {})
                    chat = str(msg.get("chat", {}).get("id", ""))
                    text = msg.get("text", "").strip().lower()

                    if chat != CHAT_ID:
                        continue

                    if text == "/status":
                        b, bt = agent.get_current_bet()
                        agent.send_telegram(
                            f"📊 <b>STATUS</b>\n\n"
                            f"🎯 Regime: <b>{agent.current_regime}</b>\n"
                            f"🤖 Bot Step: <b>{agent.bot_step}x</b>\n"
                            f"🎮 Level: <b>{agent.level}</b> | {agent.level_state}\n"
                            f"💰 Bet: <b>{b:,}</b> ({bt})\n\n"
                            f"🏆 Max Level: {agent.max_level_reached}\n"
                            f"📉 Max DD: {agent.max_loss_amount:+,.0f}\n"
                            f"💵 Profit: {agent.current_profit:+,.0f}\n"
                            f"📊 WR: {agent.get_wr():.1f}%\n"
                            f"📈 {agent.total_wins}W / {agent.total_losses}L\n"
                            f"🎯 Signals: {agent.total_signals}\n"
                            f"🕯️ Candles: {agent.candle_db.get_count()}"
                        )

                    elif text == "/reset":
                        with agent.lock:
                            agent.level = 1
                            agent.level_state = "WAITING_BET1"
                            agent.bot_step = 1
                            agent.current_profit = 0.0
                            agent.total_profit = 0.0
                            agent.total_loss_amount = 0.0
                            agent.total_wins = 0
                            agent.total_losses = 0
                            agent.max_loss_amount = 0.0
                            agent.max_level_reached = 1
                            agent.cycles_completed = 0
                            agent.total_signals = 0
                            agent.recent_results.clear()
                        agent.send_telegram("🔄 <b>Manual Reset Done</b>")

                    elif text == "/agent_stats":
                        msg_text = "📊 <b>Agent Stats</b>\n\n"
                        stats_list = []
                        for name, acc_deque in agent.meta_agent.agent_acc.items():
                            if len(acc_deque) >= 5:
                                acc = sum(acc_deque) / len(acc_deque)
                                stats_list.append((name, acc, len(acc_deque)))
                            else:
                                stats_list.append((name, 0, len(acc_deque)))
                        stats_list.sort(key=lambda x: x[1], reverse=True)
                        for name, acc, n in stats_list:
                            status = "✅" if name in agent.meta_agent.active_agents else "⏸️"
                            if n >= 5:
                                msg_text += f"{status} <b>{name}</b>: {acc:.1%} (n={n})\n"
                            else:
                                msg_text += f"{status} {name}: warming ({n})\n"
                        msg_text += f"\n<b>Active:</b> {len(agent.meta_agent.active_agents)}"
                        msg_text += f"\n<b>Suspended:</b> {len(agent.meta_agent.suspended_agents)}"
                        agent.send_telegram(msg_text)

                    elif text == "/profit":
                        agent.send_telegram(
                            f"💰 <b>PROFIT</b>\n\n"
                            f"💵 Net: <b>{agent.current_profit:+,.0f}</b>\n"
                            f"📈 Total Profit: <b>+{agent.total_profit:,.0f}</b>\n"
                            f"📉 Total Loss: <b>-{agent.total_loss_amount:,.0f}</b>\n"
                            f"🏆 Max Level: <b>{agent.max_level_reached}</b>\n"
                            f"📉 Max DD: <b>{agent.max_loss_amount:,.0f}</b>"
                        )

                    elif text == "/help":
                        agent.send_telegram(
                            f"📚 <b>COMMANDS</b>\n\n"
                            f"/status — Bot Status\n"
                            f"/reset — Manual Reset\n"
                            f"/agent_stats — Agent Performance\n"
                            f"/profit — Profit Stats\n"
                            f"/help — Commands List"
                        )

        except Exception as e:
            print(f"TG Poll Error: {e}", flush=True)
        time.sleep(1)


# ==========================================
# 🌐 API POLLER
# ==========================================
def run_bot():
    print("🚀 V20.0 — Chart Priority + Rare Skip", flush=True)
    agent = V20Engine()

    threading.Thread(target=poll_telegram, args=(agent,), daemon=True).start()

    last_processed_period = None
    url = CONFIG['api_url']
    auth = LOTTERY_AUTH
    headers = {
        "accept": "application/json, text/plain, */*",
        "authorization": f"Bearer {auth}",
        "content-type": "application/json;charset=UTF-8",
        "origin": "https://6win598.com",
        "referer": "https://6win598.com/",
        "user-agent": "Mozilla/5.0"
    }

    while True:
        try:
            payload = {
                "pageSize": 10, "pageNo": 1, "typeId": 30, "language": 7,
                "random": "036263f367384d418be07465793c8da8",
                "signature": "55F4FD150F15F090B943374F3C9BE78B",
                "timestamp": int(time.time())
            }
            res = requests.post(url, headers=headers, json=payload, timeout=5)
            if res.status_code != 200:
                time.sleep(1.5)
                continue
            data = res.json().get("data", {}).get("list", [])
            if not data:
                time.sleep(1.5)
                continue
            latest = data[0]
            raw_period = str(latest.get("issueNumber"))
            number = int(latest.get("number"))
            api_result = "Big" if number >= 5 else "Small"
            if raw_period != last_processed_period:
                last_processed_period = raw_period
                print(f"📥 Period {raw_period} → {api_result} ({number})", flush=True)
                agent.process_api_result(raw_period, api_result, number)
        except Exception as e:
            print(f"Poll Error: {e}", flush=True)
        time.sleep(1.2)


# ==========================================
# 🌐 FLASK
# ==========================================
@app.route('/')
def home():
    if not global_agent:
        return "<h3>🚀 V20.0 starting...</h3>"
    a = global_agent
    bet_amount, bet_type = a.get_current_bet()
    return f"""
    <h2>🚀 V20.0 — Chart Priority + Rare Skip</h2>
    <p><b>🎯 Regime:</b> {a.current_regime}</p>
    <p><b>🤖 Bot Step:</b> {a.bot_step}x</p>
    <p><b>🎮 Level:</b> {a.level} | {a.level_state}</p>
    <p><b>💰 Bet:</b> {bet_amount:,} ({bet_type})</p>
    <p><b>💵 Profit:</b> {a.current_profit:+,.0f}</p>
    <p><b>📊 WR:</b> {a.get_wr():.1f}%</p>
    <p><b>🕯️ Candles:</b> {a.candle_db.get_count()}</p>
    <p><b>✅ Active:</b> {len(a.meta_agent.active_agents)} | ⏸️ Suspended: {len(a.meta_agent.suspended_agents)}</p>
    """

@app.route('/stats')
def stats():
    if global_agent:
        a = global_agent
        bet_amount, bet_type = a.get_current_bet()
        return {
            "version": "V20.0",
            "regime": a.current_regime,
            "bot_step": a.bot_step,
            "level": a.level,
            "level_state": a.level_state,
            "current_bet": bet_amount,
            "max_level": a.max_level_reached,
            "signals": a.total_signals,
            "wins": a.total_wins,
            "losses": a.total_losses,
            "win_rate": f"{a.get_wr():.2f}%",
            "net_profit": round(a.current_profit, 2),
            "max_loss": round(a.max_loss_amount, 2),
            "candles": a.candle_db.get_count(),
            "active_agents": len(a.meta_agent.active_agents),
            "suspended_agents": len(a.meta_agent.suspended_agents),
        }
    return {"status": "initializing"}

@app.route('/agent_stats')
def agent_stats():
    if global_agent:
        a = global_agent
        result = {}
        for name, acc_deque in a.meta_agent.agent_acc.items():
            if len(acc_deque) >= 5:
                acc = sum(acc_deque) / len(acc_deque)
                status = "ACTIVE" if name in a.meta_agent.active_agents else "SUSPENDED"
                result[name] = f"{acc:.1%} (n={len(acc_deque)}, {status})"
            else:
                result[name] = f"warming ({len(acc_deque)})"
        return dict(sorted(result.items(), key=lambda x: x[1], reverse=True))
    return {"status": "initializing"}

@app.route('/health')
def health():
    return {"status": "ok", "version": "V20.0"}


# ==========================================
# 🚀 ENTRY
# ==========================================
if __name__ == "__main__":
    threading.Thread(target=run_bot, daemon=True).start()
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
