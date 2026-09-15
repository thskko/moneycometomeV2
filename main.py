#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
HYBRID V6.1 (Unlimited Martingale)
Data-driven Big/Small signal engine + Telegram + Flask dashboard.
- No automatic betting execution.
- Step tracking display only (Unlimited steps, resets only on Win).
- Loss silent, Win shown.
- Configure secrets through environment variables.
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
# CONFIG
# ============================================================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "8913070806:AAF3rP0zKJtofE-5KVesqcdoHzn7Go0avho")
CHAT_ID = os.getenv("CHAT_ID", "-1004402480797")

API_URL = os.getenv(
    "RESULT_API_URL",
    "https://6lotteryapi.com/api/webapi/GetNoaverageEmerdList"
)
API_AUTH = os.getenv(
    "RESULT_API_AUTH",
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpYXQiOiIxNzg3OTgxNTA5IiwibmJmIjoiMTc4Nzk4MTUwOSIsImV4cCI6IjE3ODc5ODMzMDkiLCJodHRwOi8vc2NoZW1hcy5taWNyb3NvZnQuY29tL3dzLzIwMDgvMDYvaWRlbnRpdHkvY2xhaW1zL2V4cGlyYXRpb24iOiI4LzI5LzIwMjYgMTI6MzE2NDkgUE0iLCJodHRwOi8vc2NoZW1hcy5taWNyb3NvZnQuY29tL3dzLzIwMDgvMDYvaWRlbnRpdHkvY2xhaW1zL3JvbGUiOiJBY2Nlc3NfVG9rZW4iLCJVc2VySWQiOiIxMDEyMjEzIiwiVXNlck5hbWUiOiI5NTk3NDA5MzkzNzAiLCJVc2VyUGhvdG8iOiI5IiwiTmlja05hbWUiOiJUaGVrR3lpIiwiQW1vdW50IjoiODcuMzAiLCJJbnRlZ3JhbCI6IjAiLCJMb2dpbk1hcmsiOiJINSIsImxvZ2luVGltZSI6IjcvMjkvMjAyNiAxMjowMTo0OSBQTSIsImxvZ2luSVBBZGRyZXNzIjoiNDUuNDEuMTA0LjI0MCIsImRiTnVtYmVyIjoiMCIsIklzdmFsaWRhdG9yIjoiMCIsIktleUNvZGUiOiIzMjMzMiIsImRva2VuVHlwZSI6IjJBY2Nlc3NfVG9rZW4iLCJob25lVHlwZSI6IjAiLCJVc2VyVHlwZSI6IjAiLCJVc2VyTmFtZ2UiOiIuIiwiaXNzIjoiand0SXNzdWVyIiwiYXVkIjoibG90dGVyeVRpY2tldCJ9.ZL0Y9gexUTCsKwWeZhCLAAw8AABEYJt0GnIzIviMG4g"
)
API_ORIGIN = os.getenv("API_ORIGIN", "https://6win598.com")
API_REFERER = os.getenv("API_REFERER", "https://6win598.com/")

API_TYPE_ID = int(os.getenv("API_TYPE_ID", "30"))
API_LANGUAGE = int(os.getenv("API_LANGUAGE", "7"))
PERIOD_OFFSET = int(os.getenv("PERIOD_OFFSET", "2"))
POLL_SECONDS = float(os.getenv("POLL_SECONDS", "2.0"))
REQUEST_TIMEOUT = float(os.getenv("REQUEST_TIMEOUT", "10"))

DB_PATH = os.getenv("DB_PATH", "hybrid_v61.db")
MIN_HISTORY = int(os.getenv("MIN_HISTORY", "30"))
MAX_HISTORY = int(os.getenv("MAX_HISTORY", "1000"))

MIN_SIGNAL_PROB = float(os.getenv("MIN_SIGNAL_PROB", "0.58"))
MIN_EDGE = float(os.getenv("MIN_EDGE", "0.08"))
MAX_MODEL_DISAGREEMENT = float(os.getenv("MAX_MODEL_DISAGREEMENT", "0.35"))

RECENT_WINDOW = int(os.getenv("RECENT_WINDOW", "30"))
CALIBRATION_MIN_SAMPLES = int(os.getenv("CALIBRATION_MIN_SAMPLES", "12"))

BASE_BET = float(os.getenv("BASE_BET", "1.0"))
# STEP_CAP ဖယ်ရှားလိုက်ပါပြီ
PORT = int(os.getenv("PORT", "8080"))

API_RANDOM = os.getenv("API_RANDOM", "036263f367384d418be07465793c8da8")
API_SIGNATURE = os.getenv("API_SIGNATURE", "55F4FD150F15F090B943374F3C9BE78B")

app = Flask(__name__)
global_agent = None


# ============================================================
# HELPERS
# ============================================================
VALID_RESULTS = ("Big", "Small")

def number_to_result(number):
    try:
        n = int(number)
    except (TypeError, ValueError):
        return None
    if 1 <= n <= 4:
        return "Small"
    if 5 <= n <= 9:
        return "Big"
    return None

def result_to_bit(result):
    return 1 if result == "Big" else 0

def clamp(value, lo, hi):
    return max(lo, min(hi, value))

def utc_now():
    return datetime.now(timezone.utc).isoformat()

def entropy_binary(arr):
    if not arr:
        return 0.0
    b = sum(1 for x in arr if x == "Big")
    p = b / len(arr)
    q = 1.0 - p
    h = 0.0
    if p > 0:
        h -= p * math.log2(p)
    if q > 0:
        h -= q * math.log2(q)
    return clamp(h, 0.0, 1.0)

def transition_rate(arr):
    if len(arr) < 2:
        return 0.0
    return sum(
        arr[i] != arr[i - 1] for i in range(1, len(arr))
    ) / (len(arr) - 1)

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

def longest_streak(arr):
    best = 0
    best_result = None
    cur = 0
    prev = None
    for x in arr:
        if x == prev:
            cur += 1
        else:
            cur = 1
        prev = x
        if cur > best:
            best = cur
            best_result = x
    return best, best_result


