#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
HYBRID V8.2 — High Frequency & High Precision Engine
- Multi-Dimension Signals: Big/Small & Odd/Even dual engine.
- Dynamic Regime Switching: Adapts weights based on market regimes instead of hard-blocking.
- Family Consensus (Voting): Statistical, Memory, and Streak families vote; 2/3 agreement passes signals.
- Independent Step Handling: Constant grade requirements across all steps (No high-step lockout).
- Anti-Trap Engine: Detects extended chop/alternating traps.
- SQLite Database + Telegram Bot + Flask Realtime Dashboard.
"""

import os
import time
import math
import json
import sqlite3
import threading
from collections import Counter, defaultdict, deque
from datetime import datetime, timezone
import requests
from flask import Flask, jsonify, render_template_string

# ============================================================
# CONFIGURATION
# ============================================================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
CHAT_ID = os.getenv("CHAT_ID", "")

API_URL = os.getenv("RESULT_API_URL", "https://6lotteryapi.com/api/webapi/GetNoaverageEmerdList")
API_AUTH = os.getenv("RESULT_API_AUTH", "")
API_ORIGIN = os.getenv("API_ORIGIN", "https://6win598.com")
API_REFERER = os.getenv("API_REFERER", "https://6win598.com/")
API_RANDOM = os.getenv("API_RANDOM", "")
API_SIGNATURE = os.getenv("API_SIGNATURE", "")

API_TYPE_ID = int(os.getenv("API_TYPE_ID", "30"))
API_LANGUAGE = int(os.getenv("API_LANGUAGE", "7"))
PERIOD_OFFSET = int(os.getenv("PERIOD_OFFSET", "2"))
POLL_SECONDS = float(os.getenv("POLL_SECONDS", "2.0"))
REQUEST_TIMEOUT = float(os.getenv("REQUEST_TIMEOUT", "10"))

DB_PATH = os.getenv("DB_PATH", "hybrid_v8.db")
MIN_HISTORY = int(os.getenv("MIN_HISTORY", "30"))
MAX_HISTORY = int(os.getenv("MAX_HISTORY", "1000"))

MIN_SIGNAL_PROB = float(os.getenv("MIN_SIGNAL_PROB", "0.57"))
MIN_EDGE = float(os.getenv("MIN_EDGE", "0.07"))
MAX_MODEL_DISAGREEMENT = float(os.getenv("MAX_MODEL_DISAGREEMENT", "0.38"))
MIN_Z_SCORE = float(os.getenv("MIN_Z_SCORE", "1.645"))  # 90% Statistical confidence

CALIBRATION_MIN_SAMPLES = int(os.getenv("CALIBRATION_MIN_SAMPLES", "12"))
PORT = int(os.getenv("PORT", "8080"))

# Grade Thresholds (Allows Grade B, A, A+ consistently across all steps)
GRADE_A_PLUS = float(os.getenv("GRADE_A_PLUS", "0.76"))
GRADE_A      = float(os.getenv("GRADE_A",      "0.64"))
GRADE_B      = float(os.getenv("GRADE_B",      "0.53"))
MIN_GRADE    = os.getenv("MIN_GRADE", "B")  # B, A, A+ all eligible

app = Flask(__name__)
global_agent = None


# ============================================================
# HELPER FUNCTIONS
# ============================================================
def number_to_result(number):
    try:
        n = int(number)
    except (TypeError, ValueError):
        return None
    if 0 <= n <= 4:
        return "Small"
    if 5 <= n <= 9:
        return "Big"
    return None

def number_to_odd_even(number):
    try:
        n = int(number)
    except (TypeError, ValueError):
        return None
    return "Even" if n % 2 == 0 else "Odd"

def clamp(value, lo, hi):
    return max(lo, min(hi, value))

def utc_now():
    return datetime.now(timezone.utc).isoformat()

def calculate_z_score(successes, trials, p=0.5):
    if trials <= 0:
        return 0.0
    expected = trials * p
    std_dev = math.sqrt(trials * p * (1.0 - p))
    if std_dev == 0:
        return 0.0
    return (successes - expected) / std_dev

def entropy_binary(arr, val1):
    if not arr:
        return 0.0
    c = sum(1 for x in arr if x == val1)
    p = c / len(arr)
    q = 1.0 - p
    h = 0.0
    if p > 0: h -= p * math.log2(p)
    if q > 0: h -= q * math.log2(q)
    return clamp(h, 0.0, 1.0)

def transition_rate(arr):
    if len(arr) < 2:
        return 0.0
    return sum(arr[i] != arr[i - 1] for i in range(1, len(arr))) / (len(arr) - 1)

def current_streak(arr):
    if not arr:
        return 0, None
    last = arr[-1]
    count = 0
    for x in reversed(arr):
        if x != last:
            break
        count += 1
    return count, last


# ============================================================
# DATABASE ENGINE
# ============================================================
class DataEngine:
    def __init__(self, path=DB_PATH):
        self.path = path
        self.conn = sqlite3.connect(self.path, check_same_thread=False)
        self.lock = threading.Lock()
        self._init_db()

    def _init_db(self):
        with self.lock:
            cur = self.conn.cursor()
            cur.execute("""
                CREATE TABLE IF NOT EXISTS history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    period TEXT UNIQUE NOT NULL,
                    number INTEGER NOT NULL,
                    result TEXT NOT NULL,
                    odd_even TEXT,
                    timestamp TEXT NOT NULL
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS predictions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    source_period TEXT,
                    target_period TEXT,
                    dimension TEXT,
                    prediction TEXT,
                    probability REAL,
                    edge REAL,
                    reason TEXT,
                    regime TEXT,
                    grade TEXT,
                    grade_score REAL,
                    evaluated INTEGER DEFAULT 0,
                    actual TEXT,
                    correct INTEGER
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS pattern_stats (
                    name TEXT PRIMARY KEY,
                    total INTEGER DEFAULT 0,
                    wins INTEGER DEFAULT 0,
                    recent_json TEXT,
                    updated_at TEXT
                )
            """)
            self.conn.commit()

    def save_result(self, period, number, result, odd_even):
        with self.lock:
            self.conn.execute("""
                INSERT OR IGNORE INTO history (period, number, result, odd_even, timestamp)
                VALUES (?, ?, ?, ?, ?)
            """, (str(period), int(number), result, odd_even, utc_now()))
            self.conn.commit()

    def has_period(self, period):
        with self.lock:
            row = self.conn.execute(
                "SELECT 1 FROM history WHERE period = ? LIMIT 1", (str(period),)
            ).fetchone()
            return row is not None

    def get_history_all(self, limit=MAX_HISTORY):
        with self.lock:
            rows = self.conn.execute("""
                SELECT result, odd_even, number FROM history ORDER BY id DESC LIMIT ?
            """, (int(limit),)).fetchall()
            results = [r[0] for r in reversed(rows)]
            odd_evens = [r[1] for r in reversed(rows)]
            numbers = [r[2] for r in reversed(rows)]
            return results, odd_evens, numbers

    def save_prediction(self, p):
        with self.lock:
            cur = self.conn.execute("""
                INSERT INTO predictions (
                    created_at, source_period, target_period, dimension,
                    prediction, probability, edge, reason, regime, grade, grade_score
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                utc_now(), p.get("source_period"), p.get("target_period"),
                p.get("dimension"), p.get("prediction"), p.get("probability", 0),
                p.get("edge", 0), p.get("reason", ""), p.get("regime", ""),
                p.get("grade", ""), p.get("grade_score", 0)
            ))
            self.conn.commit()
            return cur.lastrowid

    def evaluate_prediction(self, prediction_id, actual):
        with self.lock:
            row = self.conn.execute(
                "SELECT prediction FROM predictions WHERE id = ?", (prediction_id,)
            ).fetchone()
            if not row:
                return None
            correct = int(row[0] == actual)
            self.conn.execute("""
                UPDATE predictions SET evaluated = 1, actual = ?, correct = ? WHERE id = ?
            """, (actual, correct, prediction_id))
            self.conn.commit()
            return bool(correct)

    def save_pattern_stats(self, name, total, wins, recent):
        with self.lock:
            self.conn.execute("""
                INSERT INTO pattern_stats (name, total, wins, recent_json, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(name) DO UPDATE SET
                    total=excluded.total, wins=excluded.wins,
                    recent_json=excluded.recent_json, updated_at=excluded.updated_at
            """, (name, total, wins, json.dumps(list(recent)), utc_now()))
            self.conn.commit()

    def load_pattern_stats(self):
        with self.lock:
            rows = self.conn.execute("SELECT name, total, wins, recent_json FROM pattern_stats").fetchall()
            out = {}
            for name, total, wins, recent_json in rows:
                try: recent = json.loads(recent_json or "[]")
                except Exception: recent = []
                out[name] = {"total": int(total), "wins": int(wins), "recent": recent}
            return out


