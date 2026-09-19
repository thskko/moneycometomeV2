"""
🚀 V15.6 — Level 1-30+ State Machine
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Rules:
  1. Level N: WAITING_BET1 / WAITING_BET2
  2. Bet1 Lose → Level N+1 (WAITING_BET1)
  3. Bet1 Win → Level N (WAITING_BET2)
  4. Bet2 Lose → Level N+1 (WAITING_BET1)
  5. Bet2 Win → Level 1 Reset 🎉
  6. Bot Step → Signal ထုတ်ဖို့ပဲ (Bet Style မထိ)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import requests
import time
import os
import threading
import math
import numpy as np
from collections import deque, Counter
from flask import Flask

# ==========================================
# 🔑 CREDENTIALS
# ==========================================
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "8913070806:AAF3rP0zKJtofE-5KVesqcdoHzn7Go0avho")
CHAT_ID = os.environ.get("CHAT_ID", "-1004402480797")
LOTTERY_AUTH = os.environ.get("LOTTERY_AUTH", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpYXQiOiIxNzg3OTgxNTA5IiwibmJmIjoiMTc4Nzk4MTUwOSIsImV4cCI6IjE3ODc5ODMzMDkiLCJodHRwOi8vc2NoZW1hcy5taWNyb3NvZnQuY29tL3dzLzIwMDgvMDYvaWRlbnRpdHkvY2xhaW1zL2V4cGlyYXRpb24iOiI4LzI5LzIwMjYgMTI6MzE2NDkgUE0iLCJodHRwOi8vc2NoZW1hcy5taWNyb3NvZnQuY29tL3dzLzIwMDgvMDYvaWRlbnRpdHkvY2xhaW1zL3JvbGUiOiJBY2Nlc3NfVG9rZW4iLCJVc2VySWQiOiIxMDEyMjEzIiwiVXNlck5hbWUiOiI5NTk3NDA5MzkzNzAiLCJVc2VyUGhvdG8iOiI5IiwiTmlja05hbWUiOiJUaGV0R3lpIiwiQW1vdW50IjoiODcuMzAiLCJJbnRlZ3JhbCI6IjAiLCJsb2dpbk1hcmsiOiJINSIsImxvZ2luVGltZSI6IjgvMjkvMjAyNiAxMjowMTo0OSBQTSIsImxvZ2luSVBBZGRyZXNzIjoiNDUuNDEuMTA0LjI0MCIsImRiTnVtYmVyIjoiMCIsIklzdmFsaWRhdG9yIjoiMCIsIktleUNvZGUiOiIzMjMzMiIsImRva2VuVHlwZSI6IjJBY2Nlc3NfVG9rZW4iLCJob25lVHlpZSI6IjAiLCJVc2VyVHlwZSI6IjAiLCJVc2VyTmFtZ2UiOiIuIiwiaXNzIjoiand0SXNzdWVyIiwiYXVkIjoibG90dGVyeVRpY2tldCJ9.ZL0Y9gexUTCsKwWeZhCLAAw8AABEYJt0GnIzIviMG4g")

COLOUR_MAP = {
    0: "Violet+Red", 1: "Green", 2: "Red", 3: "Green", 4: "Red",
    5: "Violet+Green", 6: "Red", 7: "Green", 8: "Red", 9: "Green",
}

# ==========================================
# ⚙️ CONFIG
# ==========================================
CONFIG = {
    "window_size": 60,
    "min_data_before_signal": 12,
    "adaptive_base_threshold": 0.52,
    "min_agreement": 3,
    "min_models_for_signal": 3,
    "min_margin": 0.08,
    "q_lr": 0.35,
    "q_discount": 0.95,
    "q_epsilon": 0.10,
    "q_epsilon_decay": 0.998,
    "q_min_epsilon": 0.02,
    "lr_lr": 0.008,
    "lr_epochs": 3,
    "adaptive_weight_alpha": 0.25,
    "rolling_accuracy_window": 50,
    "api_url": "https://6lotteryapi.com/api/webapi/GetNoaverageEmerdList",
    "payout_rate": 0.96,
    "profit_reset_threshold": 100000,
}

# ==========================================
# 📊 LEVEL TABLE (1-30) + Fibonacci 31+
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
    21: {"bet1": 369000,  "bet2": 738000},
    22: {"bet1": 497000,  "bet2": 994000},
    23: {"bet1": 670000,  "bet2": 1340000},
    24: {"bet1": 902000,  "bet2": 1804000},
    25: {"bet1": 1216000, "bet2": 2432000},
    26: {"bet1": 1638000, "bet2": 3276000},
    27: {"bet1": 2207000, "bet2": 4414000},
    28: {"bet1": 2973000, "bet2": 5946000},
    29: {"bet1": 4005000, "bet2": 8010000},
    30: {"bet1": 5396000, "bet2": 10792000},
}


def get_level_bet(level):
    if level in LEVEL_TABLE:
        return LEVEL_TABLE[level]
    a = LEVEL_TABLE[29]["bet1"]
    b = LEVEL_TABLE[30]["bet1"]
    for _ in range(level - 30):
        a, b = b, a + b
    return {"bet1": b, "bet2": b * 2}


app = Flask(__name__)
global_agent = None


# ==========================================
# 📈 DFA
# ==========================================
def calculate_dfa(series, min_scale=6, max_scale=None):
    data = np.asarray(series, dtype=np.float64)
    N = len(data)
    if N < 16: return 0.5
    if max_scale is None: max_scale = N // 3
    if max_scale <= min_scale: return 0.5
    y = np.cumsum(data - np.mean(data))
    scales = np.unique(np.logspace(np.log10(min_scale), np.log10(max_scale), num=6).astype(int))
    fluctuations, valid_scales = [], []
    for s in scales:
        num_segments = N // s
        if num_segments < 2: continue
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
    if len(valid_scales) < 2: return 0.5
    alpha, _ = np.polyfit(np.log(valid_scales), np.log(fluctuations), 1)
    return float(np.clip(alpha, 0.1, 1.4))


# ==========================================
# 🧠 FEATURE ENGINEER
# ==========================================
class FeatureEngineer:
    @staticmethod
    def encode(r): return 1 if r == "Big" else 0

    @staticmethod
    def streak(encoded):
        if not encoded: return 0
        count = 1
        for i in range(len(encoded) - 2, -1, -1):
            if encoded[i] == encoded[-1]: count += 1
            else: break
        return count

    @staticmethod
    def alternating_streak(encoded):
        if len(encoded) < 2: return 0
        count = 1
        for i in range(len(encoded) - 2, -1, -1):
            if encoded[i] != encoded[i + 1]: count += 1
            else: break
        return count

    @staticmethod
    def momentum(encoded, window):
        if len(encoded) < window: return 0.5
        return sum(encoded[-window:]) / window

    @staticmethod
    def entropy(encoded, window=20):
        if len(encoded) < window: return 0.5
        recent = encoded[-window:]
        p_big = sum(recent) / window
        p_small = 1 - p_big
        if p_big == 0 or p_small == 0: return 0.0
        return -(p_big * math.log2(p_big) + p_small * math.log2(p_small))

    @staticmethod
    def ma(lst, period):
        if not lst: return 0.5
        if len(lst) < period: return sum(lst) / len(lst)
        return sum(list(lst)[-period:]) / period

    @staticmethod
    def variance(lst):
        if len(lst) < 2: return 0.0
        mean = sum(lst) / len(lst)
        return sum((x - mean) ** 2 for x in lst) / len(lst)

    @staticmethod
    def std(lst): return math.sqrt(FeatureEngineer.variance(lst))

    @staticmethod
    def autocorr(lst, lag=1):
        n = len(lst)
        if n < lag + 1: return 0.0
        mean = sum(lst) / n
        num = sum((lst[i] - mean) * (lst[i - lag] - mean) for i in range(lag, n))
        den = sum((x - mean) ** 2 for x in lst)
        return num / den if den != 0 else 0.0

    @staticmethod
    def fft_freq(lst):
        if len(lst) < 8: return 0.0
        arr = np.array(lst)
        mags = np.abs(np.fft.fft(arr))
        if len(mags) > 1:
            dom = np.argmax(mags[1:]) + 1
            return dom / len(lst)
        return 0.0

    @staticmethod
    def flip_rate(encoded):
        if len(encoded) < 2: return 0.0
        flips = sum(1 for i in range(len(encoded) - 1) if encoded[i] != encoded[i + 1])
        return flips / (len(encoded) - 1)

    @staticmethod
    def to_vector(encoded):
        n = len(encoded)
        return [
            FeatureEngineer.ma(encoded, 10),
            FeatureEngineer.ma(encoded, 30),
            FeatureEngineer.ma(encoded, 10) / max(FeatureEngineer.ma(encoded, 30), 0.01),
            FeatureEngineer.variance(encoded),
            FeatureEngineer.std(encoded),
            FeatureEngineer.autocorr(encoded, 1),
            FeatureEngineer.autocorr(encoded, 2),
            FeatureEngineer.autocorr(encoded, 3),
            FeatureEngineer.fft_freq(encoded),
            FeatureEngineer.entropy(encoded),
            sum(encoded[-3:]) / 3.0 if n >= 3 else 0.5,
            sum(encoded[-5:]) / 5.0 if n >= 5 else 0.5,
            sum(encoded[-10:]) / 10.0 if n >= 10 else 0.5,
            FeatureEngineer.streak(encoded),
            FeatureEngineer.flip_rate(encoded),
            n / CONFIG['window_size'],
        ]


# ==========================================
# 🤖 LOGISTIC REGRESSION
# ==========================================
class LogisticRegression:
    def __init__(self, input_size, lr=0.008):
        self.lr = lr
        scale = math.sqrt(2.0 / input_size)
        self.W = np.random.randn(input_size, 1) * scale
        self.b = np.zeros((1, 1))
        self.loss = 0.0

    def sigmoid(self, z): return 1.0 / (1.0 + np.exp(-np.clip(z, -500, 500)))

    def forward(self, X): return self.sigmoid(np.dot(X, self.W) + self.b)

    def train(self, X, y, epochs=3):
        X = np.array(X).reshape(-1, X.shape[-1])
        y = np.array(y).reshape(-1, 1)
        for _ in range(epochs):
            preds = self.forward(X)
            loss = -np.mean(y * np.log(preds + 1e-8) + (1 - y) * np.log(1 - preds + 1e-8))
            self.loss = loss
            m = X.shape[0]
            error = preds - y
            self.W -= self.lr * (np.dot(X.T, error) / m)
            self.b -= self.lr * (np.sum(error, axis=0, keepdims=True) / m)
        return self.loss

    def predict(self, X): return self.forward(np.array(X).reshape(1, -1))[0][0]


# ==========================================
# 🎯 V15.6 ENGINE — State Machine
# ==========================================
class V15Engine:
    def __init__(self):
        global global_agent
        global_agent = self
        self.lock = threading.Lock()
        self.window = deque(maxlen=CONFIG['window_size'])
        self.digit_history = deque(maxlen=120)
        
        self.active_prediction = None
        self.last_state = None
        self.last_digit = None
        self.last_bot_step = None
        
        # Signal Bot Step
        self.bot_step = 1
        
        # 🆕 Level State Machine
        self.level = 1
        self.level_state = "WAITING_BET1"  # WAITING_BET1 or WAITING_BET2
        self.current_bet = 0
        
        # Stats
        self.total_signals = 0
        self.total_wins = 0
        self.total_losses = 0
        self.recent_results = deque(maxlen=50)
        self.total_profit = 0.0
        self.total_loss_amount = 0.0
        self.current_profit = 0.0
        self.max_loss_amount = 0.0
        self.max_profit_seen = 0.0
        self.cycles_completed = 0
        self.max_level_reached = 1
        self.profit_resets = 0
        
        # Model accuracy
        self.model_acc = {k: deque(maxlen=40) for k in [
            "markov2", "markov3", "repeat", "alternating", "momentum",
            "digit", "fibonacci", "support_res", "gap", "bayesian",
            "qlearning", "logreg", "regime_aware"
        ]}
        self.model_weights = {k: 1.0 for k in self.model_acc}
        self.pending_models = {}
        
        # Q-Learning
        self.q_table = {}
        self.q_lr = CONFIG['q_lr']
        self.q_discount = CONFIG['q_discount']
        self.epsilon = CONFIG['q_epsilon']
        
        # Logistic Regression
        self.lr_model = LogisticRegression(input_size=16, lr=CONFIG['lr_lr'])
        self.lr_train_X = deque(maxlen=200)
        self.lr_train_y = deque(maxlen=200)
        
        self.regime = "unknown"
        self.is_paused = False

    # ==========================================
    # 📤 TELEGRAM
    # ==========================================
    def send_telegram(self, message):
        if not TELEGRAM_TOKEN or not CHAT_ID:
            print(f"[TG-DISABLED] {message[:80]}...", flush=True)
            return
        def _send():
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
            for _ in range(3):
                try:
                    res = requests.post(url, json={"chat_id": CHAT_ID, "text": message, "parse_mode": "HTML"}, timeout=15)
                    if res.status_code == 200: return
                except:
                    time.sleep(2)
        threading.Thread(target=_send, daemon=True).start()

    # ==========================================
    # 📊 HELPERS
    # ==========================================
    def get_wr(self):
        total = self.total_wins + self.total_losses
        return (self.total_wins / total * 100) if total > 0 else 0.0
    
    def update_max_tracking(self):
        if self.current_profit < self.max_loss_amount:
            self.max_loss_amount = self.current_profit
        if self.current_profit > self.max_profit_seen:
            self.max_profit_seen = self.current_profit

    # ==========================================
    # 💰 LEVEL STATE MACHINE
    # ==========================================
    def get_current_bet(self):
        """လက်ရှိ Level State အရ Bet ယူ"""
        info = get_level_bet(self.level)
        if self.level_state == "WAITING_BET1":
            return info["bet1"], "BET1"
        else:
            return info["bet2"], "BET2"

    def on_result(self, won):
        """
        Result ရရင် Level State Update
        Returns: (action, old_level, old_state)
        """
        old_level = self.level
        old_state = self.level_state
        
        if self.level_state == "WAITING_BET1":
            if won:
                # ✅ Bet1 Win → Bet2 စောင့်
                self.level_state = "WAITING_BET2"
                return "BET1_WIN", old_level, old_state
            else:
                # ❌ Bet1 Lose → Level +1
                self.level += 1
                self.level_state = "WAITING_BET1"
                if self.level > self.max_level_reached:
                    self.max_level_reached = self.level
                return "BET1_LOSE", old_level, old_state
        
        else:  # WAITING_BET2
            if won:
                # 🎉 Bet2 Win → Level 1 Reset
                self.level = 1
                self.level_state = "WAITING_BET1"
                self.cycles_completed += 1
                return "RESET", old_level, old_state
            else:
                # ❌ Bet2 Lose → Level +1
                self.level += 1
                self.level_state = "WAITING_BET1"
                if self.level > self.max_level_reached:
                    self.max_level_reached = self.level
                return "BET2_LOSE", old_level, old_state

    def update_bot_step(self, bot_won):
        """Signal Bot Step: Win → 1x Reset, Lose → +1"""
        if bot_won:
            self.bot_step = 1
        else:
            self.bot_step += 1

    # ==========================================
    # 💰 PROFIT RESET
    # ==========================================
    def check_profit_reset(self):
        if self.current_profit >= CONFIG['profit_reset_threshold']:
            old_max_level = self.max_level_reached
            report = (
                f"🎉 <b>PROFIT RESET</b>\n"
                f"\n"
                f"💰 Net Profit: <b>+{self.current_profit:,.0f}</b>\n"
                f"\n"
                f"━━━━━━━━━━━━━━━━━\n"
                f"📈 Total Profit: <b>+{self.total_profit:,.0f}</b>\n"
                f"📉 Total Loss: <b>-{self.total_loss_amount:,.0f}</b>\n"
                f"🔻 Max Drawdown: <b>{self.max_loss_amount:,.0f}</b>\n"
                f"\n"
                f"🏆 Max Level: <b>{old_max_level}</b>\n"
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

    # ==========================================
    # Q-LEARNING
    # ==========================================
    def get_state_key(self):
        if len(self.window) < 5:
            return "Big,Big,Big,Big,Big"
        return ",".join(list(self.window)[-5:])

    def get_q_action(self, state):
        if state not in self.q_table:
            self.q_table[state] = {"Big": 0.5, "Small": 0.5}
        actions = self.q_table[state]
        if np.random.random() < self.epsilon:
            return "Big" if np.random.random() < 0.5 else "Small"
        return "Big" if actions["Big"] >= actions["Small"] else "Small"

    def update_q_table(self, state, action, reward):
        if state not in self.q_table:
            self.q_table[state] = {"Big": 0.5, "Small": 0.5}
        old_q = self.q_table[state][action]
        new_q = old_q + self.q_lr * (reward + self.q_discount * max(self.q_table[state].values()) - old_q)
        self.q_table[state][action] = new_q

    def update_epsilon(self):
        self.epsilon = max(CONFIG['q_min_epsilon'], self.epsilon * CONFIG['q_epsilon_decay'])

    # ==========================================
    # 13 MODELS (Same as V15.5)
    # ==========================================
    def markov_order2(self, encoded):
        if len(encoded) < 10: return None, 0
        pair = (encoded[-2], encoded[-1])
        trans = {0: 0, 1: 0}
        for i in range(len(encoded) - 2):
            if (encoded[i], encoded[i+1]) == pair:
                trans[encoded[i+2]] += 1
        total = trans[0] + trans[1]
        if total < 3: return None, 0
        pred = 1 if trans[1] > trans[0] else 0
        return ("Big" if pred == 1 else "Small"), max(trans.values()) / total

    def markov_order3(self, encoded):
        if len(encoded) < 15: return None, 0
        pattern = tuple(encoded[-3:])
        trans = {0: 0, 1: 0}
        for i in range(len(encoded) - 3):
            if tuple(encoded[i:i+3]) == pattern:
                trans[encoded[i+3]] += 1
        total = trans[0] + trans[1]
        if total < 2: return None, 0
        pred = 1 if trans[1] > trans[0] else 0
        return ("Big" if pred == 1 else "Small"), min((max(trans.values()) / total) * 1.15, 0.85)

    def repeat_pattern(self, encoded):
        streak = FeatureEngineer.streak(encoded)
        if streak < 2: return None, 0
        if streak <= 3: return ("Big" if encoded[-1] == 1 else "Small"), 0.58
        elif streak <= 5: return ("Big" if encoded[-1] == 1 else "Small"), 0.65
        else:
            pred = 1 - encoded[-1]
            return ("Big" if pred == 1 else "Small"), 0.70

    def alternating_pattern(self, encoded):
        alt_streak = FeatureEngineer.alternating_streak(encoded)
        if alt_streak < 3: return None, 0
        pred = 1 - encoded[-1]
        conf = 0.60 + min((alt_streak - 3) * 0.03, 0.12)
        return ("Big" if pred == 1 else "Small"), conf

    def momentum_shift(self, encoded):
        if len(encoded) < 12: return None, 0
        short_mom = FeatureEngineer.momentum(encoded, 5)
        long_mom = FeatureEngineer.momentum(encoded, 12)
        shift = short_mom - long_mom
        if shift > 0.35: return "Big", 0.60
        elif shift < -0.35: return "Small", 0.60
        elif short_mom > 0.75: return "Small", 0.58
        elif short_mom < 0.25: return "Big", 0.58
        return None, 0

    def digit_transition(self):
        if len(self.digit_history) < 25: return None, 0
        hist = list(self.digit_history)
        last_d = hist[-1]
        trans = Counter()
        for i in range(len(hist) - 1):
            if hist[i] == last_d: trans[hist[i+1]] += 1
        if len(trans) < 3: return None, 0
        total = sum(trans.values())
        nxt_d, cnt = trans.most_common(1)[0]
        prob = cnt / total
        if prob < 0.25: return None, 0
        pred = "Big" if nxt_d >= 5 else "Small"
        return pred, min(prob * 1.3, 0.78)

    def fibonacci_window(self, encoded):
        if len(encoded) < 21: return None, 0
        fibs = [3, 5, 8, 13]
        votes = {0: 0.0, 1: 0.0}
        for fib in fibs:
            if len(encoded) < fib + 1: continue
            if encoded[-1] == encoded[-(fib + 1)]:
                if fib > 1 and len(encoded) >= fib:
                    votes[encoded[-(fib - 1)]] += 1.0 / fib
        total = votes[0] + votes[1]
        if total < 0.4: return None, 0
        pred = 1 if votes[1] > votes[0] else 0
        conf = max(votes.values()) / total
        return ("Big" if pred == 1 else "Small"), min(0.50 + conf * 0.25, 0.72)

    def support_resistance(self, encoded):
        if len(encoded) < 25: return None, 0
        current_streak = FeatureEngineer.streak(encoded)
        current_val = encoded[-1]
        streaks, count = [], 1
        for i in range(1, len(encoded)):
            if encoded[i] == encoded[i-1]: count += 1
            else:
                if encoded[i-1] == current_val: streaks.append(count)
                count = 1
        if encoded[-1] == current_val: streaks.append(count)
        if len(streaks) < 3: return None, 0
        avg_streak = sum(streaks) / len(streaks)
        max_streak = max(streaks)
        if current_streak > avg_streak * 1.5:
            conf = min(0.55 + (current_streak - avg_streak) * 0.04, 0.72)
            pred = 1 - current_val
            return ("Big" if pred == 1 else "Small"), conf
        if current_streak >= max_streak - 1:
            pred = 1 - current_val
            return ("Big" if pred == 1 else "Small"), 0.62
        if current_streak < avg_streak * 0.7:
            return ("Big" if current_val == 1 else "Small"), 0.56
        return None, 0

    def gap_pattern(self, encoded):
        if len(encoded) < 20: return None, 0
        pattern = tuple(encoded[-3:])
        occurrences = [i for i in range(len(encoded) - 3) if tuple(encoded[i:i+3]) == pattern]
        if len(occurrences) < 2: return None, 0
        next_vals = [encoded[occ + 3] for occ in occurrences if occ + 3 < len(encoded)]
        if len(next_vals) < 2: return None, 0
        big_count = sum(next_vals)
        small_count = len(next_vals) - big_count
        if big_count >= small_count * 1.5:
            return "Big", min(0.55 + (big_count / len(next_vals)) * 0.20, 0.72)
        elif small_count >= big_count * 1.5:
            return "Small", min(0.55 + (small_count / len(next_vals)) * 0.20, 0.72)
        return None, 0

    def bayesian_predict(self, encoded):
        if len(encoded) < 15: return None, 0
        recent = encoded[-15:]
        recent_big = sum(recent)
        recent_small = len(recent) - recent_big
        alpha_big = recent_big + 1
        alpha_small = recent_small + 1
        total = alpha_big + alpha_small
        post_big = (alpha_big * 0.5) / total
        post_small = (alpha_small * 0.5) / total
        total_post = post_big + post_small
        post_big /= total_post
        post_small /= total_post
        streak = FeatureEngineer.streak(encoded)
        last_val = encoded[-1]
        if streak >= 4:
            if last_val == 1: post_small *= 1.15
            else: post_big *= 1.15
        elif streak <= 2:
            if last_val == 1: post_big *= 1.05
            else: post_small *= 1.05
        total_post = post_big + post_small
        post_big /= total_post
        post_small /= total_post
        if post_big > post_small:
            if post_big < 0.52: return None, 0
            return "Big", min(post_big, 0.78)
        else:
            if post_small < 0.52: return None, 0
            return "Small", min(post_small, 0.78)

    def qlearning_predict(self, state_key):
        return self.get_q_action(state_key), 0.60

    def logreg_predict(self, encoded):
        try:
            vec = FeatureEngineer.to_vector(encoded)
            if len(self.lr_train_X) >= 20:
                X = list(self.lr_train_X)[-50:]
                y = list(self.lr_train_y)[-50:]
                self.lr_model.train(X, y, epochs=CONFIG['lr_epochs'])
            out = self.lr_model.predict(vec)
            return ("Big" if out > 0.5 else "Small"), max(out, 1 - out)
        except Exception as e:
            print(f"LR Error: {e}", flush=True)
            return None, 0

    def regime_aware_predict(self, encoded):
        if len(encoded) < 10: return None, 0
        last_10 = encoded[-10:]
        flips = sum(1 for i in range(len(last_10) - 1) if last_10[i] != last_10[i + 1])
        flip_ratio = flips / 9.0
        recent_5 = sum(last_10[-5:]) / 5.0
        prev_5 = sum(last_10[:5]) / 5.0
        momentum = recent_5 - prev_5
        if flip_ratio < 0.3 and abs(momentum) > 0.3:
            self.regime = "trending"
            return ("Big" if encoded[-1] == 1 else "Small"), 0.65
        elif flip_ratio > 0.6:
            self.regime = "choppy"
            streak = FeatureEngineer.streak(encoded[-5:])
            if streak >= 3:
                pred = 1 - encoded[-1]
                return ("Big" if pred == 1 else "Small"), 0.62
            return ("Big" if encoded[-1] == 1 else "Small"), 0.55
        else:
            self.regime = "neutral"
            recent_big = sum(encoded[-5:]) / 5.0
            return ("Big" if recent_big > 0.5 else "Small"), 0.58

    def get_consensus(self):
        encoded = [FeatureEngineer.encode(r) for r in self.window]
        state_key = self.get_state_key()
        signals = {}

        for name, (pred, conf) in [
            ("markov2", self.markov_order2(encoded)),
            ("markov3", self.markov_order3(encoded)),
            ("repeat", self.repeat_pattern(encoded)),
            ("alternating", self.alternating_pattern(encoded)),
            ("momentum", self.momentum_shift(encoded)),
            ("digit", self.digit_transition()),
            ("fibonacci", self.fibonacci_window(encoded)),
            ("support_res", self.support_resistance(encoded)),
            ("gap", self.gap_pattern(encoded)),
            ("bayesian", self.bayesian_predict(encoded)),
            ("qlearning", self.qlearning_predict(state_key)),
            ("logreg", self.logreg_predict(encoded)),
            ("regime_aware", self.regime_aware_predict(encoded)),
        ]:
            if pred and conf > 0:
                signals[name] = (pred, conf)

        if len(signals) < CONFIG['min_models_for_signal']:
            return None, 0, f"Insufficient ({len(signals)})", 0.5

        big_models = sum(1 for p, c in signals.values() if p == "Big")
        small_models = len(signals) - big_models
        agreement = max(big_models, small_models)

        if agreement < CONFIG['min_agreement']:
            return None, 0, f"Low Agreement {agreement}/{len(signals)}", 0.5

        big_score, small_score = 0.0, 0.0
        for name, (pred, conf) in signals.items():
            weight = self.model_weights.get(name, 1.0)
            if len(self.model_acc.get(name, deque())) >= 5:
                acc = sum(self.model_acc[name]) / len(self.model_acc[name])
                weight = 0.6 + acc * 0.8
            weighted = conf * weight
            if pred == "Big": big_score += weighted
            else: small_score += weighted

        total = big_score + small_score
        if total == 0:
            return None, 0, "No Vote", 0.5

        margin = abs(big_score - small_score) / total
        if margin < CONFIG['min_margin']:
            return None, 0, f"Low Margin {margin:.0%}", 0.5

        alpha = calculate_dfa(encoded)
        if big_score > small_score:
            return "Big", big_score / total, f"⚡13-Ens[{len(signals)}] {self.regime}", alpha
        else:
            return "Small", small_score / total, f"⚡13-Ens[{len(signals)}] {self.regime}", alpha

    def get_threshold(self):
        base = CONFIG['adaptive_base_threshold']
        if len(self.recent_results) < 10:
            return base + 0.03
        recent_wr = sum(self.recent_results) / len(self.recent_results)
        if recent_wr >= 0.65: return base - 0.04
        elif recent_wr >= 0.55: return base - 0.02
        elif recent_wr >= 0.48: return base
        else: return base + 0.04

    def should_skip(self, encoded, alpha, entropy):
        reasons = []
        if entropy > 0.99: reasons.append("Max Entropy")
        if len(self.recent_results) >= 15:
            recent_wr = sum(self.recent_results) / len(self.recent_results)
            if recent_wr < 0.35:
                reasons.append(f"Cold {recent_wr:.0%}")
        return (len(reasons) > 0), ", ".join(reasons)

    def update_model_accuracy(self, actual):
        for name, pred in self.pending_models.items():
            is_correct = 1 if pred == actual else 0
            if name in self.model_acc:
                self.model_acc[name].append(is_correct)
        self.pending_models.clear()

    def record_pending_models(self):
        encoded = [FeatureEngineer.encode(r) for r in self.window]
        state_key = self.get_state_key()
        self.pending_models = {}
        for name, (pred, conf) in [
            ("markov2", self.markov_order2(encoded)),
            ("markov3", self.markov_order3(encoded)),
            ("repeat", self.repeat_pattern(encoded)),
            ("alternating", self.alternating_pattern(encoded)),
            ("momentum", self.momentum_shift(encoded)),
            ("digit", self.digit_transition()),
            ("fibonacci", self.fibonacci_window(encoded)),
            ("support_res", self.support_resistance(encoded)),
            ("gap", self.gap_pattern(encoded)),
            ("bayesian", self.bayesian_predict(encoded)),
            ("qlearning", self.qlearning_predict(state_key)),
            ("logreg", self.logreg_predict(encoded)),
            ("regime_aware", self.regime_aware_predict(encoded)),
        ]:
            if pred: self.pending_models[name] = pred

    # ==========================================
    # 🎯 MAIN PROCESS
    # ==========================================
    def process_api_result(self, api_period, api_result, digit=None):
        with self.lock:
            self._process_internal(api_period, api_result, digit)

    def _process_internal(self, api_period, api_result, digit):
        try: api_period_int = int(api_period)
        except: return
        notifications = []

        if digit is not None:
            self.last_digit = digit
            self.digit_history.append(digit)

        # ==========================================
        # Verify Previous Prediction
        # ==========================================
        if self.active_prediction is not None and self.last_state is not None:
            bot_won = (self.active_prediction == api_result)
            self.recent_results.append(1 if bot_won else 0)

            reward = 5.0 if bot_won else -5.0
            self.update_q_table(self.last_state, self.active_prediction, reward)
            self.update_epsilon()
            self.update_model_accuracy(api_result)

            if len(self.window) >= 5:
                encoded = [FeatureEngineer.encode(r) for r in self.window]
                self.lr_train_X.append(FeatureEngineer.to_vector(encoded))
                self.lr_train_y.append([FeatureEngineer.encode(api_result)])

            if bot_won: self.total_wins += 1
            else: self.total_losses += 1

            # ==========================================
            # 🎯 LEVEL STATE MACHINE
            # ==========================================
            # လက်ရှိ bet ကို ယူ
            bet_amount, bet_type = self.get_current_bet()
            
            # Profit/Loss tracking
            if bot_won:
                profit_amount = bet_amount * CONFIG['payout_rate']
                self.total_profit += profit_amount
                self.current_profit += profit_amount
            else:
                self.total_loss_amount += bet_amount
                self.current_profit -= bet_amount
            
            self.update_max_tracking()
            
            # Level State Update
            action, old_level, old_state = self.on_result(bot_won)
            
            # ✅ WIN MESSAGE
            if bot_won:
                if action == "RESET":
                    notifications.append(
                        f"🔥 <b>WIN ✅</b> (+{profit_amount:,.0f})\n"
                        f"🎉 <b>BET2 WIN → Level 1 RESET</b>\n"
                        f"🔄 Level {old_level} → Level 1\n"
                        f"\n"
                        f"━━━━━━━━━━━━━━━━━\n"
                        f"🏆 Max Level: {self.max_level_reached}\n"
                        f"📉 Max DD: {self.max_loss_amount:,.0f}\n"
                        f"💵 Profit: {self.current_profit:+,.0f}\n"
                        f"📊 WR: {self.get_wr():.1f}%"
                    )
                else:
                    notifications.append(
                        f"🔥 <b>WIN ✅</b> (+{profit_amount:,.0f})\n"
                        f"🎯 Bet1 Win → Bet2 စောင့်\n"
                        f"🎮 Level: {self.level} | State: BET2\n"
                        f"\n"
                        f"━━━━━━━━━━━━━━━━━\n"
                        f"🏆 Max Level: {self.max_level_reached}\n"
                        f"📉 Max DD: {self.max_loss_amount:,.0f}\n"
                        f"💵 Profit: {self.current_profit:+,.0f}\n"
                        f"📊 WR: {self.get_wr():.1f}%"
                    )
            
            # Level Up message
            if action in ("BET1_LOSE", "BET2_LOSE"):
                notifications.append(
                    f"📈 <b>LEVEL UP</b>\n"
                    f"🔄 Level {old_level} → Level {self.level}\n"
                    f"💰 Next Bet1: {get_level_bet(self.level)['bet1']:,}"
                )

            # Update Bot Step
            self.update_bot_step(bot_won)

            self.active_prediction = None
            self.last_state = None
            self.last_bot_step = None

            # PROFIT RESET CHECK
            reset_report = self.check_profit_reset()
            if reset_report:
                notifications.append(reset_report)

        else:
            self.update_model_accuracy(api_result)

        self.window.append(api_result)
        next_period_short = str(api_period_int + 1)[-3:]

        # ==========================================
        # Generate Signal
        # ==========================================
        if len(self.window) < CONFIG['min_data_before_signal']:
            notifications.append(
                f"💖 Period {next_period_short}\n"
                f"⏳ Data: {len(self.window)}/{CONFIG['min_data_before_signal']}"
            )
        else:
            encoded = [FeatureEngineer.encode(r) for r in self.window]
            pred, conf, mode, alpha = self.get_consensus()

            if pred is None:
                notifications.append(
                    f"💖 Period {next_period_short}\n"
                    f"⏭️ <b>SKIP</b> ({mode})"
                )
            else:
                entropy = FeatureEngineer.entropy(encoded, 20)
                skip, reason = self.should_skip(encoded, alpha, entropy)
                threshold = self.get_threshold()

                if skip:
                    notifications.append(
                        f"💖 Period {next_period_short}\n"
                        f"⏭️ <b>SKIP</b> ({reason})"
                    )
                elif conf < threshold:
                    notifications.append(
                        f"💖 Period {next_period_short}\n"
                        f"⏭️ <b>SKIP</b> (Conf {conf:.1%} < {threshold:.1%})"
                    )
                else:
                    # ✅ SIGNAL
                    self.active_prediction = pred
                    self.last_state = self.get_state_key()
                    self.total_signals += 1
                    self.record_pending_models()
                    self.last_bot_step = self.bot_step

                    # လက်ရှိ Bet
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
# 🌐 API POLLER
# ==========================================
def run_bot():
    print("🚀 V15.6 — Level State Machine Started", flush=True)
    agent = V15Engine()
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
                time.sleep(1.5); continue
            data = res.json().get("data", {}).get("list", [])
            if not data:
                time.sleep(1.5); continue
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
        return "<h3>🚀 V15.6 starting...</h3>"
    a = global_agent
    bet_amount, bet_type = a.get_current_bet()
    return f"""
    <h2>🚀 V15.6 — Level State Machine</h2>
    <p><b>🤖 Bot Step:</b> {a.bot_step}x</p>
    <p><b>🎮 Level:</b> {a.level}</p>
    <p><b>📊 State:</b> {a.level_state}</p>
    <p><b>💰 Current Bet:</b> {bet_amount:,} ({bet_type})</p>
    <p><b>🏆 Max Level:</b> {a.max_level_reached}</p>
    <p><b>📉 Max DD:</b> {a.max_loss_amount:+,.0f}</p>
    <p><b>💵 Current Profit:</b> {a.current_profit:+,.0f}</p>
    """

@app.route('/stats')
def stats():
    if global_agent:
        a = global_agent
        bet_amount, bet_type = a.get_current_bet()
        return {
            "version": "V15.6",
            "bot_step": a.bot_step,
            "level": a.level,
            "level_state": a.level_state,
            "current_bet": bet_amount,
            "bet_type": bet_type,
            "max_level": a.max_level_reached,
            "cycles": a.cycles_completed,
            "profit_resets": a.profit_resets,
            "signals": a.total_signals,
            "wins": a.total_wins,
            "losses": a.total_losses,
            "win_rate": f"{a.get_wr():.2f}%",
            "total_profit": round(a.total_profit, 2),
            "total_loss": round(a.total_loss_amount, 2),
            "net_profit": round(a.current_profit, 2),
            "max_loss": round(a.max_loss_amount, 2),
        }
    return {"status": "initializing"}

@app.route('/model_stats')
def model_stats():
    if global_agent:
        a = global_agent
        result = {}
        for name, acc_deque in a.model_acc.items():
            if len(acc_deque) >= 5:
                acc = sum(acc_deque) / len(acc_deque)
                weight = a.model_weights.get(name, 1.0)
                result[name] = f"{acc:.1%} (n={len(acc_deque)}, w={weight:.2f})"
            else:
                result[name] = f"warming ({len(acc_deque)})"
        return dict(sorted(result.items(), key=lambda x: x[1], reverse=True))
    return {"status": "initializing"}

@app.route('/health')
def health():
    return {"status": "ok", "version": "V15.6"}


# ==========================================
# 🚀 ENTRY
# ==========================================
if __name__ == "__main__":
    threading.Thread(target=run_bot, daemon=True).start()
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