# ============================================================
# DATABASE
# ============================================================
class DataEngine:
    def __init__(self, path=DB_PATH):
        self.path = path
        self.conn = sqlite3.connect(
            self.path, check_same_thread=False
        )
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
                    timestamp TEXT NOT NULL
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS predictions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    source_period TEXT,
                    target_period TEXT,
                    prediction TEXT,
                    probability REAL,
                    edge REAL,
                    reason TEXT,
                    regime TEXT,
                    entropy REAL,
                    transition_rate REAL,
                    models_json TEXT,
                    groups_json TEXT,
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
            cur.execute("""
                CREATE TABLE IF NOT EXISTS errors (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    source_period TEXT,
                    prediction TEXT,
                    actual TEXT,
                    regime TEXT,
                    models_json TEXT,
                    wrong_models_json TEXT,
                    correct_models_json TEXT
                )
            """)
            self.conn.commit()

    def save_result(self, period, number, result):
        with self.lock:
            self.conn.execute("""
                INSERT OR IGNORE INTO history
                (period, number, result, timestamp)
                VALUES (?, ?, ?, ?)
            """, (str(period), int(number), result, utc_now()))
            self.conn.commit()

    def has_period(self, period):
        with self.lock:
            row = self.conn.execute(
                "SELECT 1 FROM history WHERE period = ? LIMIT 1",
                (str(period),)
            ).fetchone()
            return row is not None

    def get_history(self, limit=MAX_HISTORY):
        with self.lock:
            rows = self.conn.execute("""
                SELECT result FROM history ORDER BY id DESC LIMIT ?
            """, (int(limit),)).fetchall()
            return [r[0] for r in reversed(rows)]

    def get_last_rows(self, limit=30):
        with self.lock:
            rows = self.conn.execute("""
                SELECT period, number, result, timestamp
                FROM history ORDER BY id DESC LIMIT ?
            """, (int(limit),)).fetchall()
            return [
                {"period": r[0], "number": r[1], "result": r[2], "timestamp": r[3]}
                for r in reversed(rows)
            ]

    def save_prediction(self, p):
        with self.lock:
            cur = self.conn.execute("""
                INSERT INTO predictions (
                    created_at, source_period, target_period,
                    prediction, probability, edge, reason, regime,
                    entropy, transition_rate, models_json, groups_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                utc_now(),
                p.get("source_period"),
                p.get("target_period"),
                p.get("prediction"),
                p.get("probability", 0),
                p.get("edge", 0),
                p.get("reason", ""),
                p.get("regime", ""),
                p.get("entropy", 0),
                p.get("transition_rate", 0),
                json.dumps(p.get("models", {}), ensure_ascii=False),
                json.dumps(p.get("groups", {}), ensure_ascii=False),
            ))
            self.conn.commit()
            return cur.lastrowid

    def evaluate_prediction(self, prediction_id, actual):
        with self.lock:
            row = self.conn.execute(
                "SELECT prediction FROM predictions WHERE id = ?",
                (prediction_id,)
            ).fetchone()
            if not row:
                return None
            predicted = row[0]
            correct = int(predicted == actual)
            self.conn.execute("""
                UPDATE predictions
                SET evaluated = 1, actual = ?, correct = ?
                WHERE id = ?
            """, (actual, correct, prediction_id))
            self.conn.commit()
            return bool(correct)

    def save_error(self, source_period, prediction, actual, regime,
                   models, wrong_models, correct_models):
        with self.lock:
            self.conn.execute("""
                INSERT INTO errors (
                    created_at, source_period, prediction, actual,
                    regime, models_json, wrong_models_json, correct_models_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                utc_now(), source_period, prediction, actual, regime,
                json.dumps(models, ensure_ascii=False),
                json.dumps(wrong_models, ensure_ascii=False),
                json.dumps(correct_models, ensure_ascii=False),
            ))
            self.conn.commit()

    def save_pattern_stats(self, name, total, wins, recent):
        with self.lock:
            self.conn.execute("""
                INSERT INTO pattern_stats
                (name, total, wins, recent_json, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(name) DO UPDATE SET
                    total=excluded.total,
                    wins=excluded.wins,
                    recent_json=excluded.recent_json,
                    updated_at=excluded.updated_at
            """, (name, total, wins, json.dumps(list(recent)), utc_now()))
            self.conn.commit()

    def load_pattern_stats(self):
        with self.lock:
            rows = self.conn.execute("""
                SELECT name, total, wins, recent_json FROM pattern_stats
            """).fetchall()
            out = {}
            for name, total, wins, recent_json in rows:
                try:
                    recent = json.loads(recent_json or "[]")
                except Exception:
                    recent = []
                out[name] = {"total": int(total), "wins": int(wins), "recent": recent}
            return out

    def stats(self):
        with self.lock:
            row = self.conn.execute("""
                SELECT COUNT(*), SUM(CASE WHEN correct=1 THEN 1 ELSE 0 END)
                FROM predictions WHERE evaluated=1
            """).fetchone()
            total = int(row[0] or 0)
            wins = int(row[1] or 0)
            return {
                "predictions": total,
                "wins": wins,
                "losses": total - wins,
                "wr": wins / total if total else 0.0,
            }


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
        correct = predicted == actual
        if correct:
            self.wins[name] += 1
        self.recent[name].append(1 if correct else 0)
        self.db.save_pattern_stats(
            name, self.total[name], self.wins[name], self.recent[name]
        )

    def reliability(self, name):
        n = self.total[name]
        if n == 0:
            return 0.5
        prior_n = 20
        posterior = (self.wins[name] + prior_n * 0.5) / (n + prior_n)
        return clamp(posterior, 0.35, 0.65)

    def recent_wr(self, name):
        data = list(self.recent[name])
        if not data:
            return 0.5
        return sum(data) / len(data)

    def sample_factor(self, name):
        n = self.total[name]
        return clamp(math.sqrt(n / 50.0), 0.25, 1.0)

    def score(self, name):
        rel = self.reliability(name)
        recent = self.recent_wr(name)
        sample = self.sample_factor(name)
        blended = rel * 0.70 + recent * 0.30
        multiplier = 0.75 + (blended - 0.5) * 2.0
        return clamp(
            1.0 + (multiplier - 1.0) * sample,
            0.65, 1.35
        )

    def all_stats(self):
        names = sorted(set(self.total) | set(self.recent))
        result = []
        for name in names:
            total = self.total[name]
            wins = self.wins[name]
            result.append({
                "name": name,
                "total": total,
                "wins": wins,
                "wr": wins / total if total else 0.0,
                "recent_wr": self.recent_wr(name),
                "reliability": self.reliability(name),
                "sample_factor": self.sample_factor(name),
                "score": self.score(name),
            })
        result.sort(key=lambda x: (x["wr"], x["total"]), reverse=True)
        return result