# ============================================================
# PATTERN TRACKER
# ============================================================
class PatternTracker:
    def __init__(self, db):
        self.db = db
        self.total = defaultdict(int)
        self.wins = defaultdict(int)
        self.recent = defaultdict(lambda: deque(maxlen=50))
        saved = db.load_pattern_stats()
        for name, item in saved.items():
            self.total[name] = item["total"]
            self.wins[name] = item["wins"]
            self.recent[name].extend(item["recent"][-50:])

    def update(self, name, predicted, actual):
        self.total[name] += 1
        correct = (predicted == actual)
        if correct: self.wins[name] += 1
        self.recent[name].append(1 if correct else 0)
        self.db.save_pattern_stats(name, self.total[name], self.wins[name], self.recent[name])

    def score(self, name):
        n = self.total[name]
        if n == 0: return 1.0
        posterior = (self.wins[name] + 10.0) / (n + 20.0)
        recent_data = list(self.recent[name])
        recent_wr = sum(recent_data) / len(recent_data) if recent_data else 0.5
        blended = posterior * 0.65 + recent_wr * 0.35
        return clamp(0.70 + (blended - 0.5) * 2.0, 0.50, 1.40)


# ============================================================
# REGIME DETECTOR (Anti-Trap Detection)
# ============================================================
class RegimeDetector:
    def detect(self, arr, val1):
        if len(arr) < 18:
            return {"name": "BALANCED", "entropy": entropy_binary(arr, val1), "is_trap": False}

        recent20 = arr[-20:]
        recent8 = arr[-8:]
        ent = entropy_binary(recent20, val1)
        trans = transition_rate(recent20)
        trans8 = transition_rate(recent8)
        streak_len, _ = current_streak(arr)
        bias = recent20.count(val1) / len(recent20)

        # Anti-trap: High alternating cycles >= 7 turns
        if trans8 >= 0.875 and streak_len == 1:
            return {"name": "EXTENDED_ALTERNATING_TRAP", "entropy": ent, "is_trap": True}

        if trans >= 0.80:   return {"name": "ALTERNATING", "entropy": ent, "is_trap": False}
        if streak_len >= 5: return {"name": "LONG_STREAK", "entropy": ent, "is_trap": False}
        if bias >= 0.75:    return {"name": "HIGH_BIAS", "entropy": ent, "is_trap": False}
        if bias <= 0.25:    return {"name": "LOW_BIAS", "entropy": ent, "is_trap": False}
        if trans >= 0.65:   return {"name": "FAST_SWITCH", "entropy": ent, "is_trap": False}
        if ent < 0.45:      return {"name": "CHAOTIC", "entropy": ent, "is_trap": False}
        return {"name": "BALANCED", "entropy": ent, "is_trap": False}


