import requests
import time
import json
import os
import threading
import math
import copy
import numpy as np
from collections import deque, Counter
from flask import Flask

# ==========================================
# Telegram & Supabase
# ==========================================
TELEGRAM_TOKEN = "8913070806:AAF3rP0zKJtofE-5KVesqcdoHzn7Go0avho"
CHAT_ID = "-1004402480797"

SUPABASE_URL = "https://msgzacekhrvlqkqgjvly.supabase.co"
SUPABASE_KEY = "sb_publishable_bVJj1lqSAsIQ1kQ8Ae2vAQ_o3yCjDeA"

# ==========================================
# 🎨 COLOUR MAPPING
# ==========================================
COLOUR_MAP = {
    0: "Violet+Red", 1: "Green", 2: "Red", 3: "Green", 4: "Red",
    5: "Violet+Green", 6: "Red", 7: "Green", 8: "Red", 9: "Green",
}

# ==========================================
# 🧠 CONFIGURATION
# ==========================================
CONFIG = {
    "q_lr": 0.45, "q_discount": 0.95, "q_epsilon": 0.10,
    "q_epsilon_decay": 0.999, "q_min_epsilon": 0.02,
    "window_size": 60, "short_ma_period": 10, "long_ma_period": 30,
    "min_data_before_signal": 15,
    "min_confidence_for_trade": 0.60,
    "chop_filter_threshold": 0.6,
    "trend_confirmation": 2,
    "min_agreement": 4,
    "adaptive_weight_alpha": 0.2,
    "rolling_accuracy_window": 50,
    "api_url": "https://6lotteryapi.com/api/webapi/GetNoaverageEmerdList",
    "lr_lr": 0.01, "lr_epochs": 3,
    "dalarm_base_bet": 1000, "dalarm_increment": 1000,
    "dalarm_min_bet": 1000, "dalarm_sl_step": 4,
    "dalarm_payout": 0.9, "dalarm_currency": "🇲🇲",
    "profit_reset_threshold": 100000,
    "dynamic_threshold_enabled": True,
    "min_threshold": 0.55, "max_threshold": 0.65,
    # 🆕 Test Data Collection
    "test_every_n_rounds": 100,  # Every 100 rounds — Test Run
}

app = Flask(__name__)
global_agent = None


# ==========================================
# 🧪 TEST SCRIPT — PRNG Analysis
# ==========================================
class PRNGTester:
    """Test Wingo PRNG vulnerabilities"""

    def __init__(self, agent):
        self.agent = agent

    def test_period_sum(self, data):
        """Test: Period sum modulo 10"""
        matches = 0
        for item in data:
            period_sum = sum(int(d) for d in str(item["period"])) % 10
            if period_sum == item["digit"]:
                matches += 1
        return matches / len(data) if data else 0

    def test_lcg(self, digits):
        """Test: LCG (Linear Congruential Generator)"""
        if len(digits) < 10:
            return None, 0
        best = None
        max_hits = 0
        total = len(digits) - 1

        for a in range(1, 10):
            for c in range(0, 10):
                hits = 0
                for i in range(total):
                    predicted = (a * digits[i] + c) % 10
                    if predicted == digits[i + 1]:
                        hits += 1
                if hits > max_hits:
                    max_hits = hits
                    best = (a, c)
        return best, max_hits / total if total > 0 else 0

    def test_offset(self, data):
        """Test: Period last digit + offset"""
        results = []
        for offset in range(10):
            matches = 0
            for item in data:
                last_digit = int(str(item["period"])[-1])
                predicted = (last_digit + offset) % 10
                if predicted == item["digit"]:
                    matches += 1
            results.append({
                "offset": offset,
                "accuracy": matches / len(data) if data else 0
            })
        return sorted(results, key=lambda x: x["accuracy"], reverse=True)

    def test_multi_offset(self, data):
        """Test: Period last 2 digits + offset"""
        results = []
        for offset in range(10):
            matches = 0
            for item in data:
                p = str(item["period"])
                last_2 = int(p[-2:])
                predicted = (last_2 + offset) % 10
                if predicted == item["digit"]:
                    matches += 1
            results.append({
                "offset": offset,
                "accuracy": matches / len(data) if data else 0
            })
        return sorted(results, key=lambda x: x["accuracy"], reverse=True)

    def run_all_tests(self, data):
        """Run all tests and return report"""
        if len(data) < 50:
            return "⏳ Not enough data (need 50+)"

        digits = [item["digit"] for item in data]
        total = len(data)

        # Test 1: Period Sum
        sum_acc = self.test_period_sum(data)

        # Test 2: LCG
        best_lcg, lcg_acc = self.test_lcg(digits)

        # Test 3: Offset
        offsets = self.test_offset(data)

        # Test 4: Multi-Offset
        multi_offsets = self.test_multi_offset(data)

        # Build Report
        report = (
            f"🧪 <b>PRNG TEST REPORT</b>\n"
            f"📊 Data: {total} rounds\n\n"
            f"<b>Test 1 — Period Sum Mod 10:</b>\n"
            f"  Accuracy: {sum_acc:.2%}\n"
            f"  Random: 10%\n"
            f"  Result: {'🔴 VULNERABLE' if sum_acc > 0.30 else '🟢 Random'}\n\n"
            f"<b>Test 2 — LCG Brute Force:</b>\n"
        )
        if best_lcg:
            report += (
                f"  Best: a={best_lcg[0]}, c={best_lcg[1]}\n"
                f"  Accuracy: {lcg_acc:.2%}\n"
                f"  Result: {'🔴 VULNERABLE' if lcg_acc > 0.30 else '🟢 Random'}\n\n"
            )
        else:
            report += f"  Not enough data\n\n"

        report += (
            f"<b>Test 3 — Last Digit Offset:</b>\n"
            f"  Best Offset: {offsets[0]['offset']}\n"
            f"  Accuracy: {offsets[0]['accuracy']:.2%}\n"
            f"  Result: {'🔴 VULNERABLE' if offsets[0]['accuracy'] > 0.30 else '🟢 Random'}\n\n"
            f"<b>Test 4 — Last 2 Digits Offset:</b>\n"
            f"  Best Offset: {multi_offsets[0]['offset']}\n"
            f"  Accuracy: {multi_offsets[0]['accuracy']:.2%}\n"
            f"  Result: {'🔴 VULNERABLE' if multi_offsets[0]['accuracy'] > 0.30 else '🟢 Random'}\n\n"
            f"<b>Verdict:</b>\n"
        )

        vulnerabilities = 0
        if sum_acc > 0.30: vulnerabilities += 1
        if lcg_acc > 0.30: vulnerabilities += 1
        if offsets[0]['accuracy'] > 0.30: vulnerabilities += 1
        if multi_offsets[0]['accuracy'] > 0.30: vulnerabilities += 1

        if vulnerabilities == 0:
            report += "🟢 No Vulnerability — Strong PRNG"
        elif vulnerabilities <= 2:
            report += f"🟡 {vulnerabilities} Weakness — Investigate"
        else:
            report += f"🔴 {vulnerabilities} Vulnerabilities — EXPLOITABLE"

        return report


