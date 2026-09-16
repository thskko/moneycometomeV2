#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
HYBRID ENGINE V8.6
Big/Small sequence prediction engine.

V8.6 = V8.5 + Raw API debug + Field detection + Multiple structure support
     + Better error reporting.

Debug features:
- /api/debug shows raw API response text
- /api/debug shows detected JSON structure
- /api/debug tries multiple field paths (data.list, data.rows, etc.)
- Startup API test
- Telegram startup notification

No model can guarantee future accuracy.
"""

import os
import sys
import time
import math
import json
import sqlite3
import threading
import traceback
from collections import defaultdict, deque, Counter
from datetime import datetime, timezone

import requests
from flask import Flask, jsonify, render_template_string


# ============================================================
# CONFIG
# ============================================================

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "").strip()
CHAT_ID = os.getenv("CHAT_ID", "").strip()

API_URL = os.getenv(
    "RESULT_API_URL",
    "https://6lotteryapi.com/api/webapi/GetNoaverageEmerdList"
)
API_AUTH = os.getenv("RESULT_API_AUTH", "").strip()
API_ORIGIN = os.getenv("API_ORIGIN", "https://6win598.com")
API_REFERER = os.getenv("API_REFERER", "https://6win598.com/")
API_RANDOM = os.getenv("API_RANDOM", "").strip()
API_SIGNATURE = os.getenv("API_SIGNATURE", "").strip()

API_TYPE_ID = int(os.getenv("API_TYPE_ID", "30"))
API_LANGUAGE = int(os.getenv("API_LANGUAGE", "7"))
API_PAGE_SIZE = int(os.getenv("API_PAGE_SIZE", "20"))
PERIOD_OFFSET = int(os.getenv("PERIOD_OFFSET", "2"))

POLL_SECONDS = float(os.getenv("POLL_SECONDS", "2"))
REQUEST_TIMEOUT = float(os.getenv("REQUEST_TIMEOUT", "10"))

DB_PATH = os.getenv("DB_PATH", "hybrid_v86.db")

MIN_HISTORY = int(os.getenv("MIN_HISTORY", "35"))
MAX_HISTORY = int(os.getenv("MAX_HISTORY", "1000"))

MIN_LIVE_CONF = float(os.getenv("MIN_LIVE_CONF", "0.58"))
REJECT_CONF = float(os.getenv("REJECT_CONF", "0.54"))
MIN_EDGE = float(os.getenv("MIN_EDGE", "0.08"))
MAX_DISAGREEMENT = float(os.getenv("MAX_DISAGREEMENT", "0.40"))

PRIOR_N = float(os.getenv("PRIOR_N", "30"))
CONTEXT_PRIOR_N = float(os.getenv("CONTEXT_PRIOR_N", "25"))

LEARNING_RATE = float(os.getenv("LEARNING_RATE", "0.03"))
L2_PENALTY = float(os.getenv("L2_PENALTY", "0.01"))

CORR_WINDOW = int(os.getenv("CORR_WINDOW", "50"))
MIN_CORR_N = int(os.getenv("MIN_CORR_N", "20"))

SHADOW_MIN_AGREEMENT = float(os.getenv("SHADOW_MIN_AGREEMENT", "0.60"))
SHADOW_MIN_PROB = float(os.getenv("SHADOW_MIN_PROB", "0.56"))

ALLOW_TELEGRAM_COMMANDS = os.getenv("ALLOW_TELEGRAM_COMMANDS", "1") == "1"

BASE_BET = float(os.getenv("BASE_BET", "1.0"))
PORT = int(os.getenv("PORT", "8080"))

VALID_RESULTS = ("Big", "Small")

app = Flask(__name__)
global_agent = None


# ============================================================
# HELPERS
# ============================================================

def log(msg):
    print(msg, flush=True)


def clamp(x, lo, hi):
    return max(lo, min(hi, x))


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def sigmoid(x):
    x = clamp(float(x), -20, 20)
    return 1.0 / (1.0 + math.exp(-x))


def safe_logit(p):
    p = clamp(float(p), 0.02, 0.98)
    return math.log(p / (1.0 - p))


def beta_mean(wins, total, prior_mean=0.50, prior_n=30):
    return (wins + prior_mean * prior_n) / max(1.0, total + prior_n)


def entropy_binary(p):
    p = clamp(p, 1e-9, 1 - 1e-9)
    return -(p * math.log2(p) + (1 - p) * math.log2(1 - p))


def acf(arr, lag):
    if len(arr) <= lag:
        return 0.0
    x = [1.0 if v == "Big" else -1.0 for v in arr]
    mean = sum(x) / len(x)
    denom = sum((v - mean) ** 2 for v in x)
    if denom <= 1e-12:
        return 0.0
    cov = sum(
        (x[i] - mean) * (x[i - lag] - mean)
        for i in range(lag, len(x))
    )
    return clamp(cov / denom, -1, 1)


def streak_length(arr):
    if not arr:
        return 0
    last = arr[-1]
    n = 0
    for x in reversed(arr):
        if x != last:
            break
        n += 1
    return n


def streak_bucket(n):
    if n <= 1:
        return "1"
    if n == 2:
        return "2"
    if n == 3:
        return "3"
    return "4+"


def result_value(result):
    return 1.0 if result == "Big" else 0.0


# ============================================================
# DATABASE
# ============================================================

class Database:
    def __init__(self, path=DB_PATH, read_only=False):
        self.path = path
        self.read_only = read_only
        if read_only:
            uri = f"file:{path}?mode=ro"
            self.conn = sqlite3.connect(uri, uri=True, check_same_thread=False, timeout=30)
        else:
            self.conn = sqlite3.connect(path, check_same_thread=False, timeout=30)
        self.lock = threading.RLock()
        if not read_only:
            self.init_db()

    def init_db(self):
        with self.lock:
            c = self.conn.cursor()
            c.execute("""
                CREATE TABLE IF NOT EXISTS history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    period TEXT UNIQUE NOT NULL,
                    number INTEGER NOT NULL,
                    result TEXT NOT NULL,
                    timestamp TEXT NOT NULL
                )
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS predictions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    source_period TEXT,
                    target_period TEXT,
                    prediction TEXT,
                    raw_probability REAL,
                    calibrated_probability REAL,
                    confidence REAL,
                    state TEXT,
                    regime TEXT,
                    regime_age INTEGER,
                    transition INTEGER,
                    entropy REAL,
                    disagreement REAL,
                    model_json TEXT,
                    group_json TEXT,
                    feature_json TEXT,
                    evaluated INTEGER DEFAULT 0,
                    actual TEXT,
                    correct INTEGER
                )
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS model_stats (
                    model TEXT PRIMARY KEY,
                    total INTEGER DEFAULT 0,
                    wins INTEGER DEFAULT 0,
                    errors_json TEXT,
                    state TEXT DEFAULT 'NEW'
                )
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS context_stats (
                    context TEXT PRIMARY KEY,
                    total INTEGER DEFAULT 0,
                    wins INTEGER DEFAULT 0
                )
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS group_stats (
                    group_name TEXT PRIMARY KEY,
                    total INTEGER DEFAULT 0,
                    wins INTEGER DEFAULT 0
                )
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS calibration (
                    bucket TEXT PRIMARY KEY,
                    total INTEGER DEFAULT 0,
                    wins INTEGER DEFAULT 0
                )
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS meta_state (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS loss_analysis (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    source_period TEXT,
                    prediction TEXT,
                    actual TEXT,
                    regime TEXT,
                    loss_type TEXT,
                    confidence REAL,
                    model_json TEXT
                )
            """)
            self.conn.commit()

    def has_period(self, period):
        with self.lock:
            row = self.conn.execute(
                "SELECT 1 FROM history WHERE period=? LIMIT 1",
                (str(period),)
            ).fetchone()
        return row is not None

    def save_result(self, period, number, result):
        with self.lock:
            self.conn.execute("""
                INSERT OR IGNORE INTO history (period, number, result, timestamp)
                VALUES (?, ?, ?, ?)
            """, (str(period), int(number), result, utc_now()))
            self.conn.commit()

    def history(self, limit=MAX_HISTORY):
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

    def last_period(self):
        with self.lock:
            row = self.conn.execute("""
                SELECT period FROM history ORDER BY id DESC LIMIT 1
            """).fetchone()
        return row[0] if row else None

    def save_prediction(self, p):
        with self.lock:
            cur = self.conn.execute("""
                INSERT INTO predictions (
                    created_at, source_period, target_period,
                    prediction, raw_probability,
                    calibrated_probability, confidence,
                    state, regime, regime_age, transition,
                    entropy, disagreement,
                    model_json, group_json, feature_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                utc_now(),
                p.get("source_period"), p.get("target_period"),
                p["prediction"], p["raw_probability"],
                p["calibrated_probability"], p["confidence"],
                p["state"], p["regime"], p["regime_age"],
                p["transition"], p["entropy"], p["disagreement"],
                json.dumps(p["models"], ensure_ascii=False),
                json.dumps(p["groups"], ensure_ascii=False),
                json.dumps(p["features"], ensure_ascii=False),
            ))
            self.conn.commit()
            return cur.lastrowid

    def evaluate_prediction(self, prediction_id, actual):
        if not prediction_id:
            return None
        with self.lock:
            row = self.conn.execute(
                "SELECT prediction FROM predictions WHERE id=?",
                (int(prediction_id),)
            ).fetchone()
            if not row:
                return None
            correct = int(row[0] == actual)
            self.conn.execute("""
                UPDATE predictions SET evaluated=1, actual=?, correct=?
                WHERE id=?
            """, (actual, correct, int(prediction_id)))
            self.conn.commit()
        return bool(correct)

    def load_models(self):
        with self.lock:
            rows = self.conn.execute("""
                SELECT model,total,wins,errors_json,state FROM model_stats
            """).fetchall()
        out = {}
        for name, total, wins, errors, state in rows:
            try:
                errors = json.loads(errors or "[]")
            except Exception:
                errors = []
            out[name] = {
                "total": total, "wins": wins,
                "errors": deque(errors, maxlen=CORR_WINDOW),
                "state": state,
            }
        return out

    def save_model(self, name, s):
        with self.lock:
            self.conn.execute("""
                INSERT INTO model_stats (model,total,wins,errors_json,state)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(model) DO UPDATE SET
                    total=excluded.total,
                    wins=excluded.wins,
                    errors_json=excluded.errors_json,
                    state=excluded.state
            """, (
                name, s["total"], s["wins"],
                json.dumps(list(s["errors"])), s["state"],
            ))
            self.conn.commit()

    def load_context(self):
        with self.lock:
            rows = self.conn.execute("""
                SELECT context,total,wins FROM context_stats
            """).fetchall()
        return {k: {"total": n, "wins": w} for k, n, w in rows}

    def save_context(self, key, s):
        with self.lock:
            self.conn.execute("""
                INSERT INTO context_stats(context,total,wins)
                VALUES (?, ?, ?)
                ON CONFLICT(context) DO UPDATE SET
                    total=excluded.total, wins=excluded.wins
            """, (key, s["total"], s["wins"]))
            self.conn.commit()

    def load_groups(self):
        with self.lock:
            rows = self.conn.execute("""
                SELECT group_name,total,wins FROM group_stats
            """).fetchall()
        return {k: {"total": n, "wins": w} for k, n, w in rows}

    def save_group(self, key, s):
        with self.lock:
            self.conn.execute("""
                INSERT INTO group_stats(group_name,total,wins)
                VALUES (?, ?, ?)
                ON CONFLICT(group_name) DO UPDATE SET
                    total=excluded.total, wins=excluded.wins
            """, (key, s["total"], s["wins"]))
            self.conn.commit()

    def load_calibration(self):
        with self.lock:
            rows = self.conn.execute("""
                SELECT bucket,total,wins FROM calibration
            """).fetchall()
        return {k: {"total": n, "wins": w} for k, n, w in rows}

    def save_calibration(self, key, s):
        with self.lock:
            self.conn.execute("""
                INSERT INTO calibration(bucket,total,wins)
                VALUES (?, ?, ?)
                ON CONFLICT(bucket) DO UPDATE SET
                    total=excluded.total, wins=excluded.wins
            """, (key, s["total"], s["wins"]))
            self.conn.commit()

    def load_meta(self, key, default=None):
        with self.lock:
            row = self.conn.execute(
                "SELECT value FROM meta_state WHERE key=?",
                (key,)
            ).fetchone()
        if not row:
            return default
        try:
            return json.loads(row[0])
        except Exception:
            return default

    def save_meta(self, key, value):
        with self.lock:
            self.conn.execute("""
                INSERT INTO meta_state(key,value)
                VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value=excluded.value
            """, (key, json.dumps(value, ensure_ascii=False)))
            self.conn.commit()

    def save_loss(self, p):
        with self.lock:
            self.conn.execute("""
                INSERT INTO loss_analysis (
                    created_at, source_period, prediction, actual,
                    regime, loss_type, confidence, model_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                utc_now(), p.get("source_period"),
                p.get("prediction"), p.get("actual"),
                p.get("regime"), p.get("loss_type", "UNKNOWN"),
                p.get("confidence", 0.5),
                json.dumps(p.get("models", {}), ensure_ascii=False),
            ))
            self.conn.commit()

    def loss_types(self):
        with self.lock:
            rows = self.conn.execute("""
                SELECT loss_type, COUNT(*) FROM loss_analysis
                GROUP BY loss_type ORDER BY COUNT(*) DESC
            """).fetchall()
        return {r[0]: r[1] for r in rows}

    def report(self):
        with self.lock:
            total = self.conn.execute(
                "SELECT COUNT(*) FROM predictions WHERE evaluated=1"
            ).fetchone()[0]
            wins = self.conn.execute(
                "SELECT COALESCE(SUM(correct),0) FROM predictions WHERE evaluated=1"
            ).fetchone()[0]
            live_total = self.conn.execute("""
                SELECT COUNT(*) FROM predictions
                WHERE evaluated=1 AND state='LIVE'
            """).fetchone()[0]
            live_wins = self.conn.execute("""
                SELECT COALESCE(SUM(correct),0) FROM predictions
                WHERE evaluated=1 AND state='LIVE'
            """).fetchone()[0]
            shadow_total = self.conn.execute("""
                SELECT COUNT(*) FROM predictions
                WHERE evaluated=1 AND state='SHADOW'
            """).fetchone()[0]
            shadow_wins = self.conn.execute("""
                SELECT COALESCE(SUM(correct),0) FROM predictions
                WHERE evaluated=1 AND state='SHADOW'
            """).fetchone()[0]
        return {
            "total": total, "wins": wins,
            "wr": wins / total if total else None,
            "live_total": live_total, "live_wins": live_wins,
            "live_wr": live_wins / live_total if live_total else None,
            "shadow_total": shadow_total, "shadow_wins": shadow_wins,
            "shadow_wr": shadow_wins / shadow_total if shadow_total else None,
        }


# ============================================================
# MODEL GROUPS
# ============================================================

MODEL_GROUP = {
    "markov2": "SEQUENCE",
    "markov3": "SEQUENCE",
    "mirror3": "SEQUENCE",
    "repeat4": "SEQUENCE",
    "frequency20": "DISTRIBUTION",
    "bias10": "DISTRIBUTION",
    "streak_continue": "STREAK",
    "streak_reversal": "STREAK",
    "run_length": "STREAK",
    "transition": "TRANSITION",
    "alternating": "ALTERNATION",
}


# ============================================================
# BASE MODELS
# ============================================================

class BaseModels:
    @staticmethod
    def conditional(arr, n):
        if len(arr) <= n:
            return 0.50
        key = tuple(arr[-n:])
        nxt = []
        for i in range(len(arr) - n):
            if tuple(arr[i:i+n]) == key:
                nxt.append(arr[i+n])
        if not nxt:
            return 0.50
        return nxt.count("Big") / len(nxt)

    def predict(self, arr):
        out = {}
        out["markov2"] = self.conditional(arr, 2)
        out["markov3"] = self.conditional(arr, 3)

        if len(arr) >= 7:
            key = tuple(arr[-3:])
            nxt = [arr[i+3] for i in range(len(arr)-3) if tuple(arr[i:i+3]) == key]
            out["mirror3"] = nxt.count("Big") / len(nxt) if nxt else 0.50
        else:
            out["mirror3"] = 0.50

        if len(arr) >= 9:
            key = tuple(arr[-4:])
            nxt = [arr[i+4] for i in range(len(arr)-4) if tuple(arr[i:i+4]) == key]
            out["repeat4"] = nxt.count("Big") / len(nxt) if nxt else 0.50
        else:
            out["repeat4"] = 0.50

        w20 = arr[-20:]
        w10 = arr[-10:]
        out["frequency20"] = w20.count("Big") / len(w20) if w20 else 0.50
        out["bias10"] = w10.count("Big") / len(w10) if w10 else 0.50

        last = arr[-1] if arr else "Big"
        same = 0
        total = 0
        for i in range(len(arr)-1):
            if arr[i] == last:
                total += 1
                same += int(arr[i+1] == arr[i])
        continuation = same / total if total else 0.50
        out["transition"] = continuation if last == "Big" else 1.0 - continuation

        recent = arr[-6:]
        flips = sum(int(recent[i] != recent[i-1]) for i in range(1, len(recent)))
        alt_rate = flips / max(1, len(recent)-1)
        out["alternating"] = (1.0 - alt_rate) if last == "Big" else alt_rate

        s = streak_length(arr)
        cont_samples = []
        for i in range(1, len(arr)-1):
            if arr[i] == arr[i-1]:
                cont_samples.append(int(arr[i+1] == arr[i]))
        cont_rate = sum(cont_samples) / len(cont_samples) if cont_samples else 0.50
        cont_rate = 0.50 + (cont_rate - 0.50) * min(1.0, len(cont_samples) / 40.0)
        if s >= 3:
            cont_rate = 0.50 + (cont_rate - 0.50) * 0.80
        elif s == 2:
            cont_rate = 0.50 + (cont_rate - 0.50) * 0.60
        out["streak_continue"] = cont_rate if last == "Big" else 1.0 - cont_rate
        out["streak_reversal"] = 1.0 - out["streak_continue"]

        bucket = streak_bucket(s)
        run_samples = []
        for i in range(1, len(arr)-1):
            run = 1
            j = i - 1
            while j >= 0 and arr[j] == arr[i]:
                run += 1
                j -= 1
            if streak_bucket(run) == bucket:
                run_samples.append(int(arr[i+1] == arr[i]))
        run_rate = sum(run_samples) / len(run_samples) if run_samples else cont_rate
        run_rate = 0.50 + (run_rate - 0.50) * min(1.0, len(run_samples) / 30.0)
        out["run_length"] = run_rate if last == "Big" else 1.0 - run_rate

        return {k: clamp(v, 0.05, 0.95) for k, v in out.items()}


# ============================================================
# REGIME ENGINE
# ============================================================

class RegimeEngine:
    def __init__(self):
        self.last = None
        self.age = 0

    def detect(self, arr):
        if len(arr) < 20:
            return {
                "name": "UNKNOWN", "age": 0, "transition": 0,
                "p_big": 0.50, "acf1": 0, "acf2": 0, "acf3": 0, "stability": 0
            }

        w = arr[-20:]
        p_big = w.count("Big") / 20
        acf1 = acf(w, 1)
        acf2 = acf(w, 2)
        acf3 = acf(w, 3)
        flips = sum(int(w[i] != w[i-1]) for i in range(1, len(w)))
        alternation = flips / 19
        persistence = 1 - alternation

        a = w[:10]
        b = w[10:]
        p1 = a.count("Big") / 10
        p2 = b.count("Big") / 10
        stability = 1 - abs(p1 - p2)

        if acf1 <= -0.25 or alternation >= 0.72:
            name = "ALTERNATING"
        elif p_big >= 0.65 or p_big <= 0.35:
            name = "TREND"
        elif abs(acf1) < 0.12 and 0.45 <= p_big <= 0.55:
            name = "CHAOS"
        elif persistence >= 0.58:
            name = "PERSISTENT"
        else:
            name = "MIXED"

        transition = int(self.last is not None and self.last != name)
        if self.last is None or transition:
            self.age = 1
        else:
            self.age += 1
        self.last = name

        return {
            "name": name, "age": self.age, "transition": transition,
            "p_big": p_big, "acf1": acf1, "acf2": acf2, "acf3": acf3,
            "stability": stability,
        }


# ============================================================
# RELIABILITY
# ============================================================

class Reliability:
    def __init__(self, db):
        self.db = db
        self.stats = db.load_models()

    def ensure(self, name):
        if name not in self.stats:
            self.stats[name] = {
                "total": 0, "wins": 0,
                "errors": deque(maxlen=CORR_WINDOW),
                "state": "NEW",
            }

    def raw_wr(self, name):
        self.ensure(name)
        s = self.stats[name]
        return s["wins"] / s["total"] if s["total"] else 0.50

    def shrunk_wr(self, name):
        self.ensure(name)
        s = self.stats[name]
        return beta_mean(s["wins"], s["total"], 0.50, PRIOR_N)

    def update(self, name, predicted, actual):
        self.ensure(name)
        s = self.stats[name]
        correct = int(predicted == actual)
        s["total"] += 1
        s["wins"] += correct
        s["errors"].append(0 if correct else 1)
        n = len(s["errors"])
        recent_wr = 1 - sum(s["errors"]) / n if n else 0.50
        long_wr = self.raw_wr(name)

        if s["total"] < 15:
            state = "NEW"
        elif s["total"] < 25:
            state = "SHADOW"
        elif recent_wr >= 0.58 and long_wr >= 0.55:
            state = "CANDIDATE"
        elif recent_wr >= 0.52:
            state = "ACTIVE"
        elif recent_wr >= 0.47:
            state = "WEAK"
        else:
            state = "SHADOW"

        s["state"] = state
        self.db.save_model(name, s)

    def error_corr(self, a, b):
        self.ensure(a)
        self.ensure(b)
        x = list(self.stats[a]["errors"])
        y = list(self.stats[b]["errors"])
        n = min(len(x), len(y))
        if n < MIN_CORR_N:
            return 0.0
        x = x[-n:]
        y = y[-n:]
        mx = sum(x) / n
        my = sum(y) / n
        vx = sum((v-mx)**2 for v in x)
        vy = sum((v-my)**2 for v in y)
        if vx <= 1e-12 or vy <= 1e-12:
            return 0.0
        cov = sum((x[i]-mx)*(y[i]-my) for i in range(n))
        return clamp(cov / math.sqrt(vx*vy), -1, 1)

    def weight(self, name):
        self.ensure(name)
        s = self.stats[name]
        n = s["total"]
        if n == 0:
            return 0.50
        wr = self.shrunk_wr(name)
        factor = {
            "NEW": 0.45, "SHADOW": 0.55,
            "CANDIDATE": 0.80, "ACTIVE": 1.00, "WEAK": 0.60,
        }.get(s["state"], 0.50)
        sample = min(1.0, math.sqrt(n / 50))
        return clamp(0.50 + (wr - 0.50) * factor * sample * 3.0, 0.10, 0.95)


# ============================================================
# CONTEXT
# ============================================================

class Context:
    def __init__(self, db):
        self.db = db
        self.stats = db.load_context()

    def make_key(self, model, regime, arr):
        last = arr[-1] if arr else "NA"
        sb = streak_bucket(streak_length(arr))
        w = arr[-10:]
        p = w.count("Big") / max(1, len(w))
        if p >= 0.60:
            bias = "BIG"
        elif p <= 0.40:
            bias = "SMALL"
        else:
            bias = "NEUTRAL"
        return f"{model}|{regime}|{last}|{sb}|{bias}"

    def reliability(self, model, regime, arr):
        key = self.make_key(model, regime, arr)
        s = self.stats.get(key, {"total": 0, "wins": 0})
        if s["total"] >= 12:
            return beta_mean(s["wins"], s["total"], 0.50, CONTEXT_PRIOR_N)
        prefix = f"{model}|{regime}|"
        total = 0
        wins = 0
        for k, v in self.stats.items():
            if k.startswith(prefix):
                total += v["total"]
                wins += v["wins"]
        if total >= 12:
            return beta_mean(wins, total, 0.50, CONTEXT_PRIOR_N)
        return 0.50

    def update(self, model, regime, arr, correct):
        key = self.make_key(model, regime, arr)
        if key not in self.stats:
            self.stats[key] = {"total": 0, "wins": 0}
        self.stats[key]["total"] += 1
        self.stats[key]["wins"] += int(correct)
        self.db.save_context(key, self.stats[key])


# ============================================================
# FUSION
# ============================================================

class Fusion:
    def __init__(self, reliability, context):
        self.rel = reliability
        self.ctx = context

    def discount_correlated(self, probs):
        out = {}
        for m, p in probs.items():
            penalty = 0.0
            for other in probs:
                if m == other:
                    continue
                corr = self.rel.error_corr(m, other)
                if corr > 0.30:
                    penalty += corr
            discount = 1.0 / (1.0 + 0.12 * penalty)
            out[m] = 0.50 + (p - 0.50) * discount
        return out

    def groups(self, probs, regime, arr):
        buckets = defaultdict(list)
        for model, p in probs.items():
            buckets[MODEL_GROUP[model]].append((model, p))
        group_probs = {}
        group_weights = {}
        for group, items in buckets.items():
            num = 0.0
            den = 0.0
            for model, p in items:
                mw = self.rel.weight(model)
                cw = self.ctx.reliability(model, regime, arr)
                context_factor = 0.5 + abs(cw - 0.5) * 2.0
                w = mw * context_factor
                num += safe_logit(p) * w
                den += w
            gp = sigmoid(num / den) if den else 0.50
            group_probs[group] = clamp(gp, 0.05, 0.95)
            group_weights[group] = den / max(1, len(items))
        return group_probs, group_weights


# ============================================================
# META LEARNER
# ============================================================

class MetaLearner:
    def __init__(self, db):
        self.db = db
        self.features = list(MODEL_GROUP.keys()) + [
            "regime_age", "regime_transition",
            "acf1", "acf2", "acf3", "stability", "disagreement",
        ]
        saved = db.load_meta("weights")
        if isinstance(saved, dict):
            self.bias = float(saved.get("_bias", 0))
            self.weights = {f: float(saved.get(f, 0)) for f in self.features}
        else:
            self.bias = 0.0
            self.weights = {f: 0.0 for f in self.features}

    def predict(self, x):
        z = self.bias
        for f in self.features:
            z += self.weights[f] * x.get(f, 0.0)
        return sigmoid(z)

    def update(self, x, target):
        p = self.predict(x)
        err = p - target
        self.bias -= LEARNING_RATE * err
        for f in self.features:
            value = x.get(f, 0.0)
            grad = err * value + L2_PENALTY * self.weights[f]
            self.weights[f] -= LEARNING_RATE * grad
        state = dict(self.weights)
        state["_bias"] = self.bias
        self.db.save_meta("weights", state)


# ============================================================
# CALIBRATION
# ============================================================

class Calibration:
    def __init__(self, db):
        self.db = db
        self.stats = db.load_calibration()

    @staticmethod
    def bucket(confidence):
        confidence = clamp(confidence, 0.50, 0.95)
        idx = int((confidence - 0.50) / 0.05)
        idx = min(idx, 8)
        lo = 0.50 + idx * 0.05
        hi = lo + 0.05
        return f"{lo:.2f}-{hi:.2f}"

    def calibrate(self, raw):
        direction = "Big" if raw >= 0.50 else "Small"
        conf = raw if direction == "Big" else 1.0 - raw
        bucket = self.bucket(conf)
        s = self.stats.get(bucket, {"total": 0, "wins": 0})
        empirical = beta_mean(s["wins"], s["total"], 0.50, PRIOR_N)
        n_factor = min(1.0, s["total"] / 100.0)
        calibrated_conf = conf * (1 - 0.60 * n_factor) + empirical * (0.60 * n_factor)
        calibrated_conf = clamp(calibrated_conf, 0.50, 0.95)
        return calibrated_conf if direction == "Big" else 1.0 - calibrated_conf

    def update(self, probability, actual):
        direction = "Big" if probability >= 0.50 else "Small"
        conf = probability if direction == "Big" else 1.0 - probability
        bucket = self.bucket(conf)
        if bucket not in self.stats:
            self.stats[bucket] = {"total": 0, "wins": 0}
        self.stats[bucket]["total"] += 1
        self.stats[bucket]["wins"] += int(direction == actual)
        self.db.save_calibration(bucket, self.stats[bucket])


# ============================================================
# SIGNAL FILTER
# ============================================================

class SignalFilter:
    def decide(self, probability, groups, regime):
        direction = "Big" if probability >= 0.50 else "Small"
        confidence = probability if direction == "Big" else 1.0 - probability
        values = list(groups.values())
        if values:
            agreement = sum(
                int((p >= 0.50) == (direction == "Big"))
                for p in values
            ) / len(values)
        else:
            agreement = 0.0
        disagreement = 1.0 - agreement
        ent = entropy_binary(probability)

        if confidence < REJECT_CONF:
            state = "REJECTED"
        elif disagreement >= 0.50:
            state = "SHADOW"
        elif regime["transition"]:
            state = "LIVE" if confidence >= 0.62 else "SHADOW"
        elif confidence >= MIN_LIVE_CONF and disagreement <= 0.35:
            state = "LIVE"
        else:
            state = "SHADOW"

        return state, disagreement, ent


# ============================================================
# LOSS CLASSIFIER
# ============================================================

class LossClassifier:
    @staticmethod
    def classify(prediction, actual, regime_name, models):
        if prediction == actual:
            return "WIN"
        wrong = [m for m, p in models.items() if (p >= 0.5) != (actual == "Big")]
        n_wrong = len(wrong)
        n_total = len(models)
        if regime_name in ("CHAOS", "MIXED"):
            return "WRONG_REGIME"
        if n_wrong >= n_total * 0.7:
            return "MODEL_FAILURE"
        if any("markov" in m for m in wrong):
            return "MARKOV_FAILURE"
        if any("streak" in m for m in wrong):
            return "STREAK_FAILURE"
        if any("transition" in m for m in wrong):
            return "TRANSITION_FAILURE"
        if any("mirror" in m or "repeat" in m for m in wrong):
            return "SEQUENCE_FAILURE"
        return "OTHER"


# ============================================================
# MAIN ENGINE
# ============================================================

class HybridEngineV86:
    def __init__(self):
        self.db = Database()
        self.models = BaseModels()
        self.regime = RegimeEngine()
        self.reliability = Reliability(self.db)
        self.context = Context(self.db)
        self.fusion = Fusion(self.reliability, self.context)
        self.meta = MetaLearner(self.db)
        self.calibration = Calibration(self.db)
        self.filter = SignalFilter()
        self.last_prediction = None
        self.lock = threading.RLock()

    def predict_next(self, source_period=None, target_period=None):
        with self.lock:
            arr = self.db.history()
            if len(arr) < MIN_HISTORY:
                return {"status": "WAIT", "reason": f"Need {MIN_HISTORY}; have {len(arr)}"}

            regime = self.regime.detect(arr)
            base = self.models.predict(arr)
            discounted = self.fusion.discount_correlated(base)
            groups, group_weights = self.fusion.groups(discounted, regime["name"], arr)
            group_values = list(groups.values())
            group_mean = sum(group_values) / len(group_values) if group_values else 0.50

            preliminary_direction = "Big" if group_mean >= 0.50 else "Small"
            agreement = sum(
                int((p >= 0.50) == (preliminary_direction == "Big"))
                for p in group_values
            ) / len(group_values) if group_values else 0
            disagreement = 1.0 - agreement

            features = {}
            for model in MODEL_GROUP:
                features[model] = discounted.get(model, 0.50) - 0.50
            features["regime_age"] = clamp(regime["age"] / 20.0, 0, 1)
            features["regime_transition"] = float(regime["transition"])
            features["acf1"] = regime["acf1"]
            features["acf2"] = regime["acf2"]
            features["acf3"] = regime["acf3"]
            features["stability"] = regime["stability"]
            features["disagreement"] = disagreement

            meta_prob = self.meta.predict(features)
            raw = 0.65 * meta_prob + 0.35 * group_mean
            raw = clamp(raw, 0.05, 0.95)
            calibrated = self.calibration.calibrate(raw)

            if regime["transition"]:
                calibrated = 0.50 + (calibrated - 0.50) * 0.50

            state, disagreement, ent = self.filter.decide(calibrated, groups, regime)
            prediction = "Big" if calibrated >= 0.50 else "Small"
            confidence = calibrated if prediction == "Big" else 1.0 - calibrated

            payload = {
                "status": "OK",
                "prediction": prediction,
                "raw_probability": raw,
                "calibrated_probability": calibrated,
                "confidence": confidence,
                "state": state,
                "regime": regime["name"],
                "regime_age": regime["age"],
                "transition": regime["transition"],
                "entropy": ent,
                "disagreement": disagreement,
                "models": base,
                "discounted_models": discounted,
                "groups": groups,
                "group_weights": group_weights,
                "features": features,
                "source_period": source_period or self.db.last_period(),
                "target_period": target_period,
            }

            if state in ("LIVE", "SHADOW"):
                payload["prediction_id"] = self.db.save_prediction(payload)
            else:
                payload["prediction_id"] = None

            self.last_prediction = payload
            return payload

    def evaluate_last(self, actual):
        with self.lock:
            p = self.last_prediction
            if not p:
                return None
            if p["state"] not in ("LIVE", "SHADOW"):
                self.last_prediction = None
                return None

            correct = int(p["prediction"] == actual)
            self.db.evaluate_prediction(p.get("prediction_id"), actual)
            self.meta.update(p["features"], result_value(actual))
            self.calibration.update(p["calibrated_probability"], actual)

            arr = self.db.history()

            for model, probability in p["models"].items():
                sub_pred = "Big" if probability >= 0.50 else "Small"
                model_correct = sub_pred == actual
                self.reliability.update(model, sub_pred, actual)
                self.context.update(model, p["regime"], arr, model_correct)

            old_groups = self.db.load_groups()
            for group, probability in p["groups"].items():
                if group not in old_groups:
                    old_groups[group] = {"total": 0, "wins": 0}
                s = old_groups[group]
                s["total"] += 1
                s["wins"] += int(
                    ("Big" if probability >= 0.50 else "Small") == actual
                )
                self.db.save_group(group, s)

            if not correct:
                loss_type = LossClassifier.classify(
                    p["prediction"], actual, p["regime"], p["models"]
                )
                self.db.save_loss({
                    "source_period": p.get("source_period"),
                    "prediction": p["prediction"],
                    "actual": actual,
                    "regime": p["regime"],
                    "loss_type": loss_type,
                    "confidence": p["confidence"],
                    "models": p["models"],
                })

            result = {
                "prediction": p["prediction"],
                "actual": actual,
                "correct": correct,
                "state": p["state"],
                "confidence": p["confidence"],
            }
            self.last_prediction = None
            return result


# ============================================================
# API CLIENT (V8.6 — Multi-structure support)
# ============================================================

def fetch_api_raw():
    """Fetch raw API response — returns (status_code, raw_text, parsed_json)"""
    headers = {
        "User-Agent": "Mozilla/5.0",
        "accept": "application/json, text/plain, */*",
        "content-type": "application/json;charset=UTF-8",
    }
    if API_AUTH:
        headers["Authorization"] = f"Bearer {API_AUTH}"
    if API_ORIGIN:
        headers["Origin"] = API_ORIGIN
    if API_REFERER:
        headers["Referer"] = API_REFERER

    payload = {
        "typeId": API_TYPE_ID,
        "pageSize": API_PAGE_SIZE,
        "pageNo": 1,
        "language": API_LANGUAGE,
        "timestamp": int(time.time()),
    }
    if API_RANDOM:
        payload["random"] = API_RANDOM
    if API_SIGNATURE:
        payload["signature"] = API_SIGNATURE

    r = requests.post(API_URL, json=payload, headers=headers, timeout=REQUEST_TIMEOUT)
    raw = r.text
    try:
        parsed = r.json()
    except Exception:
        parsed = None
    return r.status_code, raw, parsed


def extract_rows(data):
    """V8.6 — Try multiple paths to find the list"""
    if not isinstance(data, dict):
        if isinstance(data, list):
            return data
        return []

    # Path 1: data.list
    if isinstance(data.get("data"), dict):
        d = data["data"]
        for key in ("list", "rows", "items", "results", "data"):
            if isinstance(d.get(key), list):
                return d[key]

    # Path 2: data as list
    if isinstance(data.get("data"), list):
        return data["data"]

    # Path 3: rows / list / items at top
    for key in ("list", "rows", "items", "results", "data"):
        if isinstance(data.get(key), list):
            return data[key]

    # Path 4: result.list
    if isinstance(data.get("result"), dict):
        r = data["result"]
        for key in ("list", "rows", "items"):
            if isinstance(r.get(key), list):
                return r[key]

    return []


def fetch_api():
    """V8.6 — Returns extracted rows"""
    _, _, parsed = fetch_api_raw()
    if parsed is None:
        return []
    return extract_rows(parsed)


def parse_row(row):
    period = (
        row.get("issueNumber") or row.get("period")
        or row.get("issue") or row.get("periodNumber")
        or row.get("PreIssue") or row.get("expect")
    )
    number = (
        row.get("number") or row.get("result") or row.get("openNumber")
        or row.get("num") or row.get("PreNum")
    )
    if period is None or number is None:
        return None
    try:
        period = str(period)
        number = int(number)
    except Exception:
        return None
    result = "Big" if number >= 5 else "Small"
    return period, number, result


def apply_offset(raw_period):
    try:
        return str(int(str(raw_period)) + PERIOD_OFFSET)
    except Exception:
        return str(raw_period)


# ============================================================
# TELEGRAM
# ============================================================

def telegram(text):
    if not TELEGRAM_TOKEN or not CHAT_ID:
        return False
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        r = requests.post(url, json={
            "chat_id": CHAT_ID,
            "text": text,
            "parse_mode": "HTML",
        }, timeout=REQUEST_TIMEOUT)
        return r.status_code == 200
    except Exception as e:
        log(f"[TG ERROR] {e}")
        return False


def signal_text(p):
    return (
        "🎯 <b>HYBRID V8.6</b>\n"
        "━━━━━━━━━━━━━━━━\n"
        f"📅 Target: <code>{p.get('target_period', 'N/A')}</code>\n"
        f"🎲 Prediction: <b>{p['prediction']}</b>\n"
        f"📊 Confidence: <b>{p['confidence']:.2%}</b>\n"
        f"📈 Raw: {p['raw_probability']:.2%}\n"
        f"🎯 Calibrated: {p['calibrated_probability']:.2%}\n"
        f"🏷 State: <b>{p['state']}</b>\n"
        f"🧠 Regime: {p['regime']}"
    )


# ============================================================
# POLLING WORKER
# ============================================================

def polling_worker(agent):
    log("[POLLING] Worker STARTED")
    iteration = 0

    while True:
        iteration += 1
        try:
            rows = fetch_api()
            if iteration <= 3:
                log(f"[POLLING] #{iteration} Got {len(rows)} rows")

            parsed = []
            for row in rows:
                item = parse_row(row)
                if item:
                    raw_period, number, result = item
                    period = apply_offset(raw_period)
                    parsed.append((period, number, result))

            try:
                parsed.sort(key=lambda x: int(x[0]))
            except Exception:
                parsed.reverse()

            new_count = 0
            for period, number, result in parsed:
                if agent.db.has_period(period):
                    continue
                new_count += 1
                log(f"[SYNC] {period} → {result}")

                evaluation = agent.evaluate_last(result)
                if evaluation:
                    status = "WIN" if evaluation["correct"] else "LOSS"
                    log(f"[RESULT] {period} {result} {status}")

                agent.db.save_result(period, number, result)
                prediction = agent.predict_next(source_period=period)

                if prediction.get("status") == "OK":
                    log(f"[SIGNAL] {prediction['prediction']} {prediction['confidence']:.2%} {prediction['state']}")
                    if prediction["state"] == "LIVE":
                        telegram(signal_text(prediction))
                elif prediction.get("status") == "WAIT":
                    if iteration % 30 == 0:
                        log(f"[WAIT] {prediction.get('reason')}")

            if new_count == 0 and iteration % 30 == 0:
                log(f"[POLLING] #{iteration} No new periods (history: {len(agent.db.history())})")

        except Exception as e:
            log(f"[POLL ERROR] {type(e).__name__}: {e}")
            log(traceback.format_exc())

        time.sleep(POLL_SECONDS)


# ============================================================
# TELEGRAM COMMANDS
# ============================================================

def poll_telegram_commands(agent):
    if not ALLOW_TELEGRAM_COMMANDS or not TELEGRAM_TOKEN or not CHAT_ID:
        return
    log("[TG CMD] Command listener started")
    try:
        requests.get(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/deleteWebhook",
            params={"drop_pending_updates": True}, timeout=10
        )
    except Exception:
        pass

    offset = 0
    while True:
        try:
            r = requests.get(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates",
                params={"offset": offset, "timeout": 20}, timeout=25
            )
            if r.status_code != 200:
                time.sleep(2)
                continue
            for u in r.json().get("result", []):
                offset = u["update_id"] + 1
                msg = u.get("message") or u.get("edited_message") or {}
                if str(msg.get("chat", {}).get("id", "")) != str(CHAT_ID):
                    continue
                txt = str(msg.get("text", "")).strip().lower()

                if txt == "/status":
                    rep = agent.db.report()
                    lines = [
                        "🚀 <b>HYBRID V8.6</b>\n",
                        f"DB: <code>{DB_PATH}</code>",
                        f"History: {len(agent.db.history())}",
                        f"Predicted: {rep['total']}",
                        f"WR: <b>{rep['wr']*100:.2f}%</b>" if rep['wr'] else "WR: N/A",
                        f"LIVE: {rep['live_total']}",
                    ]
                    telegram("\n".join(lines))
                elif txt == "/help":
                    telegram(
                        "🤖 <b>V8.6 COMMANDS</b>\n"
                        "/status /help"
                    )
        except Exception as e:
            log(f"[TG CMD ERROR] {e}")
        time.sleep(1)


# ============================================================
# DASHBOARD
# ============================================================

@app.route("/")
def dashboard():
    if not global_agent:
        return "Engine initializing..."
    p = global_agent.last_prediction
    report = global_agent.db.report()
    last_rows = global_agent.db.get_last_rows(40)
    return render_template_string("""
<!doctype html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="refresh" content="15">
<title>HYBRID V8.6</title>
<style>
body{background:#0f172a;color:#f8fafc;font-family:system-ui,Arial,sans-serif;padding:20px;margin:0}
h1{color:#22d3ee;margin:0 0 6px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:10px;margin:14px 0}
.card{background:#1e293b;padding:14px;border-radius:10px;margin-bottom:12px}
.big{font-size:26px;font-weight:800}
.green{color:#4ade80}.cyan{color:#22d3ee}.yellow{color:#facc15}
.mono{font-family:monospace;letter-spacing:2px}
</style>
</head>
<body>
<h1>🚀 HYBRID V8.6</h1>
<div class="grid">
<div class="card"><div>Evaluated</div><div class="big">{{ report.total }}</div></div>
<div class="card"><div>History</div><div class="big yellow">{{ last_rows|length }}</div></div>
<div class="card"><div>LIVE</div><div class="big cyan">{{ report.live_total }}</div></div>
</div>
<div class="card">
<h3>Latest</h3>
{% if p %}<p>{{ p.prediction }} — {{ "%.2f"|format(p.confidence*100) }}% [{{ p.state }}]</p>
{% else %}<p>No signal yet.</p>{% endif %}
</div>
<div class="card">
<h3>Last 40</h3>
<div class="mono">{% for r in last_rows %}{{ "B" if r.result=="Big" else "S" }}{% endfor %}</div>
</div>
</body>
</html>
""", p=p, report=report, last_rows=last_rows)


@app.route("/api/status")
def api_status():
    if not global_agent:
        return jsonify({"status": "initializing"})
    return jsonify({
        "prediction": global_agent.last_prediction,
        "report": global_agent.db.report(),
        "history_count": len(global_agent.db.history()),
    })


@app.route("/api/debug")
def api_debug():
    """V8.6 — Full raw API response debug"""
    if not global_agent:
        return jsonify({"status": "no_agent"})

    result = {}
    try:
        status_code, raw_text, parsed_json = fetch_api_raw()
        result["status_code"] = status_code
        result["raw_text"] = raw_text[:3000]
        result["parsed_json"] = parsed_json

        # Try all extraction paths
        if parsed_json:
            result["top_level_keys"] = list(parsed_json.keys()) if isinstance(parsed_json, dict) else "not_dict"
            
            # Try each path
            extraction_attempts = {}
            
            if isinstance(parsed_json, dict):
                if "data" in parsed_json:
                    d = parsed_json["data"]
                    extraction_attempts["data_type"] = type(d).__name__
                    if isinstance(d, dict):
                        extraction_attempts["data_keys"] = list(d.keys())
                        for key in ("list", "rows", "items", "results", "data"):
                            if key in d:
                                val = d[key]
                                extraction_attempts[f"data.{key}"] = {
                                    "type": type(val).__name__,
                                    "len": len(val) if isinstance(val, (list, dict)) else None,
                                }
                    elif isinstance(d, list):
                        extraction_attempts["data_is_list"] = {"len": len(d)}
                
                if "result" in parsed_json:
                    r = parsed_json["result"]
                    extraction_attempts["result_type"] = type(r).__name__
                    if isinstance(r, dict):
                        extraction_attempts["result_keys"] = list(r.keys())
                
                for key in ("list", "rows", "items", "results", "code", "msg", "message"):
                    if key in parsed_json:
                        extraction_attempts[f"top.{key}"] = parsed_json[key] if not isinstance(parsed_json[key], (list, dict)) else f"{type(parsed_json[key]).__name__}"

            result["extraction_attempts"] = extraction_attempts
            
            # Actually try to extract
            rows = extract_rows(parsed_json)
            result["extracted_rows_count"] = len(rows)
            if rows:
                result["first_row"] = rows[0]
                result["first_row_keys"] = list(rows[0].keys()) if isinstance(rows[0], dict) else "not_dict"

    except Exception as e:
        result["error"] = f"{type(e).__name__}: {e}"
        result["traceback"] = traceback.format_exc()

    return jsonify({
        "result": result,
        "config": {
            "API_URL": API_URL,
            "API_TYPE_ID": API_TYPE_ID,
            "API_PAGE_SIZE": API_PAGE_SIZE,
            "API_LANGUAGE": API_LANGUAGE,
            "PERIOD_OFFSET": PERIOD_OFFSET,
        }
    })


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":
    log("=" * 60)
    log(" HYBRID ENGINE V8.6 STARTING")
    log("=" * 60)
    log(f"DB: {DB_PATH}")
    log(f"API: {API_URL}")
    log(f"API_TYPE_ID: {API_TYPE_ID}")
    log(f"API_PAGE_SIZE: {API_PAGE_SIZE}")
    log(f"TELEGRAM_TOKEN set: {bool(TELEGRAM_TOKEN)} (len={len(TELEGRAM_TOKEN)})")
    log(f"CHAT_ID set: {bool(CHAT_ID)}")
    log(f"API_AUTH set: {bool(API_AUTH)} (len={len(API_AUTH)})")
    log("=" * 60)

    # Startup API test
    log("[STARTUP] Testing API...")
    try:
        status_code, raw_text, parsed = fetch_api_raw()
        log(f"[STARTUP] API status_code: {status_code}")
        log(f"[STARTUP] Raw text (first 500): {raw_text[:500]}")
        if parsed:
            log(f"[STARTUP] Top-level keys: {list(parsed.keys()) if isinstance(parsed, dict) else type(parsed).__name__}")
            rows = extract_rows(parsed)
            log(f"[STARTUP] Extracted rows: {len(rows)}")
            if rows:
                log(f"[STARTUP] First row: {rows[0]}")
    except Exception as e:
        log(f"[STARTUP API ERROR] {type(e).__name__}: {e}")
        log(traceback.format_exc())

    # Send Telegram startup
    telegram(
        "🚀 <b>V8.6 STARTED</b>\n"
        f"API test: check /api/debug"
    )

    global_agent = HybridEngineV86()

    threading.Thread(target=polling_worker, args=(global_agent,), daemon=True).start()
    threading.Thread(target=poll_telegram_commands, args=(global_agent,), daemon=True).start()

    log("[STARTUP] Starting Flask on port " + str(PORT))
    app.run(host="0.0.0.0", port=PORT, debug=False)