# ============================================================
# REGIME DETECTOR
# ============================================================
class RegimeDetector:
    def detect(self, arr):
        if len(arr) < 20:
            return {
                "name": "UNKNOWN",
                "confidence": 0.0,
                "entropy": entropy_binary(arr),
                "transition_rate": transition_rate(arr),
                "streak": current_streak(arr)[0],
                "bias": (arr.count("Big") / len(arr) if arr else 0.5),
            }
        recent20 = arr[-20:]
        recent10 = arr[-10:]
        ent = entropy_binary(recent20)
        trans = transition_rate(recent20)
        streak_len, streak_result = current_streak(arr)
        bias = recent20.count("Big") / 20

        if trans >= 0.80:
            return self._pack("ALTERNATING", 0.90, ent, trans, streak_len, bias)
        if streak_len >= 6:
            return self._pack("LONG_STREAK", min(0.95, 0.55 + streak_len * 0.05),
                              ent, trans, streak_len, bias)
        if bias >= 0.75:
            return self._pack("BIG_BIASED", 0.85, ent, trans, streak_len, bias)
        if bias <= 0.25:
            return self._pack("SMALL_BIASED", 0.85, ent, trans, streak_len, bias)
        if trans >= 0.65:
            return self._pack("FAST_SWITCH", 0.72, ent, trans, streak_len, bias)

        old10 = arr[-20:-10]
        old_bias = old10.count("Big") / 10
        new_bias = recent10.count("Big") / 10
        if abs(new_bias - old_bias) >= 0.50:
            return self._pack("TRANSITION", 0.82, ent, trans, streak_len, bias)
        if ent < 0.40:
            return self._pack("CHAOTIC", 0.75, ent, trans, streak_len, bias)
        if ent >= 0.72 and 0.35 <= trans <= 0.65:
            return self._pack("BALANCED", 0.70, ent, trans, streak_len, bias)
        if ent >= 0.62:
            return self._pack("TREND", 0.70, ent, trans, streak_len, bias)
        return self._pack("MIXED", 0.55, ent, trans, streak_len, bias)

    @staticmethod
    def _pack(name, confidence, ent, trans, streak, bias):
        return {
            "name": name,
            "confidence": confidence,
            "entropy": ent,
            "transition_rate": trans,
            "streak": streak,
            "bias": bias,
        }