# ==========================================
# 📊 FEATURE ENGINEER
# ==========================================
class FeatureEngineer:
    @staticmethod
    def encode(r): return 1 if r == "Big" else 0
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
    def entropy(lst):
        if not lst: return 0.0
        counts = Counter(lst)
        probs = [c / len(lst) for c in counts.values()]
        return -sum(p * math.log2(p) for p in probs if p > 0)
    @staticmethod
    def streak(encoded):
        if not encoded: return 0
        count = 1
        for i in range(len(encoded) - 2, -1, -1):
            if encoded[i] == encoded[-1]: count += 1
            else: break
        return count
    @staticmethod
    def flip_rate(encoded):
        if len(encoded) < 2: return 0.0
        flips = sum(1 for i in range(len(encoded) - 1) if encoded[i] != encoded[i + 1])
        return flips / (len(encoded) - 1)
    @staticmethod
    def extract(window):
        encoded = [FeatureEngineer.encode(r) for r in window]
        n = len(encoded)
        return {
            'ma_short': FeatureEngineer.ma(encoded, CONFIG['short_ma_period']),
            'ma_long': FeatureEngineer.ma(encoded, CONFIG['long_ma_period']),
            'ma_ratio': FeatureEngineer.ma(encoded, CONFIG['short_ma_period']) / max(FeatureEngineer.ma(encoded, CONFIG['long_ma_period']), 0.01),
            'variance': FeatureEngineer.variance(encoded),
            'std_dev': FeatureEngineer.std(encoded),
            'autocorr_lag1': FeatureEngineer.autocorr(encoded, 1),
            'autocorr_lag2': FeatureEngineer.autocorr(encoded, 2),
            'autocorr_lag3': FeatureEngineer.autocorr(encoded, 3),
            'fft_freq': FeatureEngineer.fft_freq(encoded),
            'entropy': FeatureEngineer.entropy(encoded),
            'last_3_ratio': sum(encoded[-3:]) / 3.0 if n >= 3 else 0.5,
            'last_5_ratio': sum(encoded[-5:]) / 5.0 if n >= 5 else 0.5,
            'last_10_ratio': sum(encoded[-10:]) / 10.0 if n >= 10 else 0.5,
            'current_streak_len': FeatureEngineer.streak(encoded),
            'streak_direction': encoded[-1] if encoded else 0,
            'flip_rate': FeatureEngineer.flip_rate(encoded),
            'position_in_window': n / CONFIG['window_size'],
        }, encoded
    @staticmethod
    def to_vector(features):
        return [
            features['ma_short'], features['ma_long'], features['ma_ratio'],
            features['variance'], features['std_dev'],
            features['autocorr_lag1'], features['autocorr_lag2'], features['autocorr_lag3'],
            features['fft_freq'], features['entropy'],
            features['last_3_ratio'], features['last_5_ratio'], features['last_10_ratio'],
            features['current_streak_len'], features['flip_rate'], features['position_in_window']
        ]