# ============================================================
# UNIVERSAL PATTERN ENGINE (Big/Small & Odd/Even)
# ============================================================
class UniversalPatternEngine:
    def predict(self, arr, regime, v1, v2, nums=None):
        models = {}
        # 1. Statistical Family
        m = self.freq_zscore(arr, v1, v2)
        if m: models[m["name"]] = m

        m = self.recent_zscore(arr, v1, v2)
        if m: models[m["name"]] = m

        if nums and v1 == "Big":
            m = self.ma_momentum(nums)
            if m: models[m["name"]] = m

        # 2. Memory / Markov Family
        m = self.markov2(arr, v1, v2)
        if m: models[m["name"]] = m

        m = self.markov3(arr, v1, v2)
        if m: models[m["name"]] = m

        m = self.mirror3(arr, v1, v2)
        if m: models[m["name"]] = m

        # 3. Streak / Sequence Family
        m = self.streak_continue(arr, regime)
        if m: models[m["name"]] = m

        m = self.streak_reversal(arr, regime, v1, v2)
        if m: models[m["name"]] = m

        m = self.alternating(arr, regime, v1, v2)
        if m: models[m["name"]] = m

        return models

    def freq_zscore(self, arr, v1, v2):
        if len(arr) < 22: return None
        sub = arr[-24:]
        z = calculate_z_score(sub.count(v1), len(sub), 0.5)
        if abs(z) < MIN_Z_SCORE: return None
        return {
            "name": "freq_zscore", "family": "STATISTICAL",
            "signal": v1 if z > 0 else v2,
            "probability": clamp(0.50 + abs(z) * 0.08, 0.54, 0.80),
            "support": len(sub)
        }

    def recent_zscore(self, arr, v1, v2):
        if len(arr) < 12: return None
        sub = arr[-12:]
        z = calculate_z_score(sub.count(v1), len(sub), 0.5)
        if abs(z) < 1.45: return None
        return {
            "name": "recent_zscore", "family": "STATISTICAL",
            "signal": v1 if z > 0 else v2,
            "probability": clamp(0.50 + abs(z) * 0.09, 0.52, 0.77),
            "support": len(sub)
        }

    def ma_momentum(self, nums):
        if len(nums) < 12: return None
        sub = nums[-12:]
        avg = sum(sub) / len(sub)
        if avg >= 5.75:
            return {"name": "ma_momentum", "family": "STATISTICAL", "signal": "Big",
                    "probability": clamp(0.50 + (avg - 5.0) * 0.18, 0.53, 0.76), "support": 12}
        elif avg <= 4.25:
            return {"name": "ma_momentum", "family": "STATISTICAL", "signal": "Small",
                    "probability": clamp(0.50 + (5.0 - avg) * 0.18, 0.53, 0.76), "support": 12}
        return None

    def markov2(self, arr, v1, v2):
        if len(arr) < 25: return None
        ctx = tuple(arr[-2:])
        foll = [arr[i + 2] for i in range(len(arr) - 2) if tuple(arr[i:i + 2]) == ctx]
        if len(foll) < 4: return None
        p_v1 = foll.count(v1) / len(foll)
        sig = v1 if p_v1 >= 0.5 else v2
        p = max(p_v1, 1.0 - p_v1)
        if p < 0.56: return None
        return {"name": "markov2", "family": "MEMORY", "signal": sig,
                "probability": clamp(p, 0.50, 0.85), "support": len(foll)}

    def markov3(self, arr, v1, v2):
        if len(arr) < 32: return None
        ctx = tuple(arr[-3:])
        foll = [arr[i + 3] for i in range(len(arr) - 3) if tuple(arr[i:i + 3]) == ctx]
        if len(foll) < 4: return None
        p_v1 = foll.count(v1) / len(foll)
        sig = v1 if p_v1 >= 0.5 else v2
        p = max(p_v1, 1.0 - p_v1)
        if p < 0.58: return None
        return {"name": "markov3", "family": "MEMORY", "signal": sig,
                "probability": clamp(p, 0.50, 0.88), "support": len(foll)}

    def mirror3(self, arr, v1, v2):
        if len(arr) < 18: return None
        ctx = tuple(arr[-3:])
        matches = [arr[i + 3] for i in range(len(arr) - 4) if tuple(arr[i:i + 3]) == ctx]
        if len(matches) < 3: return None
        counts = Counter(matches)
        win, cnt = counts.most_common(1)[0]
        p = cnt / len(matches)
        if p < 0.60: return None
        return {"name": "mirror3", "family": "MEMORY", "signal": win,
                "probability": clamp(p, 0.50, 0.78), "support": len(matches)}

    def streak_continue(self, arr, regime):
        if len(arr) < 6: return None
        streak, last = current_streak(arr)
        if streak < 3: return None
        p = clamp(0.50 + min(streak, 8) * 0.03, 0.50, 0.72)
        return {"name": "streak_continue", "family": "STREAK", "signal": last,
                "probability": p, "support": streak}

    def streak_reversal(self, arr, regime, v1, v2):
        if len(arr) < 8: return None
        streak, last = current_streak(arr)
        if streak < 4: return None
        opp = v2 if last == v1 else v1
        p = clamp(0.50 + min(streak - 3, 5) * 0.035, 0.50, 0.70)
        return {"name": "streak_reversal", "family": "STREAK", "signal": opp,
                "probability": p, "support": streak}

    def alternating(self, arr, regime, v1, v2):
        if len(arr) < 6 or regime.get("is_trap"): return None
        sub = arr[-6:]
        rate = transition_rate(sub)
        if rate < 0.75: return None
        sig = v2 if arr[-1] == v1 else v1
        return {"name": "alternating", "family": "STREAK", "signal": sig,
                "probability": clamp(0.50 + (rate - 0.5) * 0.35, 0.52, 0.70), "support": 6}