# ============================================================
# PATTERN ENGINE
# ============================================================
class PatternEngine:
    def predict(self, arr, regime):
        models = {}
        methods = [
            self.markov_order2, self.markov_order3,
            self.frequency, self.recent_bias,
            self.transition, self.streak_continue,
            self.streak_reversal, self.alternating,
            self.mirror, self.sequence_repeat,
            self.run_length_context,
        ]
        for method in methods:
            result = method(arr, regime)
            if result:
                models[result["name"]] = result
        return models

    def markov_order2(self, arr, regime):
        if len(arr) < 25: return None
        order = 2
        context = tuple(arr[-order:])
        following = []
        for i in range(len(arr) - order):
            if tuple(arr[i:i + order]) == context:
                following.append(arr[i + order])
        if len(following) < 5: return None
        counts = Counter(following)
        total = sum(counts.values())
        p_big = counts["Big"] / total
        signal = "Big" if p_big >= 0.5 else "Small"
        p = max(p_big, 1 - p_big)
        return {
            "name": "markov2", "group": "markov",
            "signal": signal,
            "probability": clamp(p, 0.50, 0.85),
            "support": total,
            "metadata": {"p_big": p_big},
        }

    def markov_order3(self, arr, regime):
        if len(arr) < 35: return None
        order = 3
        context = tuple(arr[-order:])
        following = []
        for i in range(len(arr) - order):
            if tuple(arr[i:i + order]) == context:
                following.append(arr[i + order])
        if len(following) < 4: return None
        counts = Counter(following)
        total = sum(counts.values())
        p_big = counts["Big"] / total
        signal = "Big" if p_big >= 0.5 else "Small"
        p = max(p_big, 1 - p_big)
        return {
            "name": "markov3", "group": "markov",
            "signal": signal,
            "probability": clamp(p, 0.50, 0.88),
            "support": total,
            "metadata": {"p_big": p_big},
        }

    def frequency(self, arr, regime):
        if len(arr) < 20: return None
        sub = arr[-20:]
        p_big = sub.count("Big") / 20
        if p_big >= 0.65:
            return {
                "name": "frequency20", "group": "distribution",
                "signal": "Big",
                "probability": clamp(0.50 + abs(p_big - 0.5) * 0.65, 0.50, 0.78),
                "support": 20, "metadata": {"p_big": p_big},
            }
        if p_big <= 0.35:
            return {
                "name": "frequency20", "group": "distribution",
                "signal": "Small",
                "probability": clamp(0.50 + abs(p_big - 0.5) * 0.65, 0.50, 0.78),
                "support": 20, "metadata": {"p_big": p_big},
            }
        return None

    def recent_bias(self, arr, regime):
        if len(arr) < 10: return None
        sub = arr[-10:]
        p_big = sub.count("Big") / 10
        if p_big >= 0.70: signal = "Big"
        elif p_big <= 0.30: signal = "Small"
        else: return None
        p = 0.50 + abs(p_big - 0.5) * 0.55
        return {
            "name": "recent_bias10", "group": "distribution",
            "signal": signal,
            "probability": clamp(p, 0.50, 0.75),
            "support": 10, "metadata": {"p_big": p_big},
        }

    def transition(self, arr, regime):
        if len(arr) < 30: return None
        old = arr[-20:-10]
        new = arr[-10:]
        old_p = old.count("Big") / 10
        new_p = new.count("Big") / 10
        delta = new_p - old_p
        if delta >= 0.50:
            return {
                "name": "transition", "group": "transition",
                "signal": "Big",
                "probability": clamp(0.54 + delta * 0.35, 0.50, 0.72),
                "support": 20, "metadata": {"delta": delta},
            }
        if delta <= -0.50:
            return {
                "name": "transition", "group": "transition",
                "signal": "Small",
                "probability": clamp(0.54 + abs(delta) * 0.35, 0.50, 0.72),
                "support": 20, "metadata": {"delta": delta},
            }
        return None

    def streak_continue(self, arr, regime):
        if len(arr) < 8: return None
        streak, result = current_streak(arr)
        if streak < 4 or result not in VALID_RESULTS: return None
        if regime["name"] not in (
            "TREND", "LONG_STREAK", "BIG_BIASED", "SMALL_BIASED"
        ):
            return None
        p = clamp(0.50 + min(streak, 8) * 0.025, 0.50, 0.70)
        return {
            "name": "streak_continue", "group": "streak",
            "signal": result,
            "probability": p,
            "support": streak,
            "metadata": {"streak": streak},
        }

    def streak_reversal(self, arr, regime):
        if len(arr) < 8: return None
        streak, result = current_streak(arr)
        if streak < 4: return None
        opposite = "Small" if result == "Big" else "Big"
        if regime["name"] in ("LONG_STREAK", "BIG_BIASED", "SMALL_BIASED"):
            p = clamp(0.50 + min(streak - 3, 6) * 0.035, 0.50, 0.70)
            return {
                "name": "streak_reversal", "group": "streak",
                "signal": opposite,
                "probability": p,
                "support": streak,
                "metadata": {"streak": streak},
            }
        return None

    def alternating(self, arr, regime):
        if len(arr) < 8: return None
        sub = arr[-8:]
        rate = transition_rate(sub)
        if rate < 0.75: return None
        signal = "Small" if arr[-1] == "Big" else "Big"
        return {
            "name": "alternating", "group": "sequence",
            "signal": signal,
            "probability": clamp(0.50 + (rate - 0.50) * 0.35, 0.50, 0.68),
            "support": 8, "metadata": {"transition_rate": rate},
        }

    def mirror(self, arr, regime):
        if len(arr) < 16: return None
        context = tuple(arr[-3:])
        matches = []
        for i in range(len(arr) - 4):
            if tuple(arr[i:i + 3]) == context:
                matches.append(arr[i + 3])
        if len(matches) < 4: return None
        counts = Counter(matches)
        winner, count = counts.most_common(1)[0]
        p = count / len(matches)
        if p < 0.55: return None
        return {
            "name": "mirror3", "group": "sequence",
            "signal": winner,
            "probability": clamp(p, 0.50, 0.78),
            "support": len(matches),
            "metadata": {"matches": len(matches)},
        }

    def sequence_repeat(self, arr, regime):
        if len(arr) < 20: return None
        context = tuple(arr[-4:])
        nexts = []
        for i in range(len(arr) - 5):
            if tuple(arr[i:i + 4]) == context:
                nexts.append(arr[i + 4])
        if len(nexts) < 3: return None
        counts = Counter(nexts)
        winner, count = counts.most_common(1)[0]
        p = count / len(nexts)
        if p < 0.55: return None
        return {
            "name": "sequence_repeat4", "group": "sequence",
            "signal": winner,
            "probability": clamp(p, 0.50, 0.80),
            "support": len(nexts),
            "metadata": {"matches": len(nexts)},
        }

    def run_length_context(self, arr, regime):
        if len(arr) < 30: return None
        streak, result = current_streak(arr)
        if streak < 2: return None
        outcomes = []
        for i in range(1, len(arr) - 1):
            if arr[i] != arr[i - 1]: continue
            run = 2
            j = i - 2
            while j >= 0 and arr[j] == arr[i]:
                run += 1
                j -= 1
            if run == streak and i + 1 < len(arr):
                outcomes.append(arr[i + 1])
        if len(outcomes) < 4: return None
        counts = Counter(outcomes)
        winner, count = counts.most_common(1)[0]
        p = count / len(outcomes)
        if p < 0.55: return None
        return {
            "name": "run_length_context", "group": "streak_context",
            "signal": winner,
            "probability": clamp(p, 0.50, 0.78),
            "support": len(outcomes),
            "metadata": {"run_length": streak, "matches": len(outcomes)},
        }


# ============================================================
# CALIBRATOR
# ============================================================
class Calibrator:
    def __init__(self, db):
        self.db = db
        self.lock = threading.Lock()
        self.bins = defaultdict(lambda: [0, 0])
        self._load()

    def _load(self):
        try:
            with self.db.lock:
                rows = self.db.conn.execute("""
                    SELECT probability, correct FROM predictions
                    WHERE evaluated=1
                      AND probability IS NOT NULL
                      AND correct IS NOT NULL
                """).fetchall()
                for p, correct in rows:
                    self._add(float(p), bool(correct))
        except Exception:
            pass

    @staticmethod
    def _key(probability):
        p = clamp(probability, 0.50, 0.99)
        return int(p * 100) // 5 * 5

    def _add(self, probability, correct):
        key = self._key(probability)
        self.bins[key][0] += 1
        self.bins[key][1] += int(correct)

    def update(self, probability, correct):
        with self.lock:
            self._add(probability, correct)

    def calibrated(self, probability):
        p = clamp(probability, 0.50, 0.99)
        key = self._key(p)
        with self.lock:
            total, wins = self.bins.get(key, [0, 0])
            if total < CALIBRATION_MIN_SAMPLES:
                return p
            empirical = wins / total
            return clamp(0.70 * empirical + 0.30 * p, 0.50, 0.99)

    def stats(self):
        out = []
        with self.lock:
            for key in sorted(self.bins):
                total, wins = self.bins[key]
                if total:
                    out.append({
                        "bin": f"{key}-{key+4}%",
                        "total": total,
                        "wins": wins,
                        "empirical": wins / total,
                    })
        return out


