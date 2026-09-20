"""
🚀 V20.6.1 PRODUCTION FIXED
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Fixes Applied:
  1. Cleaned all non-breaking spaces (\xa0) to valid ASCII spaces.
  2. Fixed V20Engine.is_warmup reset bug after initial batch.
  3. Fixed process_api_result return signature to always return a list.
  4. Fixed HMM transition probability division and stability issues.
  5. Handled BOCPD zero-division and distribution underflow gracefully.
  6. Added SQLite timeout=10.0 to prevent database lock contention.
  7. Thread-safe locks applied across Flask endpoints and Telegram poller.
  8. Guarded zero-division cases in RunsTestAgent and SurvivalAnalyzer.
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
    "candle_max_size": 3000,
    "candle_db_path": "candles.db",
    "min_data_before_signal": 30,
    "adaptive_base_threshold": 0.55,
    "min_agents_for_signal": 1,
    "min_agent_wr": 0.50,
    "reactivate_wr": 0.55,
    "suspend_wr": 0.45,
    "min_sample": 30,
    "api_url": "https://6lotteryapi.com/api/webapi/GetNoaverageEmerdList",
    "payout_rate": 0.96,
    "profit_reset_threshold": 100000,
    "max_level": 15,
    "hmm_states": 4,
    "hmm_train_size": 500,
    "stacking_train_size": 1000,
    "stacking_l2": 0.01,
    "online_adam_lr": 0.001,
    "online_scaler_refit": 200,
    "adversarial_train_size": 500,
    "adversarial_threshold": 0.65,
    "adversarial_baseline_size": 100,
    "bocpd_hazard_rate": 1 / 25,
    "bocpd_max_rl": 200,
    "bocpd_cp_threshold": 0.2,
    "cusum_shift_min": 0.02,
    "cusum_threshold": 4.0,
    "survival_min_streaks": 20,
    "kalman_process_var": 0.01,
    "kalman_measurement_var": 0.1,
    "kalman_conf_threshold": 0.7,
    "pe_order": 3,
}

# ==========================================
# 📊 LEVEL TABLE
# ==========================================
LEVEL_TABLE = {
    1:  {"bet1": 1000,   "bet2": 2000},
    2:  {"bet1": 1000,   "bet2": 2000},
    3:  {"bet1": 2000,   "bet2": 4000},
    4:  {"bet1": 2000,   "bet2": 4000},
    5:  {"bet1": 3000,   "bet2": 6000},
    6:  {"bet1": 4000,   "bet2": 8000},
    7:  {"bet1": 6000,   "bet2": 12000},
    8:  {"bet1": 8000,   "bet2": 16000},
    9:  {"bet1": 10000,  "bet2": 20000},
    10: {"bet1": 14000,  "bet2": 28000},
    11: {"bet1": 19000,  "bet2": 38000},
    12: {"bet1": 25000,  "bet2": 50000},
    13: {"bet1": 34000,  "bet2": 68000},
    14: {"bet1": 46000,  "bet2": 92000},
    15: {"bet1": 62000,  "bet2": 124000},
}


def get_level_bet(level):
    if level in LEVEL_TABLE:
        return LEVEL_TABLE[level]
    a = LEVEL_TABLE[14]["bet1"]
    b = LEVEL_TABLE[15]["bet1"]
    for _ in range(level - 15):
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
                segment = y[i * s: (i + 1) * s]
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
        p_small = 1.0 - p_big
        if p_big <= 0.0 or p_small <= 0.0:
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
# ✅ BOCPD (Threshold 0.2)
# ==========================================
class BOCPD:
    def __init__(self, hazard_rate=1 / 25, max_rl=200, cp_threshold=0.2):
        self.hazard_rate = hazard_rate
        self.max_rl = max_rl
        self.cp_threshold = cp_threshold
        self.run_length_dist = {0: 1.0}
        self.alpha = {0: 1.0}
        self.beta = {0: 1.0}
        self.total_updates = 0
        self.changepoints_detected = 0
        self.last_cp_prob = 0.0

    def update(self, observation):
        try:
            new_dist = {}
            new_alpha = {}
            new_beta = {}

            pred_probs = {}
            for r in self.run_length_dist:
                a = self.alpha.get(r, 1.0)
                b = self.beta.get(r, 1.0)
                pred_probs[r] = a / (a + b)

            for r in self.run_length_dist:
                p = pred_probs[r]
                likelihood = p if observation == 1 else (1.0 - p)
                likelihood = max(likelihood, 1e-10)

                new_r = r + 1
                if new_r <= self.max_rl:
                    new_dist[new_r] = self.run_length_dist[r] * likelihood * (1.0 - self.hazard_rate)
                    new_alpha[new_r] = self.alpha.get(r, 1.0) + observation
                    new_beta[new_r] = self.beta.get(r, 1.0) + (1.0 - observation)

            cp_prob = 0.0
            for r in self.run_length_dist:
                p = pred_probs[r]
                lik = p if observation == 1 else (1.0 - p)
                cp_prob += self.run_length_dist[r] * lik * self.hazard_rate
            cp_prob = max(cp_prob, 1e-10)

            new_dist[0] = cp_prob
            new_alpha[0] = 1.0 + observation
            new_beta[0] = 1.0 + (1.0 - observation)

            total = sum(new_dist.values())
            if total > 0:
                new_dist = {k: v / total for k, v in new_dist.items()}
            else:
                new_dist = {0: 1.0}

            self.run_length_dist = new_dist
            self.alpha = new_alpha
            self.beta = new_beta
            self.total_updates += 1

            is_cp = new_dist.get(0, 0) > self.cp_threshold
            if is_cp:
                self.changepoints_detected += 1
            self.last_cp_prob = new_dist.get(0, 0)

            erl = sum(r * p for r, p in new_dist.items())

            return {
                "changepoint_prob": new_dist.get(0, 0),
                "is_changepoint": is_cp,
                "expected_run_length": erl,
            }
        except Exception:
            return {"changepoint_prob": 0, "is_changepoint": False, "expected_run_length": 0}

    def get_prediction(self):
        try:
            if not self.run_length_dist:
                return 0.5
            pred = 0.0
            for r, prob in self.run_length_dist.items():
                a = self.alpha.get(r, 1.0)
                b = self.beta.get(r, 1.0)
                pred += (a / (a + b)) * prob
            return pred
        except Exception:
            return 0.5


# ==========================================
# ✅ CUSUM
# ==========================================
class CUSUMDetector:
    def __init__(self, baseline_p=0.5, shift_min=0.02, threshold=4.0, drift=0.001):
        self.baseline_p = baseline_p
        self.shift_min = shift_min
        self.threshold = threshold
        self.drift = drift
        self.g_plus = 0.0
        self.g_minus = 0.0
        self.alarms = 0
        self.last_shift = None
        self.shift_confidence = 0.0

    def update(self, observation):
        try:
            p0 = self.baseline_p
            p1 = min(self.baseline_p + self.shift_min, 0.99)
            if observation == 1:
                lr = math.log(p1 / p0) if p0 > 0 and p1 > 0 else 0
            else:
                lr = math.log((1 - p1) / (1 - p0)) if (1 - p0) > 0 and (1 - p1) > 0 else 0

            self.g_plus = max(0.0, self.g_plus + lr - self.drift)
            self.g_minus = max(0.0, self.g_minus - lr - self.drift)
            self.shift_confidence = max(self.g_plus, self.g_minus) / self.threshold

            if self.g_plus > self.threshold:
                self.alarms += 1
                self.last_shift = "increase"
                self.g_plus = 0.0
                return True, "increase"
            elif self.g_minus > self.threshold:
                self.alarms += 1
                self.last_shift = "decrease"
                self.g_minus = 0.0
                return True, "decrease"
            return False, None
        except Exception:
            return False, None


# ==========================================
# ✅ SURVIVAL
# ==========================================
class SurvivalAnalyzer:
    def __init__(self):
        self.streaks = []
        self.current_streak = 0
        self.current_direction = None
        self.survival_func = {0: 1.0}
        self.hazard_func = {}
        self.min_streaks = CONFIG['survival_min_streaks']

    def record_streak(self, length, direction):
        self.streaks.append((length, direction))
        self._update_survival()

    def _update_survival(self):
        try:
            if not self.streaks:
                return
            max_streak = max(s[0] for s in self.streaks)
            self.survival_func = {0: 1.0}
            self.hazard_func = {}
            for k in range(1, max_streak + 2):
                at_risk = sum(1 for s in self.streaks if s[0] >= k)
                if at_risk == 0:
                    break
                ended = sum(1 for s in self.streaks if s[0] == k)
                self.survival_func[k] = self.survival_func.get(k - 1, 1.0) * (1.0 - (ended / at_risk))
                self.hazard_func[k] = ended / at_risk
        except Exception:
            pass

    def update(self, current_result):
        try:
            encoded = 1 if current_result == "Big" else 0
            if self.current_direction is None:
                self.current_direction = encoded
                self.current_streak = 1
            elif encoded == self.current_direction:
                self.current_streak += 1
            else:
                self.record_streak(self.current_streak, self.current_direction)
                self.current_direction = encoded
                self.current_streak = 1

            if len(self.streaks) < self.min_streaks:
                return None, 0, 0

            k = self.current_streak
            max_known = max(self.survival_func.keys()) if self.survival_func else 0

            if k > max_known:
                return None, 0, 0

            s_k = self.survival_func.get(k, 1.0)
            s_k1 = self.survival_func.get(k + 1, None)

            if s_k1 is None or s_k <= 0:
                return None, 0, 0

            p_end = max(0.0, 1.0 - (s_k1 / s_k))

            if p_end > 0.6:
                prediction = "Small" if self.current_direction == 1 else "Big"
                confidence = min(p_end, 0.85)
            else:
                prediction = "Big" if self.current_direction == 1 else "Small"
                confidence = min(1.0 - p_end, 0.75)

            return prediction, confidence, p_end
        except Exception:
            return None, 0, 0


# ==========================================
# ✅ KALMAN
# ==========================================
class KalmanFilter1D:
    def __init__(self, process_var=0.01, measurement_var=0.1):
        self.x = 0.5
        self.P = 1.0
        self.Q = process_var
        self.R = measurement_var

    def predict(self):
        self.P = self.P + self.Q

    def update(self, measurement):
        try:
            K = self.P / (self.P + self.R)
            self.x = self.x + K * (measurement - self.x)
            self.P = (1.0 - K) * self.P
            return self.x
        except Exception:
            return self.x

    def get_prediction(self):
        if self.x > 0.5:
            return "Big", min(self.x, 0.85)
        else:
            return "Small", min(1.0 - self.x, 0.85)

    def adapt_noise(self, signed_errors):
        try:
            if len(signed_errors) >= 10:
                error_var = float(np.var(signed_errors))
                mean_error = float(np.mean(signed_errors))
                if error_var > 0.05:
                    self.R = min(self.R * 1.1, 0.5)
                else:
                    self.R = max(self.R * 0.9, 0.01)
                if abs(mean_error) > 0.1:
                    self.Q = min(self.Q * 1.2, 0.1)
                else:
                    self.Q = max(self.Q * 0.8, 0.001)
        except Exception:
            pass


# ==========================================
# ✅ PERMUTATION ENTROPY
# ==========================================
class PermutationEntropy:
    def __init__(self, order=3, window=50):
        self.order = order
        self.window = window
        self.n_patterns = math.factorial(order)
        self.recent_data = deque(maxlen=window)

    def update_single(self, observation):
        self.recent_data.append(observation)

    def compute(self):
        try:
            if len(self.recent_data) < self.order:
                return 0.5, False
            pattern_counts = Counter()
            data = list(self.recent_data)
            for i in range(len(data) - self.order + 1):
                window = data[i:i + self.order]
                indexed = list(enumerate(window))
                indexed.sort(key=lambda x: x[1])
                pattern = [0] * len(window)
                for rank, (idx, val) in enumerate(indexed):
                    pattern[idx] = rank
                pattern_counts[tuple(pattern)] += 1
            total = sum(pattern_counts.values())
            if total == 0:
                return 0.5, False
            entropy = 0.0
            for count in pattern_counts.values():
                p = count / total
                if p > 0:
                    entropy -= p * math.log2(p)
            max_entropy = math.log2(self.n_patterns)
            normalized = entropy / max_entropy if max_entropy > 0 else 0.5
            return normalized, normalized < 0.85
        except Exception:
            return 0.5, False


# ==========================================
# STANDARD SCALER
# ==========================================
class StandardScaler:
    def __init__(self):
        self.mean = None
        self.std = None
        self.fitted = False

    def fit(self, X):
        try:
            X = np.array(X)
            self.mean = np.mean(X, axis=0)
            self.std = np.std(X, axis=0) + 1e-8
            self.fitted = True
        except Exception:
            self.fitted = False

    def transform(self, X):
        try:
            if not self.fitted:
                return X
            return (np.array(X) - self.mean) / self.std
        except Exception:
            return X

    def fit_transform(self, X):
        self.fit(X)
        return self.transform(X)


# ==========================================
# ✅ HMM (Fixed Vectorized Transition)
# ==========================================
class HMMRegimeDetector:
    def __init__(self, n_states=4):
        self.n_states = n_states
        self.state_names = [f"cluster_{i}" for i in range(n_states)]
        rng = np.random.RandomState(42)
        self.transition = np.ones((n_states, n_states)) / n_states
        self.emission_means = rng.randn(n_states, 4) * 0.5
        self.emission_std = np.ones((n_states, 4)) * 0.5
        self.initial_probs = np.ones(n_states) / n_states
        self.state_probs = np.ones(n_states) / n_states
        self.trained = False

    def extract_features(self, encoded):
        if len(encoded) < 20:
            return None
        momentum = abs(sum(encoded[-5:]) / 5.0 - sum(encoded[-20:]) / 20.0)
        flip_rate = FeatureEngineer.flip_rate(encoded[-20:])
        entropy = FeatureEngineer.entropy(encoded, 20)
        streak = min(FeatureEngineer.streak(encoded) / 10.0, 1.0)
        return np.array([momentum, flip_rate, entropy, streak])

    def emission_prob(self, features, state):
        if features is None:
            return 1.0 / self.n_states
        mean = self.emission_means[state]
        std = np.maximum(self.emission_std[state], 1e-3)
        prob = np.prod(np.exp(-((features - mean) ** 2) / (2 * std ** 2)) / (std * np.sqrt(2 * math.pi)))
        return max(float(prob), 1e-10)

    def forward(self, features):
        try:
            predicted = np.dot(self.state_probs, self.transition)
            emissions = np.array([self.emission_prob(features, s) for s in range(self.n_states)])
            updated = predicted * emissions
            total = updated.sum()
            if total > 0:
                self.state_probs = updated / total
            else:
                self.state_probs = np.ones(self.n_states) / self.n_states
        except Exception:
            self.state_probs = np.ones(self.n_states) / self.n_states

    def train(self, features_list):
        try:
            if len(features_list) < 50:
                return
            X = np.array(features_list)
            n = len(X)
            rng = np.random.RandomState(42)
            resp = rng.rand(n, self.n_states)
            resp /= resp.sum(axis=1, keepdims=True)

            for iteration in range(20):
                weight_sum = resp.sum(axis=0) + 1e-10
                self.emission_means = (resp.T @ X) / weight_sum[:, None]

                for s in range(self.n_states):
                    diff = X - self.emission_means[s]
                    var = (resp[:, s:s + 1] * diff ** 2).sum(axis=0) / weight_sum[s]
                    self.emission_std[s] = np.sqrt(var) + 1e-3

                new_resp = np.zeros_like(resp)
                for s in range(self.n_states):
                    mean = self.emission_means[s]
                    std = np.maximum(self.emission_std[s], 1e-3)
                    diff = (X - mean) / std
                    log_prob = -0.5 * np.sum(diff ** 2, axis=1) - np.sum(np.log(std))
                    new_resp[:, s] = log_prob

                new_resp = np.exp(new_resp - new_resp.max(axis=1, keepdims=True))
                new_resp /= np.maximum(new_resp.sum(axis=1, keepdims=True), 1e-12)

                if np.allclose(resp, new_resp, atol=1e-4):
                    break
                resp = new_resp

            trans = np.zeros((self.n_states, self.n_states))
            for t in range(n - 1):
                trans += np.outer(resp[t], resp[t + 1])
            row_sums = trans.sum(axis=1, keepdims=True)
            row_sums[row_sums == 0] = 1.0
            self.transition = trans / row_sums

            self.initial_probs = resp[0] / resp[0].sum()
            self.trained = True
        except Exception as e:
            print(f"HMM Train Error: {e}", flush=True)

    def detect(self, encoded):
        try:
            features = self.extract_features(encoded)
            if features is None:
                return "unknown", 0.5
            self.forward(features)
            best_state = int(np.argmax(self.state_probs))
            confidence = float(self.state_probs[best_state])
            return self.state_names[best_state], confidence
        except Exception:
            return "unknown", 0.5


# ==========================================
# STACKING META-MODEL
# ==========================================
class StackingMetaModel:
    def __init__(self, n_features=12, l2_lambda=0.01):
        self.n_features = n_features
        self.l2_lambda = l2_lambda
        self.W = np.random.randn(n_features, 1) * 0.01
        self.b = 0.0
        self.lr = 0.05
        self.train_X = deque(maxlen=CONFIG['stacking_train_size'])
        self.train_y = deque(maxlen=CONFIG['stacking_train_size'])
        self.scaler = StandardScaler()
        self.trained = False
        self.samples_since_train = 0

    def sigmoid(self, z):
        return 1.0 / (1.0 + np.exp(-np.clip(z, -500, 500)))

    def forward(self, X):
        return self.sigmoid(np.dot(X, self.W) + self.b)

    def predict(self, features):
        try:
            X = np.array(features).reshape(1, -1)
            X_scaled = self.scaler.transform(X)
            return float(self.forward(X_scaled)[0][0])
        except Exception:
            return 0.5

    def add_training(self, features, label):
        try:
            if len(features) != self.n_features:
                return
            self.train_X.append(features)
            self.train_y.append(label)
            self.samples_since_train += 1
        except Exception:
            pass

    def should_train(self):
        return self.samples_since_train >= 50 and len(self.train_X) >= 100

    def train(self, epochs=20):
        try:
            if len(self.train_X) < 100:
                return
            X = np.array(list(self.train_X))
            y = np.array(list(self.train_y)).reshape(-1, 1)
            m = X.shape[0]
            X = self.scaler.fit_transform(X)

            for _ in range(epochs):
                preds = self.forward(X)
                error = preds - y
                grad_W = (np.dot(X.T, error) / m) + self.l2_lambda * self.W
                grad_b = np.sum(error) / m
                self.W -= self.lr * grad_W
                self.b -= self.lr * float(grad_b)

            self.trained = True
            self.samples_since_train = 0
        except Exception as e:
            print(f"Stacking Train Error: {e}", flush=True)


# ==========================================
# ONLINE LEARNER
# ==========================================
class AdamOnlineLearner:
    def __init__(self, n_features=12, lr=0.001, beta1=0.9, beta2=0.999):
        self.n_features = n_features
        self.lr = lr
        self.beta1 = beta1
        self.beta2 = beta2
        self.epsilon = 1e-8
        self.weights = np.zeros(n_features)
        self.bias = 0.0
        self.m_w = np.zeros(n_features)
        self.v_w = np.zeros(n_features)
        self.m_b = 0.0
        self.v_b = 0.0
        self.t = 0
        self.scaler = StandardScaler()
        self.scaler_fitted = False
        self.scaler_buffer = deque(maxlen=500)
        self.update_count = 0
        self.history = deque(maxlen=100)

    def sigmoid(self, z):
        return 1.0 / (1.0 + np.exp(-np.clip(z, -500, 500)))

    def update(self, features, actual):
        try:
            if len(features) != self.n_features:
                return
            self.scaler_buffer.append(np.array(features))

            if not self.scaler_fitted and len(self.scaler_buffer) >= 50:
                self.scaler.fit(list(self.scaler_buffer))
                self.scaler_fitted = True
            elif self.scaler_fitted and self.update_count > 0 and self.update_count % CONFIG['online_scaler_refit'] == 0:
                self.scaler.fit(list(self.scaler_buffer))

            if not self.scaler_fitted:
                return

            X = np.array(features)
            X_scaled = self.scaler.transform(X.reshape(1, -1))[0]

            z = np.dot(X_scaled, self.weights) + self.bias
            pred = self.sigmoid(z)
            error = pred - actual
            grad_w = error * X_scaled
            grad_b = error

            self.t += 1
            self.m_w = self.beta1 * self.m_w + (1 - self.beta1) * grad_w
            self.v_w = self.beta2 * self.v_w + (1 - self.beta2) * grad_w ** 2
            self.m_b = self.beta1 * self.m_b + (1 - self.beta1) * grad_b
            self.v_b = self.beta2 * self.v_b + (1 - self.beta2) * grad_b ** 2

            m_w_hat = self.m_w / (1 - self.beta1 ** self.t)
            v_w_hat = self.v_w / (1 - self.beta2 ** self.t)
            m_b_hat = self.m_b / (1 - self.beta1 ** self.t)
            v_b_hat = self.v_b / (1 - self.beta2 ** self.t)

            self.weights -= self.lr * m_w_hat / (np.sqrt(v_w_hat) + self.epsilon)
            self.bias -= self.lr * m_b_hat / (np.sqrt(v_b_hat) + self.epsilon)

            self.update_count += 1
            self.history.append(error ** 2)
        except Exception:
            pass

    def predict(self, features):
        try:
            if not self.scaler_fitted:
                return 0.5
            X = np.array(features).reshape(1, -1)
            X_scaled = self.scaler.transform(X)[0]
            z = np.dot(X_scaled, self.weights) + self.bias
            return float(self.sigmoid(z))
        except Exception:
            return 0.5


# ==========================================
# ADVERSARIAL VALIDATOR
# ==========================================
class AdversarialValidator:
    def __init__(self, n_features=12):
        self.n_features = n_features
        self.baseline_features = deque(maxlen=CONFIG['adversarial_train_size'])
        self.current_features = deque(maxlen=200)
        self.W = None
        self.b = 0.0
        self.shift_detected = False
        self.auc_estimate = 0.5
        self.trained = False
        self.baseline_frozen = False
        self.samples_seen = 0

    def add_current_feature(self, features):
        try:
            if len(features) != self.n_features:
                return
            self.samples_seen += 1
            arr = np.array(features)

            if not self.baseline_frozen:
                self.baseline_features.append(arr)
                if len(self.baseline_features) >= CONFIG['adversarial_baseline_size']:
                    self.baseline_frozen = True
            else:
                self.current_features.append(arr)
        except Exception:
            pass

    def sigmoid(self, z):
        return 1.0 / (1.0 + np.exp(-np.clip(z, -500, 500)))

    def train_classifier(self):
        try:
            if not self.baseline_frozen:
                return False
            if len(self.baseline_features) < 50 or len(self.current_features) < 30:
                return False
            X = np.vstack([list(self.baseline_features), list(self.current_features)])
            y = np.array([0] * len(self.baseline_features) + [1] * len(self.current_features)).reshape(-1, 1)
            mean = X.mean(axis=0)
            std = X.std(axis=0) + 1e-8
            X_scaled = (X - mean) / std
            m, n = X_scaled.shape
            self.W = np.zeros((n, 1))
            self.b = 0.0
            lr = 0.1

            for _ in range(100):
                z = np.dot(X_scaled, self.W) + self.b
                preds = self.sigmoid(z)
                error = preds - y
                grad_W = np.dot(X_scaled.T, error) / m
                grad_b = np.sum(error) / m
                self.W -= lr * grad_W
                self.b -= lr * float(grad_b)

            self.trained = True
            return True
        except Exception:
            return False

    def compute_auc(self):
        try:
            if not self.trained:
                return 0.5
            X = np.vstack([list(self.baseline_features), list(self.current_features)])
            y = np.array([0] * len(self.baseline_features) + [1] * len(self.current_features))
            mean = X.mean(axis=0)
            std = X.std(axis=0) + 1e-8
            X_scaled = (X - mean) / std
            z = np.dot(X_scaled, self.W) + self.b
            probs = self.sigmoid(z).flatten()

            pos_probs = probs[y == 1]
            neg_probs = probs[y == 0]
            if len(pos_probs) == 0 or len(neg_probs) == 0:
                return 0.5

            auc = 0.0
            for p in pos_probs:
                auc += np.sum(p > neg_probs) + 0.5 * np.sum(p == neg_probs)
            auc /= (len(pos_probs) * len(neg_probs))
            return float(auc)
        except Exception:
            return 0.5

    def check_shift(self):
        try:
            if not self.baseline_frozen:
                return False, 0.5
            if len(self.baseline_features) < 50 or len(self.current_features) < 30:
                return False, 0.5
            if not self.trained:
                self.train_classifier()
            self.auc_estimate = self.compute_auc()
            self.shift_detected = self.auc_estimate > CONFIG['adversarial_threshold']
            return self.shift_detected, self.auc_estimate
        except Exception:
            return False, 0.5


# ==========================================
# 📊 CANDLE DB (With SQLite Timeout)
# ==========================================
class CandleDB:
    def __init__(self, db_path="candles.db", max_size=3000):
        self.db_path = db_path
        self.max_size = max_size
        self.lock = threading.Lock()
        self.candles = deque(maxlen=max_size)
        self.prev_close = 5.0
        self.last_period = None
        self.insert_count = 0
        self._init_db()
        self._load_recent()

    def _get_conn(self):
        return sqlite3.connect(self.db_path, timeout=10.0)

    def _init_db(self):
        try:
            with self._get_conn() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS candles (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        period TEXT UNIQUE, digit INTEGER,
                        open REAL, high REAL, low REAL, close REAL,
                        color TEXT, big_small TEXT, timestamp INTEGER
                    )
                """)
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_period ON candles(period)")
                conn.commit()
        except Exception as e:
            print(f"DB Init Error: {e}", flush=True)

    def _load_recent(self):
        try:
            with self._get_conn() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT period, digit, open, high, low, close, color, big_small, timestamp
                    FROM candles ORDER BY id DESC LIMIT ?
                """, (self.max_size,))
                rows = cursor.fetchall()
            for row in reversed(rows):
                self.candles.append({
                    "period": row[0], "digit": row[1], "open": row[2], "high": row[3],
                    "low": row[4], "close": row[5], "color": row[6],
                    "big_small": row[7], "timestamp": row[8],
                })
                self.prev_close = row[5]
                self.last_period = row[0]
            print(f"✅ Loaded {len(self.candles)} candles", flush=True)
        except Exception as e:
            print(f"Load Error: {e}", flush=True)

    def add(self, digit, period=None):
        try:
            if period == self.last_period:
                return None
            open_p = self.prev_close
            close_p = float(digit)
            high_p = max(open_p, close_p) + 0.5
            low_p = min(open_p, close_p) - 0.5
            candle = {
                "period": str(period or int(time.time())),
                "digit": digit, "open": open_p, "high": high_p,
                "low": low_p, "close": close_p,
                "color": "green" if digit >= 5 else "red",
                "big_small": "Big" if digit >= 5 else "Small",
                "timestamp": int(time.time()),
            }
            with self.lock:
                self.candles.append(candle)
                self.prev_close = close_p
                self.last_period = candle["period"]
                try:
                    with self._get_conn() as conn:
                        cursor = conn.cursor()
                        cursor.execute("""
                            INSERT OR REPLACE INTO candles
                            (period, digit, open, high, low, close, color, big_small, timestamp)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (candle["period"], candle["digit"], candle["open"], candle["high"],
                              candle["low"], candle["close"], candle["color"],
                              candle["big_small"], candle["timestamp"]))
                        conn.commit()
                except Exception:
                    pass
                self.insert_count += 1
                if self.insert_count % 100 == 0:
                    self._prune()
            return candle
        except Exception:
            return None

    def _prune(self):
        try:
            with self._get_conn() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    DELETE FROM candles WHERE id NOT IN (
                        SELECT id FROM candles ORDER BY id DESC LIMIT ?
                    )
                """, (self.max_size,))
                conn.commit()
        except Exception:
            pass

    def get_candles(self):
        with self.lock:
            return list(self.candles)

    def get_count(self):
        with self.lock:
            return len(self.candles)


# ==========================================
# CHART ANALYZER
# ==========================================
class ChartWebAnalyzer:
    def analyze(self, candles):
        try:
            if len(candles) < 20:
                return None, 0, "Warming"
            closes = [c["close"] for c in candles]
            highs = [c["high"] for c in candles]
            lows = [c["low"] for c in candles]

            recent_highs = highs[-10:]
            recent_lows = lows[-10:]
            hh_count = sum(1 for i in range(len(recent_highs) - 1) if recent_highs[i + 1] >= recent_highs[i])
            hl_count = sum(1 for i in range(len(recent_lows) - 1) if recent_lows[i + 1] >= recent_lows[i])
            lh_count = sum(1 for i in range(len(recent_highs) - 1) if recent_highs[i + 1] <= recent_highs[i])
            ll_count = sum(1 for i in range(len(recent_lows) - 1) if recent_lows[i + 1] <= recent_lows[i])

            if hh_count >= 7 and hl_count >= 7:
                return "Big", 0.65, "📈 Uptrend"
            if lh_count >= 7 and ll_count >= 7:
                return "Small", 0.65, "📉 Downtrend"

            resistance = max(highs[-20:])
            support = min(lows[-20:])
            range_size = resistance - support if resistance > support else 1.0
            position = (closes[-1] - support) / range_size

            if position > 0.85:
                return "Small", 0.60, "🔴 Resistance"
            if position < 0.15:
                return "Big", 0.60, "🟢 Support"

            if len(closes) >= 50:
                ema9 = self._ema(closes, 9)
                ema21 = self._ema(closes, 21)
                ema50 = self._ema(closes, 50)
                if all(e is not None for e in [ema9, ema21, ema50]):
                    if ema9 > ema21 > ema50:
                        return "Big", 0.60, "📈 EMA Up"
                    if ema9 < ema21 < ema50:
                        return "Small", 0.60, "📉 EMA Down"

            if len(closes) >= 5:
                momentum = closes[-1] - closes[-5]
                if momentum > 1.5:
                    return "Big", 0.58, "🚀 Momentum"
                if momentum < -1.5:
                    return "Small", 0.58, "💥 Momentum"

            if len(closes) >= 15:
                rsi = self._rsi(closes, 14)
                if rsi < 30:
                    return "Big", 0.58, "🟢 RSI Oversold"
                if rsi > 70:
                    return "Small", 0.58, "🔴 RSI Overbought"

            return None, 0, "Neutral"
        except Exception:
            return None, 0, "Error"

    def _ema(self, prices, period):
        if len(prices) < period:
            return prices[-1] if prices else 0.5
        alpha = 2.0 / (period + 1)
        ema = prices[0]
        for p in prices[1:]:
            ema = (p * alpha) + (ema * (1.0 - alpha))
        return ema

    def _rsi(self, prices, period=14):
        if len(prices) < period + 1:
            return 50.0
        deltas = [prices[i] - prices[i - 1] for i in range(1, len(prices))]
        gains = [max(d, 0.0) for d in deltas[-period:]]
        losses = [max(-d, 0.0) for d in deltas[-period:]]
        avg_gain = sum(gains) / period
        avg_loss = sum(losses) / period
        if avg_loss == 0:
            return 100.0
        rs = avg_gain / avg_loss
        return 100.0 - (100.0 / (1.0 + rs))


# ==========================================
# 🎯 PATTERN AGENTS
# ==========================================
class MeanReversionAgent:
    NAME = "mean_rev"

    def predict(self, encoded, window):
        try:
            if len(encoded) < 15:
                return None, 0
            short_mom = sum(encoded[-5:]) / 5.0
            long_ma = sum(encoded[-20:]) / 20.0 if len(encoded) >= 20 else sum(encoded) / len(encoded)
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
            curr = tuple(history[-order:])
            if curr in transitions:
                zeros, ones = transitions[curr]
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
            if n1 == 0 or n2 == 0 or (n1 + n2 - 1) <= 0:
                return ("Big" if encoded[-1] == 1 else "Small"), 0.55
            runs = 1 + sum(1 for i in range(len(seq) - 1) if seq[i] != seq[i + 1])
            mu = (2 * n1 * n2) / (n1 + n2) + 1
            denom = (((n1 + n2) ** 2) * (n1 + n2 - 1))
            variance = (2 * n1 * n2 * (2 * n1 * n2 - n1 - n2)) / denom if denom > 0 else 0
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
            short_mom = sum(encoded[-3:]) / 3.0
            prev_mom = sum(encoded[-6:-3]) / 3.0 if len(encoded) >= 6 else 0.5
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
            ma_short = sum(encoded[-10:]) / 10.0
            ma_long = sum(encoded[-30:]) / 30.0 if len(encoded) >= 30 else sum(encoded) / len(encoded)
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
        alpha = 2.0 / (span + 1)
        ema = data[0]
        for val in data[1:]:
            ema = (val * alpha) + (ema * (1.0 - alpha))
        return ema

    def predict(self, encoded, window):
        try:
            if len(encoded) < 15:
                return ("Big" if encoded[-1] == 1 else "Small"), 0.51
            ema_fast = self._calc_ema(encoded[-5:], 3)
            ema_mid = self._calc_ema(encoded[-10:], 8)
            ema_slow = self._calc_ema(encoded[-15:], 15)
            if ema_fast > ema_mid > ema_slow:
                return "Big", 0.55 + min((ema_fast - 0.5) * 0.3, 0.20)
            elif ema_fast < ema_mid < ema_slow:
                return "Small", 0.55 + min((0.5 - ema_fast) * 0.3, 0.20)
            return ("Big" if ema_fast >= 0.5 else "Small"), 0.52
        except Exception:
            return None, 0


# ==========================================
# META-AGENT
# ==========================================
class MetaAgent:
    def __init__(self):
        self.all_agents = {
            "mean_rev": MeanReversionAgent(), "markov": MarkovAgent(),
            "knn": KNNAgent(), "runs_test": RunsTestAgent(),
            "fibonacci": FibonacciAgent(), "pattern": PatternAgent(),
            "breakout": BreakoutAgent(), "trend": TrendAgent(),
            "digit_bias": DigitBiasAgent(), "ema_ribbon": EMARibbonAgent(),
        }
        self.chart_analyzer = ChartWebAnalyzer()
        self.stacking = StackingMetaModel(n_features=12, l2_lambda=CONFIG['stacking_l2'])
        self.online_learner = AdamOnlineLearner(n_features=12, lr=CONFIG['online_adam_lr'])

        self.active_agents = ["mean_rev", "markov", "knn", "runs_test", "fibonacci", "pattern"]
        self.suspended_agents = ["breakout", "trend", "digit_bias", "ema_ribbon"]

        self.thompson_stats = {k: {"a": 2, "b": 2} for k in self.all_agents.keys()}
        self.agent_acc = {k: deque(maxlen=50) for k in self.thompson_stats}
        self.pending_agents = {}

        self.mab_strategies = ["chart_only", "pattern_only", "chart_priority", "pattern_priority"]
        self.mab_stats = {s: {"a": 2, "b": 2} for s in self.mab_strategies}
        self.last_strategy = None
        self.stacking_pending = None

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
                "cluster_0": ["mean_rev", "markov", "knn", "fibonacci", "pattern"],
                "cluster_1": ["mean_rev", "pattern", "fibonacci", "knn", "markov"],
                "cluster_2": ["pattern", "fibonacci", "mean_rev", "markov", "knn"],
                "cluster_3": ["markov", "knn", "mean_rev", "fibonacci", "runs_test"],
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

    def select_strategy_mab(self):
        try:
            samples = {}
            for s in self.mab_strategies:
                samples[s] = float(np.random.beta(self.mab_stats[s]["a"], self.mab_stats[s]["b"]))
            best = max(samples, key=samples.get)
            self.last_strategy = best
            return best
        except Exception:
            return "chart_priority"

    def update_mab(self, won):
        try:
            if self.last_strategy is None:
                return
            if won:
                self.mab_stats[self.last_strategy]["a"] += 1
            else:
                self.mab_stats[self.last_strategy]["b"] += 1
        except Exception:
            pass

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

    def build_features(self, chart_pred, chart_conf, pattern_pred, pattern_conf, signals, encoded, regime):
        try:
            features = []
            features.append(chart_conf if chart_pred == "Big" else (1.0 - chart_conf) if chart_pred else 0.5)
            features.append(1.0 if chart_pred else 0.0)
            features.append(pattern_conf if pattern_pred == "Big" else (1.0 - pattern_conf) if pattern_pred else 0.5)
            features.append(1.0 if pattern_pred else 0.0)
            features.append(len(signals) / 10.0)
            big_count = sum(1 for p, c in signals.values() if p == "Big")
            features.append(big_count / max(len(signals), 1))
            features.append(1.0 if regime in ("trending", "cluster_0") else 0.0)
            features.append(1.0 if regime in ("sideway", "cluster_1") else 0.0)
            features.append(1.0 if regime in ("choppy", "cluster_2") else 0.0)
            features.append(1.0 if regime in ("volatile", "cluster_3") else 0.0)
            features.append(sum(encoded[-5:]) / 5.0 if len(encoded) >= 5 else 0.5)
            features.append(FeatureEngineer.streak(encoded) / 10.0)
            return features[:12]
        except Exception:
            return [0.5] * 12

    def predict(self, encoded, window, regime, digit_history, candles, survival_pred=None, survival_conf=0.0):
        try:
            chart_pred, chart_conf, chart_mode = self.chart_analyzer.analyze(candles)
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
                except Exception:
                    pass

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

            strategy = self.select_strategy_mab()
            stacking_features = self.build_features(chart_pred, chart_conf, pattern_pred, pattern_conf, signals, encoded, regime)
            self.stacking_pending = stacking_features

            stacking_prob = self.stacking.predict(stacking_features) if self.stacking.trained else 0.5
            stacking_pred = "Big" if stacking_prob > 0.5 else "Small"
            stacking_conf = max(stacking_prob, 1.0 - stacking_prob)

            online_prob = self.online_learner.predict(stacking_features)
            online_pred = "Big" if online_prob > 0.5 else "Small"
            online_conf = max(online_prob, 1.0 - online_prob)

            if strategy == "chart_only" and chart_pred:
                result_pred, result_conf = chart_pred, chart_conf
            elif strategy == "pattern_only" and pattern_pred:
                result_pred, result_conf = pattern_pred, pattern_conf
            elif strategy == "chart_priority":
                if chart_pred and chart_mode in ["📈 Uptrend", "📉 Downtrend"]:
                    result_pred, result_conf = chart_pred, chart_conf
                elif chart_pred and pattern_pred:
                    result_pred, result_conf = (chart_pred, chart_conf) if chart_conf > pattern_conf else (pattern_pred, pattern_conf)
                elif chart_pred:
                    result_pred, result_conf = chart_pred, chart_conf
                elif pattern_pred:
                    result_pred, result_conf = pattern_pred, pattern_conf
                else:
                    result_pred, result_conf = None, 0
            else:
                if pattern_pred and chart_pred:
                    result_pred, result_conf = (pattern_pred, pattern_conf) if pattern_conf > chart_conf else (chart_pred, chart_conf)
                elif pattern_pred:
                    result_pred, result_conf = pattern_pred, pattern_conf
                elif chart_pred:
                    result_pred, result_conf = chart_pred, chart_conf
                else:
                    result_pred, result_conf = None, 0

            if self.stacking.trained and stacking_conf > 0.65:
                if stacking_pred != result_pred and stacking_conf > result_conf + 0.05:
                    result_pred, result_conf = stacking_pred, stacking_conf

            if self.online_learner.scaler_fitted and online_conf > 0.65:
                if online_pred != result_pred and online_conf > result_conf + 0.05:
                    result_pred, result_conf = online_pred, online_conf

            if survival_pred and survival_conf > 0.65:
                if survival_pred != result_pred and survival_conf > result_conf + 0.05:
                    result_pred, result_conf = survival_pred, survival_conf

            if result_pred is None:
                return None, 0, f"No Signal ({strategy})", regime

            mode = f"🎯 V20.6F [{strategy}] S={stacking_conf:.2f} O={online_conf:.2f}"
            return result_pred, result_conf, mode, regime
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
        except Exception:
            pass

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
        except Exception:
            pass


# ==========================================
# CONFIDENCE CALIBRATOR
# ==========================================
class ConfidenceCalibrator:
    def __init__(self):
        self.buckets = {
            "50-55": {"wins": 0, "total": 0}, "55-60": {"wins": 0, "total": 0},
            "60-65": {"wins": 0, "total": 0}, "65-70": {"wins": 0, "total": 0},
            "70-80": {"wins": 0, "total": 0}, "80+": {"wins": 0, "total": 0},
        }

    def get_bucket(self, conf):
        if conf < 0.55:
            return "50-55"
        elif conf < 0.60:
            return "55-60"
        elif conf < 0.65:
            return "60-65"
        elif conf < 0.70:
            return "65-70"
        elif conf < 0.80:
            return "70-80"
        else:
            return "80+"

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
            if data["total"] >= 30:
                return data["wins"] / data["total"]
            return conf
        except Exception:
            return conf


# ==========================================
# ENGINE
# ==========================================
class V20Engine:
    def __init__(self):
        global global_agent
        global_agent = self
        self.lock = threading.Lock()
        self.window = deque(maxlen=CONFIG['window_size'])
        self.digit_history = deque(maxlen=120)
        self.candle_db = CandleDB(db_path=CONFIG['candle_db_path'], max_size=CONFIG['candle_max_size'])

        self.active_prediction = None
        self.last_state = None
        self.last_digit = None
        self.last_bot_step = None
        self.last_conf = 0.5
        self.last_regime = "unknown"

        self.hmm_detector = HMMRegimeDetector(n_states=CONFIG['hmm_states'])
        self.adversarial = AdversarialValidator(n_features=12)
        self.meta_agent = MetaAgent()
        self.calibrator = ConfidenceCalibrator()
        self.current_regime = "unknown"

        self.bocpd = BOCPD(hazard_rate=CONFIG['bocpd_hazard_rate'], max_rl=CONFIG['bocpd_max_rl'], cp_threshold=CONFIG['bocpd_cp_threshold'])
        self.cusum = CUSUMDetector(baseline_p=0.5, shift_min=CONFIG['cusum_shift_min'], threshold=CONFIG['cusum_threshold'])
        self.survival = SurvivalAnalyzer()
        self.kalman = KalmanFilter1D(process_var=CONFIG['kalman_process_var'], measurement_var=CONFIG['kalman_measurement_var'])
        self.perm_entropy = PermutationEntropy(order=CONFIG['pe_order'], window=50)

        self.kalman_signed_errors = deque(maxlen=50)
        self.hmm_feature_buffer = deque(maxlen=CONFIG['hmm_train_size'])

        self.is_warmup = True
        self.warmup_rounds = 0
        self.shift_check_counter = 0

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
        old_level, old_state = self.level, self.level_state
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
            if recent_wr >= 0.65:
                base -= 0.03
            elif recent_wr < 0.45:
                base += 0.03
        return max(0.50, min(base, 0.65))

    def get_consensus(self, survival_pred=None, survival_conf=0.0):
        try:
            encoded = [FeatureEngineer.encode(r) for r in self.window]
            candles = self.candle_db.get_candles()

            regime, regime_conf = self.hmm_detector.detect(encoded)
            self.current_regime = regime

            hmm_features = self.hmm_detector.extract_features(encoded)
            if hmm_features is not None:
                self.hmm_feature_buffer.append(hmm_features)
                if len(self.hmm_feature_buffer) >= 200 and len(self.hmm_feature_buffer) % 100 == 0:
                    self.hmm_detector.train(list(self.hmm_feature_buffer))

            pred, conf, mode, regime = self.meta_agent.predict(
                encoded, self.window, regime, self.digit_history, candles,
                survival_pred=survival_pred, survival_conf=survival_conf
            )

            if pred is None:
                return None, 0, mode, regime

            calib_conf = self.calibrator.calibrate(conf)

            bocpd_pred = self.bocpd.get_prediction()
            if abs(bocpd_pred - 0.5) > 0.15:
                if (bocpd_pred > 0.5 and pred == "Big") or (bocpd_pred < 0.5 and pred == "Small"):
                    calib_conf = min(calib_conf + 0.02, 0.90)

            if self.cusum.shift_confidence > 0.5:
                if self.cusum.last_shift == "increase" and pred == "Big":
                    calib_conf = min(calib_conf + 0.01, 0.90)
                elif self.cusum.last_shift == "decrease" and pred == "Small":
                    calib_conf = min(calib_conf + 0.01, 0.90)

            kalman_pred, kalman_conf = self.kalman.get_prediction()
            if kalman_conf > CONFIG['kalman_conf_threshold'] and kalman_pred == pred:
                calib_conf = min(calib_conf + 0.01, 0.90)

            pe_entropy, is_structured = self.perm_entropy.compute()
            if is_structured:
                calib_conf = min(calib_conf + 0.01, 0.90)

            threshold = self.get_threshold()
            if calib_conf < threshold:
                return None, 0, f"Low Conf {calib_conf:.1%}", regime

            return pred, calib_conf, mode, regime
        except Exception as e:
            print(f"get_consensus Error: {e}", flush=True)
            return None, 0, "Error", "unknown"

    def process_api_result(self, api_period, api_result, digit=None, is_warmup=False):
        with self.lock:
            return self._process_internal(api_period, api_result, digit, is_warmup)

    def _process_internal(self, api_period, api_result, digit, is_warmup=False):
        notifications = []
        try:
            api_period_int = int(api_period)
        except Exception:
            return notifications

        if digit is not None:
            self.last_digit = digit
            self.digit_history.append(digit)
            self.candle_db.add(digit, period=api_period)

        observation = 1 if api_result == "Big" else 0

        self.bocpd.update(observation)
        self.cusum.update(observation)
        surv_pred, surv_conf, p_end = self.survival.update(api_result)
        self.kalman.predict()
        self.kalman.update(observation)
        self.perm_entropy.update_single(observation)

        if is_warmup:
            self.window.append(api_result)
            self.warmup_rounds += 1
            if self.warmup_rounds % 10 == 0:
                print(f"🔥 Warm-up: {self.warmup_rounds}", flush=True)
            return notifications

        if self.active_prediction is not None and self.last_state is not None:
            bot_won = (self.active_prediction == api_result)
            self.recent_results.append(1 if bot_won else 0)

            self.meta_agent.update_accuracy(api_result)
            self.calibrator.record(self.last_conf, bot_won)
            self.meta_agent.update_mab(bot_won)

            if self.meta_agent.stacking_pending is not None:
                self.meta_agent.stacking.add_training(
                    self.meta_agent.stacking_pending, observation
                )
                if self.meta_agent.stacking.should_train():
                    self.meta_agent.stacking.train(epochs=10)

                self.meta_agent.online_learner.update(
                    self.meta_agent.stacking_pending, observation
                )

                self.adversarial.add_current_feature(self.meta_agent.stacking_pending)

            kalman_p_big = self.kalman.x
            if self.active_prediction:
                kalman_signed = kalman_p_big - observation
                self.kalman_signed_errors.append(kalman_signed)
                if len(self.kalman_signed_errors) >= 20:
                    self.kalman.adapt_noise(list(self.kalman_signed_errors))

            self.shift_check_counter += 1
            if self.shift_check_counter >= 50:
                self.shift_check_counter = 0
                shift, auc = self.adversarial.check_shift()
                if shift:
                    notifications.append(f"⚠️ <b>Distribution Shift</b>\nAUC: {auc:.3f}")

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
            self.last_regime = self.current_regime

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
            pred, conf, mode, regime = self.get_consensus(survival_pred=surv_pred, survival_conf=surv_conf)
            self.meta_agent.record_pending(encoded, self.window, regime, self.digit_history)

            if pred is None:
                notifications.append(f"💖 Period {next_period_short}\n⏭️ <b>SKIP</b> ({mode})")
            else:
                self.active_prediction = pred
                self.last_state = "active"
                self.total_signals += 1
                self.last_bot_step = self.bot_step
                self.last_conf = conf

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

        return notifications


# ==========================================
# TELEGRAM POLLER
# ==========================================
def poll_telegram(agent):
    if not TELEGRAM_TOKEN:
        print("⚠️ TELEGRAM_TOKEN not set — TG disabled", flush=True)
        return

    try:
        requests.get(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/deleteWebhook?drop_pending_updates=true", timeout=10)
    except Exception:
        pass

    offset = 0
    error_count = 0
    while True:
        try:
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates?offset={offset}&timeout=20"
            res = requests.get(url, timeout=25)
            if res.status_code == 200:
                error_count = 0
                for upd in res.json().get("result", []):
                    offset = upd["update_id"] + 1
                    msg = upd.get("message", {})
                    chat = str(msg.get("chat", {}).get("id", ""))
                    text = msg.get("text", "").strip().lower()
                    if chat != CHAT_ID:
                        continue

                    if text == "/status":
                        with agent.lock:
                            b, bt = agent.get_current_bet()
                            status_msg = (
                                f"📊 <b>V20.6 FINAL STATUS</b>\n\n"
                                f"🎯 Regime: <b>{agent.current_regime}</b>\n"
                                f"🔥 Warm-up: <b>{'YES' if agent.is_warmup else 'DONE'}</b>\n"
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
                        agent.send_telegram(status_msg)

                    elif text == "/v206":
                        with agent.lock:
                            v_msg = (
                                f"🧠 <b>V20.6 FINAL</b>\n\n"
                                f"🔄 <b>BOCPD</b>: {agent.bocpd.changepoints_detected} CPs\n"
                                f"📊 <b>CUSUM</b>: {agent.cusum.alarms} alarms\n"
                                f"📈 <b>Survival</b>: {len(agent.survival.streaks)} streaks\n"
                                f"🎯 <b>Kalman</b>: {agent.kalman.x:.3f}\n"
                                f"📚 <b>Stacking</b>: {'Trained' if agent.meta_agent.stacking.trained else 'Warming'}\n"
                                f"🌊 <b>Online</b>: {agent.meta_agent.online_learner.update_count} updates\n"
                                f"🔎 <b>Adversarial</b>: {'Baseline Frozen' if agent.adversarial.baseline_frozen else 'Warming'}\n"
                                f"🔢 <b>HMM</b>: {'Trained' if agent.hmm_detector.trained else 'Warming'}\n"
                                f"💾 <b>Stability</b>: {len(agent.meta_agent.stacking.train_X)} samples"
                            )
                        agent.send_telegram(v_msg)

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
                        with agent.lock:
                            for name, acc_deque in agent.meta_agent.agent_acc.items():
                                if len(acc_deque) >= 5:
                                    acc = sum(acc_deque) / len(acc_deque)
                                    stats_list.append((name, acc, len(acc_deque)))
                                else:
                                    stats_list.append((name, 0, len(acc_deque)))
                            active_set = set(agent.meta_agent.active_agents)

                        stats_list.sort(key=lambda x: x[1], reverse=True)
                        for name, acc, n in stats_list:
                            status = "✅" if name in active_set else "⏸️"
                            if n >= 5:
                                msg_text += f"{status} <b>{name}</b>: {acc:.1%} (n={n})\n"
                            else:
                                msg_text += f"{status} {name}: warming ({n})\n"
                        agent.send_telegram(msg_text)

                    elif text == "/profit":
                        with agent.lock:
                            p_msg = (
                                f"💰 <b>PROFIT</b>\n\n"
                                f"💵 Net: <b>{agent.current_profit:+,.0f}</b>\n"
                                f"📈 Total Profit: <b>+{agent.total_profit:,.0f}</b>\n"
                                f"📉 Total Loss: <b>-{agent.total_loss_amount:,.0f}</b>\n"
                                f"🏆 Max Level: <b>{agent.max_level_reached}</b>\n"
                                f"📉 Max DD: <b>{agent.max_loss_amount:,.0f}</b>"
                            )
                        agent.send_telegram(p_msg)

                    elif text == "/help":
                        agent.send_telegram(
                            f"📚 <b>V20.6 FINAL COMMANDS</b>\n\n"
                            f"/status — Bot Status\n"
                            f"/v206 — Methods Status\n"
                            f"/agent_stats — Agent Performance\n"
                            f"/profit — Profit Stats\n"
                            f"/reset — Manual Reset\n"
                            f"/help — Commands"
                        )
            else:
                error_count += 1
                if error_count > 5:
                    time.sleep(5)
                    error_count = 0
        except Exception as e:
            print(f"TG Poll Error: {e}", flush=True)
            error_count += 1
            if error_count > 5:
                time.sleep(5)
                error_count = 0
        time.sleep(1)


# ==========================================
# API POLLER
# ==========================================
def run_bot():
    print("🚀 V20.6 FINAL — All 14 Bugs Fixed", flush=True)
    agent = V20Engine()
    threading.Thread(target=poll_telegram, args=(agent,), daemon=True).start()

    last_processed_period = None
    is_first_poll = True
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

            sorted_data = sorted(data, key=lambda x: int(x.get("issueNumber", 0)))

            if is_first_poll:
                print(f"🔥 Warm-up: {len(sorted_data)} periods", flush=True)
                for item in sorted_data:
                    period = str(item.get("issueNumber"))
                    num = int(item.get("number"))
                    result = "Big" if num >= 5 else "Small"
                    agent.process_api_result(period, result, num, is_warmup=True)
                last_processed_period = sorted_data[-1].get("issueNumber")
                agent.is_warmup = False
                is_first_poll = False
            else:
                for item in sorted_data:
                    period = str(item.get("issueNumber"))
                    num = int(item.get("number"))
                    result = "Big" if num >= 5 else "Small"
                    if period != last_processed_period:
                        last_processed_period = period
                        print(f"📥 Period {period} → {result} ({num})", flush=True)
                        notifications = agent.process_api_result(period, result, num)
                        if notifications:
                            for msg in notifications:
                                agent.send_telegram(msg)
                                time.sleep(0.1)
        except Exception as e:
            print(f"Poll Error: {e}", flush=True)
        time.sleep(1.2)


# ==========================================
# 🌐 FLASK
# ==========================================
@app.route('/')
def home():
    if not global_agent:
        return "<h3>🚀 V20.6 FINAL starting...</h3>"
    a = global_agent
    with a.lock:
        bet_amount, bet_type = a.get_current_bet()
        return f"""
        <h2>🚀 V20.6 FINAL</h2>
        <p><b>🔥 Warm-up:</b> {'YES' if a.is_warmup else 'DONE'}</p>
        <p><b>🎯 Regime:</b> {a.current_regime}</p>
        <p><b>🔄 BOCPD CPs:</b> {a.bocpd.changepoints_detected}</p>
        <p><b>📊 CUSUM Alarms:</b> {a.cusum.alarms}</p>
        <p><b>📈 Survival Streaks:</b> {len(a.survival.streaks)}</p>
        <p><b>🎯 Kalman P(Big):</b> {a.kalman.x:.3f}</p>
        <p><b>📚 Stacking:</b> {'Trained' if a.meta_agent.stacking.trained else 'Warming'}</p>
        <p><b>🌊 Online:</b> {a.meta_agent.online_learner.update_count}</p>
        <p><b>🔎 Adversarial:</b> {'Baseline Frozen' if a.adversarial.baseline_frozen else 'Warming'}</p>
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
        with a.lock:
            bet_amount, _ = a.get_current_bet()
            return {
                "version": "V20.6.1 FIXED",
                "warmup": a.is_warmup,
                "regime_hmm": a.current_regime,
                "hmm_trained": a.hmm_detector.trained,
                "bocpd_changepoints": a.bocpd.changepoints_detected,
                "cusum_alarms": a.cusum.alarms,
                "survival_streaks": len(a.survival.streaks),
                "kalman_p_big": round(a.kalman.x, 3),
                "stacking_trained": a.meta_agent.stacking.trained,
                "stacking_samples": len(a.meta_agent.stacking.train_X),
                "online_updates": a.meta_agent.online_learner.update_count,
                "online_scaler_fitted": a.meta_agent.online_learner.scaler_fitted,
                "adversarial_frozen": a.adversarial.baseline_frozen,
                "adversarial_auc": round(a.adversarial.auc_estimate, 3),
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
            }
    return {"status": "initializing"}

@app.route('/health')
def health():
    return {"status": "ok", "version": "V20.6.1 FIXED"}


# ==========================================
# 🚀 ENTRY
# ==========================================
if __name__ == "__main__":
    threading.Thread(target=run_bot, daemon=True).start()
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port) 