class LogisticRegression:
    def __init__(self, input_size, lr=0.01):
        self.lr = lr
        scale = math.sqrt(2.0 / input_size)
        self.W = np.random.randn(input_size, 1) * scale
        self.b = np.zeros((1, 1))
        self.loss = 0.0
    def sigmoid(self, z): return 1.0 / (1.0 + np.exp(-np.clip(z, -500, 500)))
    def forward(self, X): return self.sigmoid(np.dot(X, self.W) + self.b)
    def train(self, X, y, epochs=3):
        X = np.array(X).reshape(-1, X.shape[-1]) if len(X.shape) > 1 else X.reshape(1, -1)
        y = np.array(y).reshape(-1, 1) if len(y.shape) > 1 else y.reshape(-1, 1)
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
# 🎯 V9.0 ENGINE
# ==========================================
class V9Engine:
    def __init__(self):
        global global_agent
        global_agent = self
        self.lock = threading.Lock()
        self.window = deque(maxlen=CONFIG['window_size'])
        self.last_api_period = "None"
        self.next_signal_period = "None"
        self.active_prediction = None
        self.last_state = None
        self.last_predictions_by_model = {}
        self.last_feature_vector = None
        self.last_confidence = None
        self.last_digit = None
        self.total_signals = 0
        self.total_wins = 0
        self.total_losses = 0
        self.prediction_history = deque(maxlen=CONFIG['rolling_accuracy_window'])
        self.step_signals = {1: 0, 2: 0, 3: 0, 4: 0}
        self.step_wins = {1: 0, 2: 0, 3: 0, 4: 0}

        # 🆕 Data History (for Test)
        self.full_history = []  # ← Persistent — for testing
        self.digit_history = deque(maxlen=200)
        self.colour_history = deque(maxlen=200)
        self.odd_even_history = deque(maxlen=200)

        MODEL_NAMES = [
            "Markov", "Pattern", "Streak", "QLearning", "Statistical",
            "MeanReversion", "Momentum", "RegimeAware", "LogisticReg",
            "DigitModel", "ColourModel", "OddEvenModel"
        ]
        self.model_correct = {k: 0 for k in MODEL_NAMES}
        self.model_total = {k: 0 for k in MODEL_NAMES}
        self.model_weights = {k: 1.0 for k in MODEL_NAMES}
        self.model_accuracy = {k: deque(maxlen=CONFIG['rolling_accuracy_window']) for k in MODEL_NAMES}

        self.q_lr = CONFIG['q_lr']
        self.q_discount = CONFIG['q_discount']
        self.epsilon = CONFIG['q_epsilon']
        self.q_table = {}
        self.lr_model = LogisticRegression(input_size=16, lr=CONFIG['lr_lr'])
        self.lr_train_X = deque(maxlen=200)
        self.lr_train_y = deque(maxlen=200)
        self.lr_loss = 0.0
        self.regime = "unknown"
        self.is_paused = False

        # DALARM
        self.dalarm_bet_size = CONFIG['dalarm_base_bet']
        self.dalarm_step = 1
        self.dalarm_profit = 0.0
        self.dalarm_max_negative = 0.0
        self.is_sl_mode = False
        self.dalarm_sl_entry_bet = CONFIG['dalarm_base_bet']
        self.dalarm_max_bet_size = CONFIG['dalarm_base_bet']
        self.dalarm_total_rounds = 0
        self.profit_reset_threshold = CONFIG['profit_reset_threshold']

        # 🆕 Tester
        self.tester = PRNGTester(self)

    def get_current_multiplier(self): return self.dalarm_step

    def send_telegram(self, message):
        def _send():
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
            for attempt in range(3):
                try:
                    res = requests.post(url, json={"chat_id": CHAT_ID, "text": message, "parse_mode": "HTML"}, timeout=15)
                    if res.status_code == 200: return
                except Exception as e:
                    time.sleep(2)
        threading.Thread(target=_send, daemon=True).start()

    def get_state_key(self, window=None):
        if window is None: window = self.window
        if len(window) < 5: return "Big,Big,Big,Big,Big"
        return ",".join(list(window)[-5:])

    def get_q_action(self, state):
        if state not in self.q_table: self.q_table[state] = {"Big": 0.5, "Small": 0.5}
        actions = self.q_table[state]
        if np.random.random() < self.epsilon:
            return "Big" if np.random.random() < 0.5 else "Small"
        return "Big" if actions["Big"] >= actions["Small"] else "Small"

    def update_q_table(self, state, action, reward):
        if state not in self.q_table: self.q_table[state] = {"Big": 0.5, "Small": 0.5}
        old_q = self.q_table[state][action]
        new_q = old_q + self.q_lr * (reward + self.q_discount * max(self.q_table[state].values()) - old_q)
        self.q_table[state][action] = new_q

    def update_epsilon(self):
        self.epsilon = max(CONFIG['q_min_epsilon'], self.epsilon * CONFIG['q_epsilon_decay'])

    # Base Models
    def markov_predict(self, lst):
        if len(lst) < 4: return "Big"
        transitions = {}
        arr = list(lst)
        for i in range(len(arr) - 1):
            key = arr[i]
            if key not in transitions: transitions[key] = {"Big": 0, "Small": 0}
            transitions[key][arr[i + 1]] += 1
        last = arr[-1]
        if last in transitions:
            b, s = transitions[last]["Big"], transitions[last]["Small"]
            if b == s: return last
            return "Big" if b > s else "Small"
        return last

    def pattern_predict(self, lst):
        arr = list(lst)
        if len(arr) < 8: return arr[-1] if arr else "Big"
        for length in range(min(8, len(arr) // 2), 2, -1):
            pattern = tuple(arr[-length:])
            matches = []
            for i in range(len(arr) - length):
                if tuple(arr[i:i + length]) == pattern and (i + length) < len(arr):
                    matches.append(arr[i + length])
            if matches: return max(set(matches), key=matches.count)
        return arr[-1]

    def streak_predict(self, lst):
        arr = list(lst)
        if len(arr) < 5: return "Big"
        encoded = [FeatureEngineer.encode(r) for r in arr]
        streak_count = 1
        for i in range(len(encoded) - 2, -1, -1):
            if encoded[i] == encoded[-1]: streak_count += 1
            else: break
        mom3 = sum(encoded[-3:]) / 3.0
        mom5 = sum(encoded[-5:]) / 5.0
        if streak_count >= 4: return "Small" if arr[-1] == "Big" else "Big"
        elif streak_count >= 3 and abs(mom3 - mom5) > 0.4: return "Small" if arr[-1] == "Big" else "Big"
        elif mom3 > 0.6: return "Big"
        elif mom3 < 0.4: return "Small"
        return arr[-1]

    def q_momentum_predict(self, lst, state_key):
        q_act = self.get_q_action(state_key)
        recent = list(lst)[-3:] if len(lst) >= 3 else list(lst)
        mom = recent[-1] if recent else "Big"
        if q_act == mom: return q_act
        if state_key in self.q_table:
            q_conf = abs(self.q_table[state_key]["Big"] - self.q_table[state_key]["Small"])
            if q_conf > 0.3: return q_act
        return mom

    def statistical_predict(self, lst):
        arr = list(lst)
        if len(arr) < 10: return "Big"
        encoded = [FeatureEngineer.encode(r) for r in arr]
        ma_s = FeatureEngineer.ma(encoded, CONFIG['short_ma_period'])
        ma_l = FeatureEngineer.ma(encoded, CONFIG['long_ma_period'])
        dev = ma_s - ma_l
        if abs(dev) > 0.2: return "Small" if dev > 0 else "Big"
        return "Big" if ma_s > ma_l else "Small"

    def mean_reversion_predict(self, lst):
        arr = list(lst)
        if len(arr) < 10: return "Big"
        encoded = [FeatureEngineer.encode(r) for r in arr]
        short_ma = sum(encoded[-5:]) / 5.0
        long_ma = sum(encoded[-20:]) / 20.0 if len(encoded) >= 20 else sum(encoded) / len(encoded)
        deviation = short_ma - long_ma
        if deviation > 0.3: return "Small"
        elif deviation < -0.3: return "Big"
        return arr[-1] if arr else "Big"

    def momentum_predict(self, lst):
        arr = list(lst)
        if len(arr) < 5: return "Big"
        encoded = [FeatureEngineer.encode(r) for r in arr]
        recent_3 = sum(encoded[-3:]) / 3.0
        prev_3 = sum(encoded[-6:-3]) / 3.0 if len(encoded) >= 6 else sum(encoded[:3]) / min(3, len(encoded))
        if recent_3 > prev_3 + 0.2: return "Big"
        elif recent_3 < prev_3 - 0.2: return "Small"
        return arr[-1] if arr else "Big"

    def detect_market_regime(self, lst):
        if len(lst) < 10: return "unknown", 0.0
        encoded = [FeatureEngineer.encode(r) for r in lst]
        last_10 = encoded[-10:]
        flips = sum(1 for i in range(len(last_10) - 1) if last_10[i] != last_10[i + 1])
        flip_ratio = flips / 9.0
        recent_5 = sum(last_10[-5:]) / 5.0
        prev_5 = sum(last_10[:5]) / 5.0
        momentum = recent_5 - prev_5
        if flip_ratio < 0.3 and abs(momentum) > 0.3: return "trending", abs(momentum)
        elif flip_ratio > 0.6: return "choppy", flip_ratio
        else: return "neutral", 0.5

    def regime_aware_predict(self, lst):
        regime, strength = self.detect_market_regime(lst)
        if regime == "trending": return lst[-1] if lst else "Big"
        elif regime == "choppy":
            encoded = [FeatureEngineer.encode(r) for r in lst[-5:]]
            streak = FeatureEngineer.streak(encoded)
            if streak >= 3: return "Small" if lst[-1] == "Big" else "Big"
            return lst[-1] if lst else "Big"
        else:
            encoded = [FeatureEngineer.encode(r) for r in lst[-10:]]
            return "Big" if sum(encoded[-5:]) / 5.0 > 0.5 else "Small"

    def lr_predict(self, features):
        try:
            vec = FeatureEngineer.to_vector(features)
            if len(self.lr_train_X) >= 20:
                X = list(self.lr_train_X)[-50:]
                y = list(self.lr_train_y)[-50:]
                self.lr_loss = self.lr_model.train(X, y, epochs=CONFIG['lr_epochs'])
            out = self.lr_model.predict(vec)
            return "Big" if out > 0.5 else "Small", out
        except Exception as e:
            return "Big", 0.5

    def digit_model_predict(self):
        if len(self.digit_history) < 20:
            return "Big", 0.5
        digit_counts = Counter(list(self.digit_history)[-50:])
        last_digit = self.digit_history[-1]
        transitions = {}
        hist = list(self.digit_history)
        for i in range(len(hist) - 1):
            if hist[i] == last_digit:
                transitions[hist[i + 1]] = transitions.get(hist[i + 1], 0) + 1
        if transitions:
            predicted_digit = max(transitions, key=transitions.get)
            total = sum(transitions.values())
            conf = transitions[predicted_digit] / total
            return ("Big" if predicted_digit >= 5 else "Small"), min(conf * 2, 0.95)
        most_common = digit_counts.most_common(1)[0][0]
        return ("Big" if most_common >= 5 else "Small"), 0.5

    def colour_model_predict(self):
        if len(self.colour_history) < 20:
            return "Big", 0.5
        last_colour = self.colour_history[-1]
        transitions = {}
        hist = list(self.colour_history)
        for i in range(len(hist) - 1):
            if hist[i] == last_colour:
                transitions[hist[i + 1]] = transitions.get(hist[i + 1], 0) + 1
        if transitions:
            predicted_colour = max(transitions, key=transitions.get)
            matching_digits = []
            for i, colour in enumerate(self.colour_history):
                if colour == predicted_colour and i < len(self.digit_history):
                    matching_digits.append(self.digit_history[i])
            if matching_digits:
                big_count = sum(1 for d in matching_digits if d >= 5)
                small_count = len(matching_digits) - big_count
                if big_count > small_count:
                    return "Big", 0.5 + (big_count / len(matching_digits) - 0.5) * 0.5
                elif small_count > big_count:
                    return "Small", 0.5 + (small_count / len(matching_digits) - 0.5) * 0.5
        return "Big", 0.5

    def odd_even_model_predict(self):
        if len(self.odd_even_history) < 20:
            return "Big", 0.5
        matching_digits = []
        for i, oe in enumerate(self.odd_even_history):
            if oe == self.odd_even_history[-1] and i < len(self.digit_history):
                matching_digits.append(self.digit_history[i])
        if matching_digits:
            big_count = sum(1 for d in matching_digits if d >= 5)
            small_count = len(matching_digits) - big_count
            if big_count > small_count:
                return "Big", 0.5 + (big_count / len(matching_digits) - 0.5) * 0.4
            elif small_count > big_count:
                return "Small", 0.5 + (small_count / len(matching_digits) - 0.5) * 0.4
        return "Big", 0.5

    def get_digit_frequency(self):
        if not self.digit_history: return {}
        return dict(Counter(list(self.digit_history)))

    def get_colour_frequency(self):
        if not self.colour_history: return {}
        return dict(Counter(list(self.colour_history)))

    def check_volatility(self, lst):
        if len(lst) < 6: return False, 0.0
        recent = list(lst)[-6:]
        flips = sum(1 for i in range(len(recent) - 1) if recent[i] != recent[i + 1])
        ratio = flips / 5.0
        return ratio >= CONFIG['chop_filter_threshold'], ratio

    def update_model_weights(self, actual_result):
        if actual_result is None: return
        for name, pred in self.last_predictions_by_model.items():
            correct = 1 if pred == actual_result else 0
            self.model_accuracy[name].append(correct)
            self.model_total[name] += 1
            if correct: self.model_correct[name] += 1
            if len(self.model_accuracy[name]) >= 5:
                acc = sum(list(self.model_accuracy[name])[-5:]) / 5.0
                old_w = self.model_weights[name]
                target = acc * 3.0
                new_w = CONFIG['adaptive_weight_alpha'] * target + (1 - CONFIG['adaptive_weight_alpha']) * old_w
                self.model_weights[name] = max(0.3, min(5.0, new_w))

    def get_model_accuracy(self):
        acc = {}
        for name in self.model_correct:
            total = self.model_total[name]
            acc[name] = self.model_correct[name] / total if total > 0 else 0.5
        return acc

    def get_consensus(self, window_list, state_key=None):
        if state_key is None: state_key = self.get_state_key()
        m1 = self.markov_predict(window_list)
        m2 = self.pattern_predict(window_list)
        m3 = self.streak_predict(window_list)
        m4 = self.q_momentum_predict(window_list, state_key)
        m5 = self.statistical_predict(window_list)
        m6 = self.mean_reversion_predict(window_list)
        m7 = self.momentum_predict(window_list)
        m8 = self.regime_aware_predict(window_list)
        features, _ = FeatureEngineer.extract(window_list)
        lr_pred, lr_conf = self.lr_predict(features)
        digit_pred, digit_conf = self.digit_model_predict()
        colour_pred, colour_conf = self.colour_model_predict()
        oe_pred, oe_conf = self.odd_even_model_predict()

        predictions = {
            "Markov": m1, "Pattern": m2, "Streak": m3,
            "QLearning": m4, "Statistical": m5,
            "MeanReversion": m6, "Momentum": m7,
            "RegimeAware": m8,
            "DigitModel": digit_pred,
            "ColourModel": colour_pred,
            "OddEvenModel": oe_pred,
        }
        self.last_predictions_by_model = {**predictions, "LogisticReg": lr_pred}

        scores = {"Big": 0.0, "Small": 0.0}
        for name, pred in predictions.items():
            scores[pred] += self.model_weights.get(name, 1.0)

        lr_weight = self.model_weights.get("LogisticReg", 1.0)
        if lr_pred == "Big": scores["Big"] += lr_weight * lr_conf
        else: scores["Small"] += lr_weight * (1 - lr_conf)

        total_w = sum(self.model_weights.get(name, 1.0) for name in predictions) + lr_weight
        confidence = max(scores["Big"], scores["Small"]) / total_w
        predicted = "Big" if scores["Big"] >= scores["Small"] else "Small"
        agreement_count = sum(1 for pred in predictions.values() if pred == predicted)

        if agreement_count < CONFIG['min_agreement']:
            return predicted, f"⏳ Wait ({agreement_count}/11)", confidence

        regime, regime_strength = self.detect_market_regime(window_list)
        self.regime = regime
        if regime == "trending":
            if predicted != window_list[-1]: confidence *= 0.7
        elif regime == "choppy":
            if predicted == window_list[-1]: confidence *= 0.7

        self.last_confidence = confidence
        return predicted, f"🎯 {predicted}", confidence

    def get_rolling_accuracy(self):
        if not self.prediction_history: return 0.0
        return sum(self.prediction_history) / len(self.prediction_history)

    def get_dynamic_threshold(self):
        if not CONFIG['dynamic_threshold_enabled']:
            return CONFIG['min_confidence_for_trade']
        if len(self.prediction_history) < 20:
            return CONFIG['min_confidence_for_trade']
        recent_wr = self.get_rolling_accuracy()
        if recent_wr >= 0.55: return CONFIG['min_threshold']
        elif recent_wr >= 0.50: return 0.60
        else: return CONFIG['max_threshold']

    def get_dalarm_bet_display(self):
        if self.is_sl_mode: return "⛔ SL (No Bet)"
        return f"{CONFIG['dalarm_currency']} {self.dalarm_bet_size}"

    def get_dalarm_profit_display(self):
        if self.dalarm_profit >= 0: profit_str = f"+{self.dalarm_profit:.0f}"
        else: profit_str = f"{self.dalarm_profit:.0f}"
        max_float_str = f"{self.dalarm_max_negative:.0f}"
        return f"💰 Current Profit: {profit_str}\n📉 Max Float: {max_float_str}"

    def update_dalarm_bet(self, won, api_period=None):
        if self.dalarm_bet_size > self.dalarm_max_bet_size:
            self.dalarm_max_bet_size = self.dalarm_bet_size
        self.dalarm_total_rounds += 1
        if self.is_sl_mode:
            if won:
                self.is_sl_mode = False
                self.dalarm_step = 1
                self.dalarm_bet_size = self.dalarm_sl_entry_bet + CONFIG['dalarm_increment']
            else:
                self.dalarm_step += 1
            if self.dalarm_profit < self.dalarm_max_negative:
                self.dalarm_max_negative = self.dalarm_profit
            return
        if won:
            profit = self.dalarm_bet_size * CONFIG['dalarm_payout']
            self.dalarm_profit += profit
            self.dalarm_step = 1
            self.dalarm_bet_size = max(CONFIG['dalarm_min_bet'], self.dalarm_bet_size - CONFIG['dalarm_increment'])
        else:
            self.dalarm_profit -= self.dalarm_bet_size
            if self.dalarm_step + 1 >= CONFIG['dalarm_sl_step']:
                self.is_sl_mode = True
                self.dalarm_sl_entry_bet = self.dalarm_bet_size
                self.dalarm_step += 1
            else:
                self.dalarm_step += 1
                self.dalarm_bet_size += CONFIG['dalarm_increment']
        if self.dalarm_profit < self.dalarm_max_negative:
            self.dalarm_max_negative = self.dalarm_profit

    def check_profit_reset(self):
        if self.dalarm_profit >= self.profit_reset_threshold:
            report = (
                f"📊 <b>REPORT — Profit +{self.profit_reset_threshold}</b>\n"
                f"💰 Profit: +{self.dalarm_profit:.0f}\n"
                f"📉 Max Float: {self.dalarm_max_negative:.0f}\n"
                f"📈 Max Bet: {self.dalarm_max_bet_size}\n"
                f"🎯 Rounds: {self.dalarm_total_rounds}\n\n"
                f"🔄 Auto Reset!"
            )
            self.dalarm_profit = 0.0
            self.dalarm_max_negative = 0.0
            self.dalarm_max_bet_size = CONFIG['dalarm_base_bet']
            self.dalarm_bet_size = CONFIG['dalarm_base_bet']
            self.dalarm_total_rounds = 0
            return report
        return None

    def process_api_result(self, api_period, api_result, digit=None):
        with self.lock:
            self._process_api_result_internal(api_period, api_result, digit)

    def _process_api_result_internal(self, api_period, api_result, digit=None):
        self.last_api_period = str(api_period)
        try: api_period_int = int(api_period)
        except (ValueError, TypeError): return
        notifications = []

        # 🆕 Track Digit
        if digit is not None:
            self.last_digit = digit
            self.digit_history.append(digit)
            self.colour_history.append(COLOUR_MAP.get(digit, "Unknown"))
            self.odd_even_history.append("Odd" if digit % 2 == 1 else "Even")

            # 🆕 Persistent history for Test
            self.full_history.append({
                "period": api_period,
                "digit": digit,
                "bigsmall": api_result,
                "colour": COLOUR_MAP.get(digit, "Unknown"),
                "timestamp": int(time.time())
            })

        # 🆕 Auto Test — every 100 rounds
        if len(self.full_history) > 0 and len(self.full_history) % CONFIG['test_every_n_rounds'] == 0:
            test_report = self.tester.run_all_tests(self.full_history)
            notifications.append(test_report)

        if self.active_prediction is not None and self.last_state is not None:
            predicted = self.active_prediction
            is_correct = (predicted.lower() == api_result.lower())
            self.prediction_history.append(1 if is_correct else 0)
            current_step = min(self.dalarm_step, 4)
            self.step_signals[current_step] += 1
            if is_correct: self.step_wins[current_step] += 1
            reward = 5.0 if is_correct else -5.0
            self.update_q_table(self.last_state, predicted, reward)
            self.update_model_weights(api_result)
            if self.last_feature_vector is not None:
                self.lr_train_X.append(self.last_feature_vector)
                self.lr_train_y.append([FeatureEngineer.encode(api_result)])
            self.update_dalarm_bet(is_correct, api_period)
            if is_correct: self.total_wins += 1
            else: self.total_losses += 1
            if is_correct:
                short = str(api_period)[-3:] if len(str(api_period)) >= 3 else str(api_period)
                notifications.append(f"🔥 WIN — Period {short} 🔥")
            self.active_prediction = None
            self.last_state = None
            self.update_epsilon()
            reset_report = self.check_profit_reset()
            if reset_report: notifications.append(reset_report)

        self.window.append(api_result)
        if len(self.window) > 0:
            features, _ = FeatureEngineer.extract(list(self.window))
            self.last_feature_vector = FeatureEngineer.to_vector(features)

        next_period_full = str(api_period_int + 1)
        self.next_signal_period = next_period_full
        next_period_short = next_period_full[-3:] if len(next_period_full) >= 3 else next_period_full

        if len(self.window) < CONFIG['min_data_before_signal']:
            notifications.append(f"💖Period {next_period_short}\n⏳ Collecting... {len(self.window)}/{CONFIG['min_data_before_signal']}")
        else:
            prediction, regime, confidence = self.get_consensus(list(self.window))
            threshold = self.get_dynamic_threshold()
            if confidence < threshold:
                notifications.append(f"💖Period {next_period_short}\n⏭️ SKIP (Conf: {confidence:.1%} < {threshold:.1%})")
                self.active_prediction = None
            else:
                self.last_state = self.get_state_key()
                self.active_prediction = prediction
                self.total_signals += 1
                bet_display = self.get_dalarm_bet_display()
                profit_display = self.get_dalarm_profit_display()
                colour_display = ""
                if self.last_digit is not None:
                    colour_display = f"\n🎨 Last: {self.last_digit} ({COLOUR_MAP.get(self.last_digit, '?')})"

                notifications.append(
                    f"💖Period {next_period_short}\n"
                    f"🎯 SIGNAL → {prediction.capitalize()}\n"
                    f"📊 Confidence: {confidence:.1%}\n"
                    f"💰 Step {self.dalarm_step}x\n"
                    f"📈 Win Rate: {self.get_rolling_accuracy():.0%}\n"
                    f"{bet_display}\n"
                    f"{profit_display}"
                    f"{colour_display}"
                )

        for msg in notifications:
            self.send_telegram(msg)
            time.sleep(0.5)


def poll_telegram(agent):
    try:
        requests.get(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/deleteWebhook?drop_pending_updates=true", timeout=10)
    except: pass
    offset = 0
    while True:
        try:
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates?offset={offset}&timeout=20"
            res = requests.get(url, timeout=25)
            if res.status_code == 200:
                for upd in res.json().get("result", []):
                    offset = upd["update_id"] + 1
                    msg = upd.get("message", {}) or upd.get("edited_message", {})
                    chat = str(msg.get("chat", {}).get("id", ""))
                    text = msg.get("text", "").strip().lower()
                    if chat != CHAT_ID: continue

                    if text == "/status":
                        agent.send_telegram(
                            f"📊 STATUS (V9.0 + PRNG Test)\n\n"
                            f"💰 Step: {agent.dalarm_step}x | Bet: {agent.dalarm_bet_size}\n"
                            f"💵 Profit: {agent.dalarm_profit:+.0f}\n"
                            f"📊 Signals: {agent.total_signals}\n"
                            f"📈 WR: {agent.get_rolling_accuracy():.1%}\n"
                            f"🔬 Data Collected: {len(agent.full_history)}"
                        )
                    elif text == "/metrics":
                        acc = agent.get_model_accuracy()
                        acc_str = "\n".join([f"  {k}: {v:.2%}" for k, v in acc.items()])
                        agent.send_telegram(f"📊 <b>METRICS</b>\n\n{acc_str}")
                    elif text == "/test":
                        # 🆕 Manual Test
                        if len(agent.full_history) >= 50:
                            report = agent.tester.run_all_tests(agent.full_history)
                            agent.send_telegram(report)
                        else:
                            agent.send_telegram(f"⏳ Need 50+ data. Have {len(agent.full_history)}.")
                    elif text == "/data":
                        # 🆕 Show Data Count
                        agent.send_telegram(
                            f"📊 <b>DATA STATUS</b>\n"
                            f"Total: {len(agent.full_history)}\n"
                            f"Next Test: {CONFIG['test_every_n_rounds'] - (len(agent.full_history) % CONFIG['test_every_n_rounds'])} rounds"
                        )
                    elif text == "/reset":
                        with agent.lock:
                            agent.dalarm_bet_size = CONFIG['dalarm_base_bet']
                            agent.dalarm_step = 1
                            agent.dalarm_profit = 0.0
                            agent.dalarm_max_negative = 0.0
                            agent.dalarm_max_bet_size = CONFIG['dalarm_base_bet']
                            agent.dalarm_total_rounds = 0
                            agent.is_sl_mode = False
                            agent.dalarm_sl_entry_bet = CONFIG['dalarm_base_bet']
                        agent.send_telegram("🔄 Reset")
        except Exception as e:
            print(f"TG Poll Error: {e}", flush=True)
        time.sleep(1)


def run_bot():
    print("🤖 Bot Started (V9.0 + PRNG Test)", flush=True)
    agent = V9Engine()
    threading.Thread(target=poll_telegram, args=(agent,), daemon=True).start()
    last_processed_period = None
    url = CONFIG['api_url']
    auth = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpYXQiOiIxNzg3OTgxNTA5IiwibmJmIjoiMTc4Nzk4MTUwOSIsImV4cCI6IjE3ODc5ODMzMDkiLCJodHRwOi8vc2NoZW1hcy5taWNyb3NvZnQuY29tL3dzLzIwMDgvMDYvaWRlbnRpdHkvY2xhaW1zL2V4cGlyYXRpb24iOiI4LzI5LzIwMjYgMTI6MzE2NDkgUE0iLCJodHRwOi8vc2NoZW1hcy5taWNyb3NvZnQuY29tL3dzLzIwMDgvMDYvaWRlbnRpdHkvY2xhaW1zL3JvbGUiOiJBY2Nlc3NfVG9rZW4iLCJVc2VySWQiOiIxMDEyMjEzIiwiVXNlck5hbWUiOiI5NTk3NDA5MzkzNzAiLCJVc2VyUGhvdG8iOiI5IiwiTmlja05hbWUiOiJUaGV0R3lpIiwiQW1vdW50IjoiODcuMzAiLCJJbnRlZ3JhbCI6IjAiLCJsb2dpbk1hcmsiOiJINSIsImxvZ2luVGltZSI6IjgvMjkvMjAyNiAxMjowMTo0OSBQTSIsImxvZ2luSVBBZGRyZXNzIjoiNDUuNDEuMTA0LjI0MCIsImRiTnVtYmVyIjoiMCIsIklzdmFsaWRhdG9yIjoiMCIsIktleUNvZGUiOiIzMjMzMiIsImRva2VuVHlwZSI6IjJBY2Nlc3NfVG9rZW4iLCJob25lVHlpZSI6IjAiLCJVc2VyVHlwZSI6IjAiLCJVc2VyTmFtZ2UiOiIuIiwiaXNzIjoiand0SXNzdWVyIiwiYXVkIjoibG90dGVyeVRpY2tldCJ9.ZL0Y9gexUTCsKwWeZhCLAAw8AABEYJt0GnIzIviMG4g"
    headers = {"accept": "application/json, text/plain, */*", "authorization": f"Bearer {auth}", "content-type": "application/json;charset=UTF-8", "origin": "https://6win598.com", "referer": "https://6win598.com/", "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    while True:
        try:
            payload = {"pageSize": 10, "pageNo": 1, "typeId": 30, "language": 7, "random": "036263f367384d418be07465793c8da8", "signature": "55F4FD150F15F090B943374F3C9BE78B", "timestamp": int(time.time())}
            res = requests.post(url, headers=headers, json=payload, timeout=5)
            if res.status_code != 200:
                time.sleep(2)
                continue
            data = res.json()
            list_data = data.get("data", {}).get("list", [])
            if len(list_data) == 0:
                time.sleep(2)
                continue
            latest = list_data[0]
            raw_period = latest.get("issueNumber")
            number = latest.get("number")
            if raw_period is None or number is None:
                time.sleep(2)
                continue
            raw_period = str(raw_period)
            number = int(number)
            api_result = "Big" if number >= 5 else "Small"
            digit = number
            if raw_period != last_processed_period:
                last_processed_period = raw_period
                print(f"📥 API: Period {raw_period} → {api_result} (Digit {digit})", flush=True)
                agent.process_api_result(raw_period, api_result, digit)
        except Exception as e:
            print(f"Main Loop Error: {e}", flush=True)
        time.sleep(2)

threading.Thread(target=run_bot, daemon=True).start()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