# ============================================================
# EVIDENCE FUSION
# ============================================================
class EvidenceFusion:
    GROUPS = (
        "markov", "distribution", "transition",
        "streak", "sequence", "streak_context",
    )

    def __init__(self, tracker):
        self.tracker = tracker

    def combine(self, models, regime):
        grouped = defaultdict(list)
        for name, model in models.items():
            grouped[model["group"]].append(model)

        selected = {}
        for group, candidates in grouped.items():
            candidates = sorted(
                candidates,
                key=lambda x: (
                    x["probability"] * self.tracker.score(x["name"]),
                    x["support"]
                ),
                reverse=True
            )
            selected[group] = candidates[0]

        big_evidence = 0.0
        small_evidence = 0.0
        total_evidence = 0.0
        group_scores = {}

        for group, model in selected.items():
            p = model["probability"]
            signal = model["signal"]
            name = model["name"]
            reliability = self.tracker.score(name)
            support_factor = clamp(
                math.sqrt(max(model["support"], 1) / 20.0),
                0.35, 1.0
            )
            regime_factor = self.regime_factor(model, regime)
            weight = reliability * support_factor * regime_factor
            signed = (p - 0.5) * 2.0 * weight

            if signal == "Big":
                big_evidence += signed
            else:
                small_evidence += signed
            total_evidence += abs(signed)

            group_scores[group] = {
                "signal": signal,
                "probability": p,
                "weight": weight,
                "signed": signed,
                "model": name,
                "support": model["support"],
            }

        if not selected or total_evidence <= 0:
            return {
                "prediction": None,
                "raw_probability": 0.5,
                "agreement": 0.0,
                "disagreement": 1.0,
                "groups": {},
                "selected_models": {},
            }

        net = big_evidence - small_evidence
        probability = 0.5 + min(
            0.49, abs(net) / max(1.0, len(selected))
        )
        prediction = "Big" if net >= 0 else "Small"
        signals = [item["signal"] for item in selected.values()]
        agreement = sum(s == prediction for s in signals) / len(signals)
        disagreement = 1.0 - agreement

        return {
            "prediction": prediction,
            "raw_probability": clamp(probability, 0.50, 0.99),
            "agreement": agreement,
            "disagreement": disagreement,
            "groups": dict(group_scores),
            "selected_models": {
                group: item["name"] for group, item in selected.items()
            },
        }

    @staticmethod
    def regime_factor(model, regime):
        name = model["name"]
        r = regime["name"]
        if r == "ALTERNATING":
            if name in ("alternating", "markov2", "markov3"): return 1.10
            if name == "streak_continue": return 0.85
        if r == "LONG_STREAK":
            if name == "streak_continue": return 1.08
            if name == "streak_reversal": return 1.05
        if r == "TRANSITION":
            if name == "transition": return 1.12
            if name in ("recent_bias10", "frequency20"): return 0.92
        if r == "CHAOTIC":
            if name in ("markov3", "sequence_repeat4"): return 0.85
        return 1.0


# ============================================================
# SIGNAL FILTER
# ============================================================
class SignalFilter:
    def decide(self, fusion, calibrated_probability, regime):
        prediction = fusion["prediction"]
        if prediction is None:
            return False, "NO_EVIDENCE"

        edge = abs(calibrated_probability - 0.5)
        if calibrated_probability < MIN_SIGNAL_PROB:
            return False, "LOW_PROBABILITY"
        if edge < MIN_EDGE:
            return False, "LOW_EDGE"
        if fusion["disagreement"] > MAX_MODEL_DISAGREEMENT:
            return False, "MODEL_DISAGREEMENT"

        if regime["name"] in ("TRANSITION", "CHAOTIC"):
            if calibrated_probability < 0.62:
                return False, "REGIME_UNCERTAINTY"
        if regime["name"] == "UNKNOWN":
            return False, "UNKNOWN_REGIME"

        return True, "EDGE_OK"