# ============================================================
# EVIDENCE FUSION (Dynamic Regime Switching + Family Voting)
# ============================================================
class EvidenceFusion:
    def __init__(self, tracker):
        self.tracker = tracker

    def combine(self, models, regime, v1, v2):
        if not models:
            return None

        # Group by families for voting
        family_evidence = defaultdict(lambda: {v1: 0.0, v2: 0.0})
        total_evidence_v1 = 0.0
        total_evidence_v2 = 0.0

        for name, m in models.items():
            sig = m["signal"]
            prob = m["probability"]
            fam = m["family"]
            score = self.tracker.score(name)
            reg_mult = self.get_regime_multiplier(name, regime)
            weight = score * reg_mult
            signed = (prob - 0.5) * 2.0 * weight

            if sig == v1:
                family_evidence[fam][v1] += signed
                total_evidence_v1 += signed
            else:
                family_evidence[fam][v2] += signed
                total_evidence_v2 += signed

        # Determine overall prediction
        net = total_evidence_v1 - total_evidence_v2
        prediction = v1 if net >= 0 else v2
        raw_prob = clamp(0.50 + abs(net) / max(1.0, len(models)), 0.50, 0.95)

        # Family Voting (Consensus Check)
        family_votes = {}
        agreeing_families = 0
        for fam, votes in family_evidence.items():
            fam_winner = v1 if votes[v1] >= votes[v2] else v2
            family_votes[fam] = fam_winner
            if fam_winner == prediction:
                agreeing_families += 1

        consensus = (agreeing_families >= 2)

        signals = [m["signal"] for m in models.values()]
        agreement = sum(s == prediction for s in signals) / len(signals)
        disagreement = 1.0 - agreement

        return {
            "prediction": prediction,
            "raw_probability": raw_prob,
            "agreement": agreement,
            "disagreement": disagreement,
            "consensus": consensus,
            "agreeing_families": agreeing_families,
            "models": models
        }

    @staticmethod
    def get_regime_multiplier(model_name, regime):
        r = regime["name"]
        # Dynamic Regime Switching (Specialization multipliers)
        if r == "LONG_STREAK":
            if model_name == "streak_continue": return 1.35
            if model_name == "streak_reversal": return 0.50
        elif r in ("ALTERNATING", "FAST_SWITCH"):
            if model_name in ("alternating", "markov2"): return 1.30
            if model_name == "streak_continue": return 0.55
        elif r in ("HIGH_BIAS", "LOW_BIAS"):
            if "zscore" in model_name or model_name == "streak_continue": return 1.25
        elif r == "CHAOTIC":
            if "zscore" in model_name: return 1.20
            if "markov" in model_name: return 0.70
        return 1.0


