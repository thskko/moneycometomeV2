"""
🚀 V16.2 — Multi-Agent Bot (10 Agents + Thompson Sampling)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Agents (10):
  1. TrendAgent
  2. MeanReversionAgent
  3. PatternAgent
  4. BreakoutAgent
  5. FibonacciAgent
  6. MarkovAgent         🆕
  7. KNNAgent            🆕
  8. RunsTestAgent       🆕
  9. DigitBiasAgent      🆕
  10. EMARibbonAgent     🆕

Features:
  - Thompson Sampling (Dynamic Agent Selection)
  - Min Agents = 2 (Quality Control)
  - Regime Detection (Streak Priority)
  - Conf No Cap
  - Level State Machine
  - Profit Reset
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
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
CHAT_ID = os.environ.get("CHAT_ID", "")
LOTTERY_AUTH = os.environ.get("LOTTERY_AUTH", "")

COLOUR_MAP = {
    0: "Violet+Red", 1: "Green", 2: "Red", 3: "Green", 4: "Red",
    5: "Violet+Green", 6: "Red", 7: "Green", 8: "Red", 9: "Green",
}

# ==========================================
# ⚙️ CONFIG
# ==========================================
CONFIG = {
    "window_size": 60,
    "min_data_before_signal": 20,
    "adaptive_base_threshold": 0.58,
    "min_margin": 0.12,
    "min_agents_for_signal": 2,
    "api_url": "https://6lotteryapi.com/api/webapi/GetNoaverageEmerdList",
    "payout_rate": 0.96,
    "profit_reset_threshold": 100000,
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
    try:
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
    except Exception as e:
        print(f"DFA Error: {e}", flush=True)
        return 0.5


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
    def std(lst):
        if len(lst) < 2: return 0.0
        mean = sum(lst) / len(lst)
        return math.sqrt(sum((x - mean) ** 2 for x in lst) / len(lst))

    @staticmethod
    def flip_rate(encoded):
        if len(encoded) < 2: return 0.0
        flips = sum(1 for i in range(len(encoded) - 1) if encoded[i] != encoded[i + 1])
        return flips / (len(encoded) - 1)


# ==========================================
# 🎯 AGENT 1: TREND AGENT
# ==========================================
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

            if trend_strength > 0.12 and alpha > 0.50:
                pred = 1 if encoded[-1] == 1 else 0
                conf = 0.58 + min(trend_strength * 0.5, 0.15)
                return ("Big" if pred == 1 else "Small"), min(conf, 0.78)

            return None, 0
        except Exception as e:
            print(f"TrendAgent Error: {e}", flush=True)
            return None, 0


# ==========================================
# 🎯 AGENT 2: MEAN REVERSION AGENT
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
        except Exception as e:
            print(f"MeanRevAgent Error: {e}", flush=True)
            return None, 0


# ==========================================
# 🎯 AGENT 3: PATTERN AGENT
# ==========================================
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
        except Exception as e:
            print(f"PatternAgent Error: {e}", flush=True)
            return None, 0


# ==========================================
# 🎯 AGENT 4: BREAKOUT AGENT
# ==========================================
class BreakoutAgent:
    NAME = "breakout"

    def predict(self, encoded, window):
        try:
            if len(encoded) < 8:
                return None, 0

            recent_5 = encoded[-5:]
            recent_std = FeatureEngineer.std(recent_5)

            short_mom = sum(encoded[-3:]) / 3
            prev_mom = sum(encoded[-6:-3]) / 3 if len(encoded) >= 6 else 0.5
            accel = short_mom - prev_mom

            if abs(accel) > 0.30:
                pred = 1 if accel > 0 else 0
                conf = 0.56 + min(abs(accel) * 0.3, 0.15)
                return ("Big" if pred == 1 else "Small"), conf

            if recent_std > 0.45:
                pred = 1 - encoded[-1]
                return ("Big" if pred == 1 else "Small"), 0.55

            return None, 0
        except Exception as e:
            print(f"BreakoutAgent Error: {e}", flush=True)
            return None, 0


# ==========================================
# 🎯 AGENT 5: FIBONACCI AGENT
# ==========================================
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
                    if fib > 1 and len(encoded) >= fib:
                        votes[encoded[-(fib - 1)]] += 1.0 / fib

            total = votes[0] + votes[1]
            if total < 0.3:
                return None, 0

            pred = 1 if votes[1] > votes[0] else 0
            conf = max(votes.values()) / total
            return ("Big" if pred == 1 else "Small"), min(0.55 + conf * 0.25, 0.75)
        except Exception as e:
            print(f"FibonacciAgent Error: {e}", flush=True)
            return None, 0


# ==========================================
# 🆕 AGENT 6: MARKOV AGENT
# ==========================================
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
        except Exception as e:
            print(f"MarkovAgent Error: {e}", flush=True)
            return None, 0


# ==========================================
# 🆕 AGENT 7: KNN AGENT
# ==========================================
class KNNAgent:
    NAME = "knn"

    def predict(self, encoded, window, k=4):
        try:
            if len(encoded) < 25:
                return ("Big" if encoded[-1] == 1 else "Small"), 0.51

            target_pattern = list(encoded[-k:])
            matches = []

            for i in range(len(encoded) - k - 1):
                window_slice = list(encoded[i : i + k])
                if window_slice == target_pattern:
                    matches.append(encoded[i + k])

            if not matches:
                return ("Big" if encoded[-1] == 1 else "Small"), 0.51

            big_count = sum(matches)
            small_count = len(matches) - big_count

            if big_count >= small_count:
                return "Big", min(0.50 + (big_count / len(matches)) * 0.25, 0.75)
            else:
                return "Small", min(0.50 + (small_count / len(matches)) * 0.25, 0.75)
        except Exception as e:
            print(f"KNNAgent Error: {e}", flush=True)
            return None, 0


# ==========================================
# 🆕 AGENT 8: RUNS TEST AGENT
# ==========================================
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
            last_val = encoded[-1]

            if z < -1.0:
                return ("Big" if last_val == 1 else "Small"), 0.58
            elif z > 1.0:
                return ("Small" if last_val == 1 else "Big"), 0.58

            return ("Big" if last_val == 1 else "Small"), 0.51
        except Exception as e:
            print(f"RunsTestAgent Error: {e}", flush=True)
            return None, 0


# ==========================================
# 🆕 AGENT 9: DIGIT BIAS AGENT
# ==========================================
class DigitBiasAgent:
    NAME = "digit_bias"

    def predict(self, digit_history):
        try:
            if len(digit_history) < 15:
                return None, 0

            recent_digits = list(digit_history)[-10:]
            avg_val = sum(recent_digits) / len(recent_digits)

            if avg_val > 5.5:
                return "Small", min(0.55 + (avg_val - 4.5) * 0.05, 0.70)
            elif avg_val < 3.5:
                return "Big", min(0.55 + (4.5 - avg_val) * 0.05, 0.70)

            last_d = digit_history[-1]
            return ("Big" if last_d >= 5 else "Small"), 0.52
        except Exception as e:
            print(f"DigitBiasAgent Error: {e}", flush=True)
            return None, 0


# ==========================================
# 🆕 AGENT 10: EMA RIBBON AGENT
# ==========================================
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
        except Exception as e:
            print(f"EMARibbonAgent Error: {e}", flush=True)
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
        except Exception as e:
            print(f"MarketDetector Error: {e}", flush=True)
            return "unknown", 0.5


# ==========================================
# 🎯 META-AGENT (10 Agents + Thompson)
# ==========================================
class MetaAgent:
    def __init__(self):
        # 10 Agents
        self.trend_agent = TrendAgent()
        self.mean_rev_agent = MeanReversionAgent()
        self.pattern_agent = PatternAgent()
        self.breakout_agent = BreakoutAgent()
        self.fib_agent = FibonacciAgent()
        self.markov_agent = MarkovAgent()
        self.knn_agent = KNNAgent()
        self.runs_agent = RunsTestAgent()
        self.digit_agent = DigitBiasAgent()
        self.ema_agent = EMARibbonAgent()

        # Thompson Sampling Stats (alpha, beta)
        self.thompson_stats = {
            "trend": {"a": 2, "b": 2},
            "mean_rev": {"a": 2, "b": 2},
            "pattern": {"a": 2, "b": 2},
            "breakout": {"a": 2, "b": 2},
            "fibonacci": {"a": 2, "b": 2},
            "markov": {"a": 2, "b": 2},
            "knn": {"a": 2, "b": 2},
            "runs_test": {"a": 2, "b": 2},
            "digit_bias": {"a": 2, "b": 2},
            "ema_ribbon": {"a": 2, "b": 2},
        }

        # Accuracy tracking
        self.agent_acc = {k: deque(maxlen=50) for k in self.thompson_stats}
        self.pending_agents = {}

    def get_active_agents(self, regime):
        """Regime-based Agent Selection"""
        if regime == "trending":
            return ["trend", "breakout", "fibonacci", "pattern", "markov", "ema_ribbon"]
        elif regime == "sideway":
            return ["mean_rev", "pattern", "fibonacci", "trend", "knn", "digit_bias"]
        elif regime == "choppy":
            return ["pattern", "fibonacci", "mean_rev", "breakout", "markov", "knn"]
        elif regime == "volatile":
            return ["breakout", "trend", "fibonacci", "pattern", "runs_test", "ema_ribbon"]
        else:  # neutral
            return ["trend", "mean_rev", "pattern", "breakout", "fibonacci",
                    "markov", "knn", "runs_test", "digit_bias", "ema_ribbon"]

    def get_thompson_weight(self, name):
        """Thompson Sampling Weight"""
        try:
            stats = self.thompson_stats.get(name, {"a": 2, "b": 2})
            return float(np.random.beta(stats["a"], stats["b"]))
        except Exception:
            return 1.0

    def predict(self, encoded, window, regime, digit_history):
        try:
            active = self.get_active_agents(regime)
            signals = {}

            agents_map = {
                "trend": lambda: self.trend_agent.predict(encoded, window),
                "mean_rev": lambda: self.mean_rev_agent.predict(encoded, window),
                "pattern": lambda: self.pattern_agent.predict(encoded, window),
                "breakout": lambda: self.breakout_agent.predict(encoded, window),
                "fibonacci": lambda: self.fib_agent.predict(encoded, window),
                "markov": lambda: self.markov_agent.predict(encoded, window),
                "knn": lambda: self.knn_agent.predict(encoded, window),
                "runs_test": lambda: self.runs_agent.predict(encoded, window),
                "digit_bias": lambda: self.digit_agent.predict(digit_history),
                "ema_ribbon": lambda: self.ema_agent.predict(encoded, window),
            }

            for name in active:
                try:
                    result = agents_map[name]()
                    if result and result[0] and result[1] > 0:
                        signals[name] = result
                except Exception as e:
                    print(f"Agent {name} Error: {e}", flush=True)

            # Min Agents Check
            if len(signals) < CONFIG['min_agents_for_signal']:
                return None, 0, f"Agents {len(signals)}/{len(active)}", regime

            # Weighted Voting with Thompson Sampling
            big_score = 0.0
            small_score = 0.0

            for name, (pred, conf) in signals.items():
                # Thompson weight + accuracy weight
                thompson_w = self.get_thompson_weight(name)

                acc_w = 1.0
                if len(self.agent_acc[name]) >= 10:
                    acc = sum(self.agent_acc[name]) / len(self.agent_acc[name])
                    acc_w = 0.5 + acc * 1.5

                weight = thompson_w * acc_w
                weighted = conf * weight

                if pred == "Big":
                    big_score += weighted
                else:
                    small_score += weighted

            total = big_score + small_score
            if total == 0:
                return None, 0, "No Vote", regime

            margin = abs(big_score - small_score) / total
            if margin < CONFIG['min_margin']:
                return None, 0, f"Low Margin {margin:.0%}", regime

            confidence = max(big_score, small_score) / total
            confidence = max(0.52, min(confidence, 0.92))

            if big_score > small_score:
                return "Big", confidence, f"🎯 Agent[{len(signals)}] {regime}", regime
            else:
                return "Small", confidence, f"🎯 Agent[{len(signals)}] {regime}", regime

        except Exception as e:
            print(f"MetaAgent Error: {e}", flush=True)
            return None, 0, "Error", regime

    def update_accuracy(self, actual):
        try:
            for name, pred in self.pending_agents.items():
                is_correct = 1 if pred == actual else 0
                if name in self.agent_acc:
                    self.agent_acc[name].append(is_correct)

                # Thompson update
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
            active = self.get_active_agents(regime)

            agents_map = {
                "trend": lambda: self.trend_agent.predict(encoded, window),
                "mean_rev": lambda: self.mean_rev_agent.predict(encoded, window),
                "pattern": lambda: self.pattern_agent.predict(encoded, window),
                "breakout": lambda: self.breakout_agent.predict(encoded, window),
                "fibonacci": lambda: self.fib_agent.predict(encoded, window),
                "markov": lambda: self.markov_agent.predict(encoded, window),
                "knn": lambda: self.knn_agent.predict(encoded, window),
                "runs_test": lambda: self.runs_agent.predict(encoded, window),
                "digit_bias": lambda: self.digit_agent.predict(digit_history),
                "ema_ribbon": lambda: self.ema_agent.predict(encoded, window),
            }

            self.pending_agents = {}
            for name in active:
                try:
                    result = agents_map[name]()
                    if result and result[0]:
                        self.pending_agents[name] = result[0]
                except Exception:
                    pass
        except Exception as e:
            print(f"record_pending Error: {e}", flush=True)


# ==========================================
# 🎯 V16.2 ENGINE
# ==========================================
class V16Engine:
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

        self.market_detector = MarketDetector()
        self.meta_agent = MetaAgent()
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
                    if res.status_code == 200: return
                except:
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
            old_max_level = self.max_level_reached
            report = (
                f"🎉 <b>PROFIT RESET</b>\n\n"
                f"💰 Net Profit: <b>+{self.current_profit:,.0f}</b>\n\n"
                f"━━━━━━━━━━━━━━━━━\n"
                f"📈 Total Profit: <b>+{self.total_profit:,.0f}</b>\n"
                f"📉 Total Loss: <b>-{self.total_loss_amount:,.0f}</b>\n"
                f"🔻 Max DD: <b>{self.max_loss_amount:,.0f}</b>\n\n"
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

    def get_consensus(self):
        try:
            encoded = [FeatureEngineer.encode(r) for r in self.window]
            regime, strength = self.market_detector.detect(encoded)
            self.current_regime = regime

            pred, conf, mode, regime = self.meta_agent.predict(
                encoded, self.window, regime, self.digit_history
            )

            if pred is None:
                return None, 0, mode, regime

            threshold = self.get_threshold()
            if conf < threshold:
                return None, 0, f"Low Conf {conf:.1%}", regime

            return pred, conf, mode, regime
        except Exception as e:
            print(f"get_consensus Error: {e}", flush=True)
            return None, 0, "Error", "unknown"

    def get_threshold(self):
        base = CONFIG['adaptive_base_threshold']
        if len(self.recent_results) < 10:
            return base + 0.02
        recent_wr = sum(self.recent_results) / len(self.recent_results)
        if recent_wr >= 0.65: return base - 0.04
        elif recent_wr >= 0.55: return base - 0.02
        elif recent_wr >= 0.48: return base
        else: return base + 0.04

    def process_api_result(self, api_period, api_result, digit=None):
        with self.lock:
            self._process_internal(api_period, api_result, digit)

    def _process_internal(self, api_period, api_result, digit):
        try:
            api_period_int = int(api_period)
        except:
            return
        notifications = []

        if digit is not None:
            self.last_digit = digit
            self.digit_history.append(digit)

        if self.active_prediction is not None and self.last_state is not None:
            bot_won = (self.active_prediction == api_result)
            self.recent_results.append(1 if bot_won else 0)

            self.meta_agent.update_accuracy(api_result)

            if bot_won: self.total_wins += 1
            else: self.total_losses += 1

            bet_amount, bet_type = self.get_current_bet()

            if bot_won:
                profit_amount = bet_amount * CONFIG['payout_rate']
                self.total_profit += profit_amount
                self.current_profit += profit_amount
            else:
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
# 🌐 API POLLER
# ==========================================
def run_bot():
    print("🚀 V16.2 — 10 Agents + Thompson Sampling", flush=True)
    agent = V16Engine()
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
        return "<h3>🚀 V16.2 starting...</h3>"
    a = global_agent
    bet_amount, bet_type = a.get_current_bet()
    return f"""
    <h2>🚀 V16.2 — 10 Agents + Thompson</h2>
    <p><b>🎯 Regime:</b> {a.current_regime}</p>
    <p><b>🤖 Bot Step:</b> {a.bot_step}x</p>
    <p><b>🎮 Level:</b> {a.level} | {a.level_state}</p>
    <p><b>💰 Bet:</b> {bet_amount:,} ({bet_type})</p>
    <p><b>💵 Profit:</b> {a.current_profit:+,.0f}</p>
    <p><b>📊 WR:</b> {a.get_wr():.1f}%</p>
    """

@app.route('/stats')
def stats():
    if global_agent:
        a = global_agent
        bet_amount, bet_type = a.get_current_bet()
        return {
            "version": "V16.2",
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
                thompson = a.meta_agent.thompson_stats.get(name, {})
                result[name] = f"{acc:.1%} (n={len(acc_deque)}, a={thompson.get('a', 0)}, b={thompson.get('b', 0)})"
            else:
                result[name] = f"warming ({len(acc_deque)})"
        return dict(sorted(result.items(), key=lambda x: x[1], reverse=True))
    return {"status": "initializing"}

@app.route('/health')
def health():
    return {"status": "ok", "version": "V16.2"}


# ==========================================
# 🚀 ENTRY
# ==========================================
if __name__ == "__main__":
    threading.Thread(target=run_bot, daemon=True).start()
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