# ============================================================
# HYBRID V6.1 ENGINE
# ============================================================
class HybridV61:
    def __init__(self):
        global global_agent
        global_agent = self

        self.db = DataEngine()
        self.history = deque(
            self.db.get_history(MAX_HISTORY),
            maxlen=MAX_HISTORY
        )

        self.regime_detector = RegimeDetector()
        self.pattern_engine = PatternEngine()
        self.tracker = PatternTracker(self.db)
        self.calibrator = Calibrator(self.db)
        self.fusion = EvidenceFusion(self.tracker)
        self.signal_filter = SignalFilter()
        self.lock = threading.RLock()

        self.active_prediction = None
        self.current_step = 0
        self.is_paused = False

        self.total_signals = 0
        self.total_skips = 0
        self.total_wins = 0
        self.total_losses = 0
        self.consecutive_wins = 0
        self.consecutive_losses = 0

        self.win_by_step = defaultdict(int)
        self.loss_by_step = defaultdict(int)

        self.last_period = "None"
        self.last_number = None
        self.last_result = "None"
        self.last_signal = "None"
        self.last_reason = "None"
        self.last_probability = 0.0
        self.last_edge = 0.0
        self.last_regime = "UNKNOWN"

        self.api_errors = 0
        self.last_api_error = ""

        print(f"🚀 HYBRID V6.1 loaded {len(self.history)} results", flush=True)

    # --------------------------------------------------------
    # Telegram
    # --------------------------------------------------------
    def send_telegram(self, message):
        if not TELEGRAM_TOKEN or not CHAT_ID:
            return False
        try:
            r = requests.post(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                json={
                    "chat_id": CHAT_ID,
                    "text": message,
                    "parse_mode": "HTML",
                },
                timeout=10
            )
            return r.ok
        except Exception:
            return False

    # --------------------------------------------------------
    # Evaluation (Win Only Shown - Unlimited Martingale)
    # --------------------------------------------------------
    def evaluate_previous(self, actual, current_period):
        if not self.active_prediction:
            return None

        p = self.active_prediction
        predicted = p["prediction"]
        correct = predicted == actual
        step = p["step"]

        with self.lock:
            if correct:
                # ✅ WIN → Step Reset
                self.total_wins += 1
                self.consecutive_wins += 1
                self.consecutive_losses = 0
                self.win_by_step[step] += 1
                self.calibrator.update(p["probability"], True)

                for model in p["models"].values():
                    self.tracker.update(model["name"], model["signal"], actual)

                if p.get("db_id"):
                    self.db.evaluate_prediction(p["db_id"], actual)

                self.current_step = 0

                # ✅ Win Only Message
                self.send_telegram(
                    f"✅ <b>WIN</b> — Step {step + 1}\n"
                    f"🔢 {actual}\n"
                    f"🔄 Step Reset → <b>Step 1</b>\n"
                    f"📊 WR: {self.get_wr()*100:.1f}%"
                )
            else:
                # ❌ LOSS → Step +1 (Silent & Unlimited)
                self.total_losses += 1
                self.consecutive_losses += 1
                self.consecutive_wins = 0
                self.loss_by_step[step] += 1
                self.calibrator.update(p["probability"], False)

                wrong = []
                correct_models = []
                for model in p["models"].values():
                    if model["signal"] == actual:
                        correct_models.append(model["name"])
                    else:
                        wrong.append(model["name"])
                    self.tracker.update(model["name"], model["signal"], actual)

                self.db.save_error(
                    p.get("source_period"), predicted, actual,
                    p["regime"], p["models"], wrong, correct_models
                )

                if p.get("db_id"):
                    self.db.evaluate_prediction(p["db_id"], actual)

                # Step Cap ဖယ်ရှားလိုက်ပြီဖြစ်သောကြောင့် အကန့်အသတ်မရှိ ဆက်လက်တိုးမည်
                self.current_step += 1

            self.active_prediction = None

        return correct

    # --------------------------------------------------------
    # Generate
    # --------------------------------------------------------
    def generate(self, source_period):
        arr = list(self.history)
        if len(arr) < MIN_HISTORY:
            return {
                "signal": None, "probability": 0.0, "edge": 0.0,
                "reason": "WARMUP", "regime": "UNKNOWN",
                "models": {}, "groups": {},
            }

        regime = self.regime_detector.detect(arr)
        models = self.pattern_engine.predict(arr, regime)

        if not models:
            return {
                "signal": None, "probability": 0.0, "edge": 0.0,
                "reason": "NO_MODEL_EVIDENCE", "regime": regime["name"],
                "models": {}, "groups": {},
            }

        fusion = self.fusion.combine(models, regime)
        raw_p = fusion["raw_probability"]
        calibrated = self.calibrator.calibrated(raw_p)
        edge = abs(calibrated - 0.5)

        ok, filter_reason = self.signal_filter.decide(
            fusion, calibrated, regime
        )

        if not ok:
            return {
                "signal": None, "probability": calibrated, "edge": edge,
                "reason": filter_reason, "regime": regime["name"],
                "models": models, "groups": fusion["groups"],
                "agreement": fusion["agreement"],
                "disagreement": fusion["disagreement"],
            }

        reason = (
            f"EDGE_OK | {regime['name']} | "
            f"agree={fusion['agreement']*100:.0f}%"
        )
        return {
            "signal": fusion["prediction"],
            "probability": calibrated,
            "edge": edge,
            "reason": reason,
            "regime": regime["name"],
            "models": models,
            "groups": fusion["groups"],
            "agreement": fusion["agreement"],
            "disagreement": fusion["disagreement"],
            "source_period": str(source_period),
        }

    # --------------------------------------------------------
    # Round
    # --------------------------------------------------------
    def analyze_round(self, period, number):
        result = number_to_result(number)
        if result is None:
            print(f"⚠️ Invalid: period={period}, number={number}", flush=True)
            return

        with self.lock:
            if self.db.has_period(period):
                return

            # 1) Evaluate previous (Win Only Shown)
            self.evaluate_previous(result, str(period))

            # 2) Save
            self.db.save_result(period, number, result)
            self.history.append(result)
            self.last_period = str(period)
            self.last_number = int(number)
            self.last_result = result

            if self.is_paused:
                self.last_signal = "PAUSED"
                self.last_reason = "PAUSED"
                return

            # 3) Generate
            prediction = self.generate(period)
            self.last_signal = (
                prediction["signal"] if prediction["signal"] else "SKIP"
            )
            self.last_reason = prediction["reason"]
            self.last_probability = prediction["probability"]
            self.last_edge = prediction["edge"]
            self.last_regime = prediction["regime"]

            if prediction["signal"] is None:
                self.total_skips += 1
                self.send_telegram(
                    f"⏸️ <b>SKIP</b>\n"
                    f"📅 {period}\n"
                    f"📌 {prediction['reason']}\n"
                    f"📊 Prob: {prediction['probability']*100:.1f}% | "
                    f"Edge: {prediction['edge']*100:.1f}pp"
                )
                return

            # 4) Signal
            self.total_signals += 1
            target_period = self.estimate_next_period(period)

            model_list = {
                name: {
                    "name": model["name"],
                    "group": model["group"],
                    "signal": model["signal"],
                    "probability": model["probability"],
                    "support": model["support"],
                    "metadata": model.get("metadata", {}),
                }
                for name, model in prediction["models"].items()
            }

            record = {
                "source_period": str(period),
                "target_period": str(target_period) if target_period else None,
                "prediction": prediction["signal"],
                "probability": prediction["probability"],
                "edge": prediction["edge"],
                "reason": prediction["reason"],
                "regime": prediction["regime"],
                "entropy": self.regime_detector.detect(list(self.history))["entropy"],
                "transition_rate": transition_rate(list(self.history)[-20:]),
                "models": model_list,
                "groups": prediction.get("groups", {}),
            }

            db_id = self.db.save_prediction(record)

            self.active_prediction = {
                **record,
                "db_id": db_id,
                "step": self.current_step,
            }

            # ✅ Signal Message (Shows current step multiplier)
            self.send_telegram(
                f"🚀 <b>HYBRID V6.1 SIGNAL</b>\n"
                f"📅 Period: {period}\n"
                f"🎯 <b>{prediction['signal'].upper()}</b>\n"
                f"💰 <b>Step {self.current_step + 1}</b> "
                f"({2**self.current_step}x)\n"
                f"📊 Prob: {prediction['probability']*100:.1f}% | "
                f"Edge: {prediction['edge']*100:.1f}pp\n"
                f"📌 {prediction['regime']} | "
                f"Agree: {prediction.get('agreement', 0)*100:.0f}%"
            )

    @staticmethod
    def estimate_next_period(period):
        try:
            return str(int(str(period)) + 1)
        except Exception:
            return None

    # --------------------------------------------------------
    # Stats
    # --------------------------------------------------------
    def get_wr(self):
        total = self.total_wins + self.total_losses
        return self.total_wins / total if total else 0.0

    def get_win3_rate(self):
        wins = (
            self.win_by_step[0] + self.win_by_step[1] + self.win_by_step[2]
        )
        total = self.total_wins
        return wins / total if total else 0.0

    # Step >= 4 (index >= 3) အကြိမ်အရေအတွက်အားလုံးပေါင်း
    def get_win_s4_plus(self):
        return sum(count for step, count in self.win_by_step.items() if step >= 3)

    def dashboard_state(self):
        arr = list(self.history)
        regime = self.regime_detector.detect(arr)
        return {
            "version": "HYBRID V6.1",
            "history": len(arr),
            "signals": self.total_signals,
            "skips": self.total_skips,
            "wins": self.total_wins,
            "losses": self.total_losses,
            "wr": self.get_wr(),
            "win3": self.get_win3_rate(),
            "step": self.current_step + 1,
            "paused": self.is_paused,
            "last_period": self.last_period,
            "last_number": self.last_number,
            "last_result": self.last_result,
            "last_signal": self.last_signal,
            "last_reason": self.last_reason,
            "last_probability": self.last_probability,
            "last_edge": self.last_edge,
            "regime": regime,
            "db": self.db.stats(),
            "api_errors": self.api_errors,
            "last_api_error": self.last_api_error,
        }