# ============================================================
# GRADE CALCULATOR (Step-Independent Evaluation)
# ============================================================
class GradeCalculator:
    def calculate(self, prob, agreement, entropy):
        prob_score = clamp((prob - 0.5) * 4.0, 0.0, 1.0)
        agree_score = clamp(agreement, 0.0, 1.0)
        ent_score = clamp(1.0 - entropy, 0.0, 1.0)

        score = 0.45 * prob_score + 0.35 * agree_score + 0.20 * ent_score

        if score >= GRADE_A_PLUS: grade = "A+"
        elif score >= GRADE_A:    grade = "A"
        elif score >= GRADE_B:    grade = "B"
        elif score >= 0.44:       grade = "C"
        else:                     grade = "D"

        return {"grade": grade, "score": score}

    @staticmethod
    def passes(grade):
        order = {"A+": 5, "A": 4, "B": 3, "C": 2, "D": 1}
        return order.get(grade, 0) >= order.get(MIN_GRADE, 3)

    @staticmethod
    def emoji(grade):
        return {"A+": "🔥", "A": "⭐", "B": "✅", "C": "⚠️", "D": "🛑"}.get(grade, "❓")


# ============================================================
# MAIN AGENT (HYBRID V8.2)
# ============================================================
class HybridV8:
    def __init__(self):
        global global_agent
        global_agent = self

        self.db = DataEngine()
        res_history, oe_history, num_history = self.db.get_history_all(MAX_HISTORY)
        self.history_res = deque(res_history, maxlen=MAX_HISTORY)
        self.history_oe = deque(oe_history, maxlen=MAX_HISTORY)
        self.history_num = deque(num_history, maxlen=MAX_HISTORY)

        self.regime_detector = RegimeDetector()
        self.pattern_engine = UniversalPatternEngine()
        self.tracker = PatternTracker(self.db)
        self.fusion = EvidenceFusion(self.tracker)
        self.grader = GradeCalculator()

        self.lock = threading.RLock()
        self.active_prediction = None
        self.current_step = 0
        self.is_paused = False

        self.total_signals = 0
        self.total_skips = 0
        self.total_wins = 0
        self.total_losses = 0
        self.win_by_step = defaultdict(int)

        self.last_period = "None"
        self.last_number = None
        self.last_result = "None"
        self.last_signal = "None"
        self.last_dimension = "None"
        self.last_reason = "None"
        self.last_prob = 0.0
        self.last_grade = "None"

        print(f"🚀 HYBRID V8.2 active with {len(self.history_res)} historical records.", flush=True)

    def send_telegram(self, message):
        if not TELEGRAM_TOKEN or not CHAT_ID: return False
        try:
            r = requests.post(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                json={"chat_id": CHAT_ID, "text": message, "parse_mode": "HTML"},
                timeout=10
            )
            return r.ok
        except Exception:
            return False

    def evaluate_previous(self, actual_res, actual_oe, current_period):
        if not self.active_prediction:
            return None

        p = self.active_prediction
        dim = p["dimension"]
        predicted = p["prediction"]
        actual = actual_res if dim == "BIG_SMALL" else actual_oe
        correct = (predicted == actual)
        step = p["step"]
        grade = p.get("grade", "?")

        with self.lock:
            # Update pattern weights
            for m in p["models"].values():
                self.tracker.update(m["name"], m["signal"], actual)

            if correct:
                self.total_wins += 1
                self.win_by_step[step] += 1
                if p.get("db_id"):
                    self.db.evaluate_prediction(p["db_id"], actual)

                self.current_step = 0
                emoji = self.grader.emoji(grade)
                self.send_telegram(
                    f"✅ <b>WIN</b>\n"
                    f"🎯 {dim} → {actual} | {emoji} {grade}\n"
                    f"🔄 Step Reset → <b>Step 1</b>\n"
                    f"📊 Overall WR: {self.get_wr()*100:.1f}%"
                )
            else:
                self.total_losses += 1
                if p.get("db_id"):
                    self.db.evaluate_prediction(p["db_id"], actual)
                self.current_step += 1

            self.active_prediction = None
        return correct

    def generate(self, source_period):
        bs_arr = list(self.history_res)
        oe_arr = list(self.history_oe)
        num_arr = list(self.history_num)

        if len(bs_arr) < MIN_HISTORY:
            return {"signal": None, "reason": "WARMUP"}

        # 1. Evaluate Big / Small
        regime_bs = self.regime_detector.detect(bs_arr, "Big")
        models_bs = self.pattern_engine.predict(bs_arr, regime_bs, "Big", "Small", num_arr)
        fusion_bs = self.fusion.combine(models_bs, regime_bs, "Big", "Small") if models_bs else None

        # 2. Evaluate Odd / Even
        regime_oe = self.regime_detector.detect(oe_arr, "Odd")
        models_oe = self.pattern_engine.predict(oe_arr, regime_oe, "Odd", "Even")
        fusion_oe = self.fusion.combine(models_oe, regime_oe, "Odd", "Even") if models_oe else None

        # Pick Best Dimension based on consensus, edge, and probability
        candidate = self.select_best_dimension(fusion_bs, regime_bs, fusion_oe, regime_oe)
        if not candidate:
            return {"signal": None, "reason": "NO_QUALIFIED_EDGE"}

        dim, fusion, regime = candidate

        # Anti-trap filter
        if regime.get("is_trap"):
            return {"signal": None, "reason": "EXTENDED_ALTERNATING_TRAP"}

        prob = fusion["raw_probability"]
        edge = abs(prob - 0.5)

        # Filters: Consensus eases disagreement penalty
        disagree_limit = 0.42 if fusion["consensus"] else MAX_MODEL_DISAGREEMENT
        if fusion["disagreement"] > disagree_limit:
            return {"signal": None, "reason": "MODEL_DISAGREEMENT"}

        if prob < MIN_SIGNAL_PROB or edge < MIN_EDGE:
            return {"signal": None, "reason": "LOW_PROBABILITY"}

        # Grade Evaluation
        grade_res = self.grader.calculate(prob, fusion["agreement"], regime["entropy"])
        grade = grade_res["grade"]

        if not self.grader.passes(grade):
            return {"signal": None, "reason": f"LOW_GRADE_{grade}"}

        return {
            "dimension": dim,
            "signal": fusion["prediction"],
            "probability": prob,
            "edge": edge,
            "regime": regime["name"],
            "grade": grade,
            "grade_score": grade_res["score"],
            "consensus": fusion["consensus"],
            "models": fusion["models"],
            "source_period": str(source_period)
        }

    def select_best_dimension(self, f_bs, r_bs, f_oe, r_oe):
        # Rate candidate suitability
        candidates = []
        if f_bs and not r_bs.get("is_trap"):
            score_bs = f_bs["raw_probability"] + (0.05 if f_bs["consensus"] else 0.0)
            candidates.append(("BIG_SMALL", f_bs, r_bs, score_bs))
        if f_oe and not r_oe.get("is_trap"):
            score_oe = f_oe["raw_probability"] + (0.05 if f_oe["consensus"] else 0.0)
            candidates.append(("ODD_EVEN", f_oe, r_oe, score_oe))

        if not candidates:
            return None
        candidates.sort(key=lambda x: x[3], reverse=True)
        best = candidates[0]
        return best[0], best[1], best[2]

    def analyze_round(self, period, number):
        res = number_to_result(number)
        oe = number_to_odd_even(number)
        if res is None or oe is None: return

        with self.lock:
            if self.db.has_period(period): return

            self.evaluate_previous(res, oe, str(period))
            self.db.save_result(period, number, res, oe)
            self.history_res.append(res)
            self.history_oe.append(oe)
            self.history_num.append(int(number))

            self.last_period = str(period)
            self.last_number = int(number)
            self.last_result = f"{res} ({oe})"

            if self.is_paused:
                self.last_signal = "PAUSED"
                return

            pred = self.generate(period)
            if pred["signal"] is None:
                self.total_skips += 1
                self.last_signal = "SKIP"
                self.last_reason = pred["reason"]
                self.send_telegram(f"⏸️ <b>SKIP</b>\n📅 {period}\n📌 {pred['reason']}")
                return

            self.total_signals += 1
            target_period = str(int(str(period)) + 1)

            record = {
                "source_period": str(period),
                "target_period": target_period,
                "dimension": pred["dimension"],
                "prediction": pred["signal"],
                "probability": pred["probability"],
                "edge": pred["edge"],
                "reason": f"CONSENSUS_{pred['consensus']}",
                "regime": pred["regime"],
                "grade": pred["grade"],
                "grade_score": pred["grade_score"],
                "models": pred["models"]
            }

            db_id = self.db.save_prediction(record)
            self.active_prediction = {**record, "db_id": db_id, "step": self.current_step}

            self.last_dimension = pred["dimension"]
            self.last_signal = pred["signal"]
            self.last_prob = pred["probability"]
            self.last_grade = pred["grade"]

            grade_emoji = self.grader.emoji(pred["grade"])
            dim_tag = "🎯 [BIG/SMALL]" if pred["dimension"] == "BIG_SMALL" else "🎲 [ODD/EVEN]"

            self.send_telegram(
                f"{dim_tag} <b>{pred['signal'].upper()}</b>\n"
                f"{grade_emoji} <b>Grade: {pred['grade']}</b> ({pred['grade_score']:.2f})\n\n"
                f"📅 Period: {period}\n"
                f"💰 Step {self.current_step + 1} ({2**self.current_step}x)\n"
                f"📊 Prob: {pred['probability']*100:.1f}% | Edge: {pred['edge']*100:.1f}pp\n"
                f"🧠 Regime: {pred['regime']} (Consensus: {'✅' if pred['consensus'] else '⚠️'})"
            )

    def get_wr(self):
        tot = self.total_wins + self.total_losses
        return self.total_wins / tot if tot else 0.0

    def dashboard_state(self):
        return {
            "version": "HYBRID V8.2",
            "history": len(self.history_res),
            "signals": self.total_signals,
            "skips": self.total_skips,
            "wins": self.total_wins,
            "losses": self.total_losses,
            "wr": self.get_wr(),
            "step": self.current_step + 1,
            "paused": self.is_paused,
            "last_period": self.last_period,
            "last_result": self.last_result,
            "last_dimension": self.last_dimension,
            "last_signal": self.last_signal,
            "last_prob": self.last_prob,
            "last_grade": self.last_grade
        }


# ============================================================
# TELEGRAM COMMAND LOOP
# ============================================================
def poll_telegram(agent):
    if not TELEGRAM_TOKEN or not CHAT_ID: return
    offset = 0
    while True:
        try:
            r = requests.get(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates",
                params={"offset": offset, "timeout": 20}, timeout=25
            )
            if r.status_code == 200:
                for u in r.json().get("result", []):
                    offset = u["update_id"] + 1
                    msg = u.get("message") or {}
                    if str(msg.get("chat", {}).get("id")) != str(CHAT_ID): continue
                    txt = str(msg.get("text", "")).strip().lower()

                    if txt == "/status":
                        s = agent.dashboard_state()
                        agent.send_telegram(
                            f"🚀 <b>HYBRID V8.2 STATUS</b>\n\n"
                            f"Mode: {'PAUSED 🛑' if s['paused'] else 'RUNNING 🟢'}\n"
                            f"WR: <b>{s['wr']*100:.2f}%</b> (W: {s['wins']} | L: {s['losses']})\n"
                            f"Signals: {s['signals']} | Skips: {s['skips']}\n"
                            f"Current Step: <b>Step {s['step']}</b>\n"
                            f"Last: {s['last_dimension']} → {s['last_signal']} ({s['last_grade']})"
                        )
                    elif txt == "/pause":
                        agent.is_paused = True
                        agent.send_telegram("🛑 Paused")
                    elif txt == "/resume":
                        agent.is_paused = False
                        agent.send_telegram("🟢 Resumed")
                    elif txt == "/reset":
                        agent.current_step = 0
                        agent.send_telegram("🔄 Step Reset → 1")
        except Exception:
            pass
        time.sleep(1)