# ============================================================
# TELEGRAM COMMAND LOOP
# ============================================================
def poll_telegram(agent):
    if not TELEGRAM_TOKEN or not CHAT_ID:
        print("ℹ️ Telegram disabled", flush=True)
        return

    try:
        requests.get(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/deleteWebhook",
            params={"drop_pending_updates": True},
            timeout=10
        )
    except Exception:
        pass

    offset = 0
    while True:
        try:
            r = requests.get(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates",
                params={"offset": offset, "timeout": 20},
                timeout=25
            )
            if r.status_code != 200:
                time.sleep(2)
                continue
            for u in r.json().get("result", []):
                offset = u["update_id"] + 1
                msg = u.get("message") or u.get("edited_message") or {}
                cid = str(msg.get("chat", {}).get("id", ""))
                if cid != str(CHAT_ID): continue
                txt = str(msg.get("text", "")).strip().lower()

                if txt == "/status":
                    s = agent.dashboard_state()
                    wbs = agent.win_by_step
                    agent.send_telegram(
                        f"🚀 <b>HYBRID V6.1 STATUS</b>\n\n"
                        f"Mode: {'PAUSED 🛑' if s['paused'] else 'RUNNING 🟢'}\n"
                        f"History: {s['history']}\n"
                        f"Signals: {s['signals']} | Skips: {s['skips']}\n"
                        f"W: {s['wins']} | L: {s['losses']}\n"
                        f"📊 WR: <b>{s['wr']*100:.2f}%</b>\n"
                        f"🎯 Win≤3: {s['win3']*100:.1f}%\n"
                        f"💰 <b>Step: {s['step']}</b>\n\n"
                        f"Regime: {s['regime']['name']}\n"
                        f"Entropy: {s['regime']['entropy']:.3f}\n\n"
                        f"<b>Win by Step:</b>\n"
                        f"S1:{wbs[0]} S2:{wbs[1]} S3:{wbs[2]}\n"
                        f"S4+:{agent.get_win_s4_plus()}"
                    )
                elif txt == "/patterns":
                    rows = agent.tracker.all_stats()
                    if not rows:
                        agent.send_telegram("No data yet.")
                        continue
                    lines = ["🧠 <b>PATTERN STATS</b>"]
                    for row in rows[:12]:
                        lines.append(
                            f"{row['name']}: "
                            f"{row['wr']*100:.1f}% "
                            f"n={row['total']} "
                            f"recent={row['recent_wr']*100:.1f}%"
                        )
                    agent.send_telegram("\n".join(lines))
                elif txt == "/pause":
                    agent.is_paused = True
                    agent.send_telegram("🛑 Paused")
                elif txt == "/resume":
                    agent.is_paused = False
                    agent.send_telegram("🟢 Resumed")
                elif txt == "/reset":
                    agent.current_step = 0
                    agent.consecutive_losses = 0
                    agent.send_telegram("🔄 Step Reset → 1")
                elif txt == "/help":
                    agent.send_telegram(
                        "🤖 <b>Commands</b>\n"
                        "/status - Full stats\n"
                        "/patterns - Pattern stats\n"
                        "/pause - Pause\n"
                        "/resume - Resume\n"
                        "/reset - Reset step"
                    )
        except Exception as e:
            print(f"TG error: {e}", flush=True)
        time.sleep(1)