# ============================================================
# API CLIENT & BACKGROUND WORKER
# ============================================================
class ResultAPIClient:
    def __init__(self):
        self.session = requests.Session()

    def fetch_latest(self):
        headers = {
            "accept": "application/json, text/plain, */*",
            "content-type": "application/json;charset=UTF-8",
            "user-agent": "Mozilla/5.0",
        }
        if API_AUTH: headers["authorization"] = f"Bearer {API_AUTH}"
        if API_ORIGIN: headers["origin"] = API_ORIGIN
        if API_REFERER: headers["referer"] = API_REFERER

        payload = {
            "pageSize": 10, "pageNo": 1, "typeId": API_TYPE_ID,
            "language": API_LANGUAGE, "timestamp": int(time.time()),
        }
        if API_RANDOM: payload["random"] = API_RANDOM
        if API_SIGNATURE: payload["signature"] = API_SIGNATURE

        r = self.session.post(API_URL, headers=headers, json=payload, timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
        items = r.json().get("data", {}).get("list", [])
        if not items: return None
        latest = items[0]
        raw_period = latest.get("issueNumber") or latest.get("period")
        raw_number = latest.get("number")
        if raw_period is None or raw_number is None: return None
        return {"period": str(int(str(raw_period)) + PERIOD_OFFSET), "number": int(raw_number)}


def run_bot():
    print("🚀 Starting HYBRID V8.2...", flush=True)
    agent = HybridV8()
    api = ResultAPIClient()
    threading.Thread(target=poll_telegram, args=(agent,), daemon=True).start()

    last_period = None
    while True:
        try:
            item = api.fetch_latest()
            if item and item["period"] != last_period:
                last_period = item["period"]
                print(f"📡 Sync {item['period']} → {item['number']}", flush=True)
                agent.analyze_round(item["period"], item["number"])
        except Exception as e:
            print(f"⚠️ API Polling error: {e}", flush=True)
        time.sleep(POLL_SECONDS)


# ============================================================
# DASHBOARD
# ============================================================
HTML = r"""
<!doctype html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="refresh" content="10">
<title>HYBRID V8.2</title>
<style>
body { margin:0; background:#0b1020; color:#e9f0ff; font-family:system-ui,Arial,sans-serif; padding:14px; }
h1 { color:#00ffff; margin-bottom:4px; }
.card { background:#151d33; border:1px solid #2b3858; border-radius:12px; padding:14px; margin:10px 0; }
.grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(160px,1fr)); gap:10px; }
.val { font-size:26px; font-weight:bold; }
.green { color:#00ff88; } .cyan { color:#00ffff; } .yellow { color:#ffe600; }
</style>
</head>
<body>
<h1>🚀 HYBRID V8.2 Engine</h1>
<div>Multi-Dimension (Big/Small & Odd/Even) + Consensus Voting</div>
{% if agent %}
<div class="grid">
  <div class="card"><div>Mode</div><div class="val">{{ "PAUSED 🛑" if agent.is_paused else "RUNNING 🟢" }}</div></div>
  <div class="card"><div>Win Rate</div><div class="val green">{{ "%.2f"|format(agent.get_wr()*100) }}%</div></div>
  <div class="card"><div>Signals/Skips</div><div class="val">{{ agent.total_signals }} / {{ agent.total_skips }}</div></div>
  <div class="card"><div>Current Step</div><div class="val yellow">Step {{ agent.current_step + 1 }}</div></div>
</div>
<div class="card">
  <h2>🎯 Last Signal Summary</h2>
  <p>Period: <b>{{ agent.last_period }}</b> | Result: <b>{{ agent.last_result }}</b></p>
  <p>Target: <b class="cyan">{{ agent.last_dimension }}</b> → <b class="green">{{ agent.last_signal }}</b></p>
  <p>Grade: <b>{{ agent.last_grade }}</b> | Prob: <b>{{ "%.1f"|format(agent.last_prob*100) }}%</b></p>
</div>
{% endif %}
</body>
</html>
"""

@app.route("/")
def home():
    return render_template_string(HTML, agent=global_agent)

@app.route("/api/status")
def api_status():
    if not global_agent: return jsonify({"status": "starting"})
    return jsonify(global_agent.dashboard_state())

if __name__ == "__main__":
    threading.Thread(target=run_bot, daemon=True).start()
    app.run(host="0.0.0.0", port=PORT, debug=False)