# ============================================================
# API CLIENT
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
        if API_AUTH:
            headers["authorization"] = f"Bearer {API_AUTH}"
        if API_ORIGIN:
            headers["origin"] = API_ORIGIN
        if API_REFERER:
            headers["referer"] = API_REFERER

        payload = {
            "pageSize": 10, "pageNo": 1,
            "typeId": API_TYPE_ID, "language": API_LANGUAGE,
            "timestamp": int(time.time()),
        }
        if API_RANDOM: payload["random"] = API_RANDOM
        if API_SIGNATURE: payload["signature"] = API_SIGNATURE

        r = self.session.post(
            API_URL, headers=headers, json=payload,
            timeout=REQUEST_TIMEOUT
        )
        r.raise_for_status()
        data = r.json()
        items = data.get("data", {}).get("list", []) if isinstance(data, dict) else []
        if not items:
            return None
        latest = items[0]
        raw_period = latest.get("issueNumber") or latest.get("period") or latest.get("issue")
        raw_number = latest.get("number") if latest.get("number") is not None else latest.get("num")
        if raw_period is None or raw_number is None:
            return None
        return {
            "raw_period": str(raw_period),
            "period": self.apply_offset(raw_period),
            "number": int(raw_number),
        }

    @staticmethod
    def apply_offset(raw_period):
        try:
            return str(int(str(raw_period)) + PERIOD_OFFSET)
        except Exception:
            return str(raw_period)


# ============================================================
# MAIN BOT LOOP
# ============================================================
def run_bot():
    print("🚀 HYBRID V6.1 starting...", flush=True)
    agent = HybridV61()
    api = ResultAPIClient()

    threading.Thread(
        target=poll_telegram, args=(agent,), daemon=True
    ).start()

    last_period = None
    while True:
        try:
            item = api.fetch_latest()
            if item:
                period = item["period"]
                number = item["number"]
                if period != last_period:
                    last_period = period
                    print(f"📡 Sync {period} → {number}", flush=True)
                    agent.analyze_round(period, number)
        except Exception as e:
            agent.api_errors += 1
            agent.last_api_error = str(e)
            print(f"⚠️ API error: {e}", flush=True)
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
<meta http-equiv="refresh" content="15">
<title>HYBRID V6.1</title>
<style>
body { margin:0; background:#0b1020; color:#e9f0ff; font-family:system-ui,Arial,sans-serif; padding:14px; }
h1 { color:#00ffff; margin-bottom:6px; }
.small { color:#9eabc4; }
.grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(180px,1fr)); gap:10px; }
.card { background:#151d33; border:1px solid #2b3858; border-radius:14px; padding:14px; margin:10px 0; }
.value { font-size:28px; font-weight:800; }
.green { color:#00ff88; } .red { color:#ff5566; }
.yellow { color:#ffe600; } .cyan { color:#00ffff; }
.mono { font-family:monospace; letter-spacing:2px; }
table { width:100%; border-collapse:collapse; }
td,th { padding:8px; border-bottom:1px solid #2b3858; text-align:left; }
</style>
</head>
<body>
<h1>🚀 HYBRID V6.1</h1>
<div class="small">Signal Only + Unlimited Step Tracking + Win Only Display</div>

{% if not agent %}
<div class="card">Starting...</div>
{% else %}
<div class="grid">
  <div class="card">
    <div>Mode</div>
    <div class="value">{{ "PAUSED 🛑" if agent.is_paused else "RUNNING 🟢" }}</div>
  </div>
  <div class="card">
    <div>Win Rate</div>
    <div class="value green">{{ "%.2f"|format(agent.get_wr()*100) }}%</div>
  </div>
  <div class="card">
    <div>Signals / Skips</div>
    <div class="value">{{ agent.total_signals }} / {{ agent.total_skips }}</div>
  </div>
  <div class="card">
    <div>W / L</div>
    <div class="value">
      <span class="green">{{ agent.total_wins }}</span> /
      <span class="red">{{ agent.total_losses }}</span>
    </div>
  </div>
  <div class="card">
    <div>Current Step</div>
    <div class="value yellow">{{ agent.current_step + 1 }}</div>
  </div>
</div>

<div class="card">
  <h2>📊 Win by Step</h2>
  <p>S1: {{ agent.win_by_step[0] }} | S2: {{ agent.win_by_step[1] }} |
     S3: {{ agent.win_by_step[2] }} | S4+: {{ agent.get_win_s4_plus() }}</p>
  <p>Win ≤3: <b class="cyan">{{ "%.1f"|format(agent.get_win3_rate()*100) }}%</b></p>
</div>

<div class="card">
  <h2>🎯 Last Signal</h2>
  <p>Period: <b>{{ agent.last_period }}</b></p>
  <p>Result: <b>{{ agent.last_number }} → {{ agent.last_result }}</b></p>
  <p>Signal: <b class="cyan">{{ agent.last_signal }}</b></p>
  <p>Probability: <b>{{ "%.1f"|format(agent.last_probability*100) }}%</b></p>
  <p>Edge: <b>{{ "%.1f"|format(agent.last_edge*100) }}pp</b></p>
  <p>Reason: {{ agent.last_reason }}</p>
</div>

<div class="card">
  <h2>📊 Pattern Performance</h2>
  <table>
    <tr><th>Pattern</th><th>Total</th><th>WR</th><th>Recent</th></tr>
    {% for row in agent.tracker.all_stats()[:15] %}
    <tr>
      <td>{{ row.name }}</td>
      <td>{{ row.total }}</td>
      <td>{{ "%.1f"|format(row.wr*100) }}%</td>
      <td>{{ "%.1f"|format(row.recent_wr*100) }}%</td>
    </tr>
    {% endfor %}
  </table>
</div>

<div class="card">
  <h2>📜 Last 30 Results</h2>
  <div class="mono">
    {% for row in agent.db.get_last_rows(30) %}
      {{ "B" if row.result == "Big" else "S" }}
    {% endfor %}
  </div>
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
    if not global_agent:
        return jsonify({"status": "starting"})
    return jsonify(global_agent.dashboard_state())

@app.route("/api/patterns")
def api_patterns():
    if not global_agent:
        return jsonify([])
    return jsonify(global_agent.tracker.all_stats())


# ============================================================
# START
# ============================================================
if __name__ == "__main__":
    threading.Thread(target=run_bot, daemon=True).start()
    app.run(host="0.0.0.0", port=PORT, debug=False)
