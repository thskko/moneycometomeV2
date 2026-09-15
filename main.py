import requests
import time
import os
import math
import sqlite3
import threading
from collections import deque, Counter, defaultdict
from datetime import datetime
from flask import Flask, jsonify

# ==========================================
# CONFIG
# ==========================================
TELEGRAM_TOKEN = "8913070806:AAF3rP0zKJtofE-5KVesqcdoHzn7Go0avho"
CHAT_ID = "-1004402480797"

API_URL = "https://6lotteryapi.com/api/webapi/GetNoaverageEmerdList"
API_AUTH = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpYXQiOiIxNzg3OTgxNTA5IiwibmJmIjoiMTc4Nzk4MTUwOSIsImV4cCI6IjE3ODc5ODMzMDkiLCJodHRwOi8vc2NoZW1hcy5taWNyb3NvZnQuY29tL3dzLzIwMDgvMDYvaWRlbnRpdHkvY2xhaW1zL2V4cGlyYXRpb24iOiI4LzI5LzIwMjYgMTI6MzE2NDkgUE0iLCJodHRwOi8vc2NoZW1hcy5taWNyb3NvZnQuY29tL3dzLzIwMDgvMDYvaWRlbnRpdHkvY2xhaW1zL3JvbGUiOiJBY2Nlc3NfVG9rZW4iLCJVc2VySWQiOiIxMDEyMjEzIiwiVXNlck5hbWUiOiI5NTk3NDA5MzkzNzAiLCJVc2VyUGhvdG8iOiI5IiwiTmlja05hbWUiOiJUaGVrR3lpIiwiQW1vdW50IjoiODcuMzAiLCJJbnRlZ3JhbCI6IjAiLCJMb2dpbk1hcmsiOiJINSIsImxvZ2luVGltZSI6IjcvMjkvMjAyNiAxMjowMTo0OSBQTSIsImxvZ2luSVBBZGRyZXNzIjoiNDUuNDEuMTA0LjI0MCIsImRiTnVtYmVyIjoiMCIsIklzdmFsaWRhdG9yIjoiMCIsIktleUNvZGUiOiIzMjMzMiIsImRva2VuVHlwZSI6IjJBY2Nlc3NfVG9rZW4iLCJob25lVHlwZSI6IjAiLCJVc2VyVHlwZSI6IjAiLCJVc2VyTmFtZ2UiOiIuIiwiaXNzIjoiand0SXNzdWVyIiwiYXVkIjoibG90dGVyeVRpY2tldCJ9.ZL0Y9gexUTCsKwWeZhCLAAw8AABEYJt0GnIzIviMG4g"

BASE_BET = 1.0

app = Flask(__name__)
global_agent = None


# ==========================================
# 📊 DASHBOARD
# ==========================================
@app.route('/')
def home():
    global global_agent
    if not global_agent:
        return "<h3>🚀 HYBRID v4.4.4 starting...</h3>"
    
    a = global_agent
    total = a.total_wins + a.total_losses
    wr = (a.total_wins / total * 100) if total > 0 else 0.0
    win3 = a.get_win3_rate()
    
    last_20 = " ".join([("B" if r == "Big" else "S") for r in list(a.history)[-20:]])
    
    pat_rows = ""
    for k, v in sorted(a.pattern_wr.items(), key=lambda x: x[1], reverse=True)[:12]:
        t = a.pattern_total[k]
        acc_wr = a.get_accelerated_wr(k)
        pat_rows += f"<tr><td>{k}</td><td>{v*100:.0f}%</td><td>{acc_wr*100:.0f}%</td><td>{t}</td></tr>"
    
    return f"""
    <html><head><title>HYBRID v4.4.4</title>
    <meta http-equiv="refresh" content="15">
    <style>
    body{{background:#0a0e27;color:#0ff;font-family:monospace;padding:20px}}
    h1{{color:#0ff;text-shadow:0 0 10px #0ff}}
    .box{{background:#1a1f3a;border:1px solid #0ff;padding:15px;margin:10px 0;border-radius:8px}}
    .big{{font-size:32px;color:#0f0;font-weight:bold}}
    .nums{{font-size:18px;color:#ff0;letter-spacing:3px}}
    table{{width:100%;border-collapse:collapse}}
    th,td{{padding:6px;border:1px solid #0ff;text-align:left;font-size:12px}}
    th{{background:#0ff;color:#000}}
    </style></head><body>
    <h1>🚀 HYBRID v4.4.4</h1>
    
    <div class="box">
      <h2>📊 Performance</h2>
      <p>Status: <b>{'PAUSED 🛑' if a.is_paused else 'RUNNING 🟢'}</b></p>
      <p>Signals: {a.total_signals} | Skips: {a.total_skips}</p>
      <p>W: {a.total_wins} | L: {a.total_losses}</p>
      <p>Win Rate: <span class="big">{wr:.2f}%</span></p>
      <p>Win3: <span class="big">{win3:.1f}%</span></p>
      <p>Step: {a.current_step + 1} ({2**a.current_step}x)</p>
      <p>Vol: {a.volatility_index:.2f}</p>
    </div>
    
    <div class="box">
      <h2>💰 Martingale</h2>
      <p>Base Bet: <b>${BASE_BET:.2f}</b></p>
      <p>Current Step: <b>{a.current_step + 1}</b></p>
      <p>Next Bet: <b>${BASE_BET * (2**a.current_step):.2f}</b></p>
    </div>
    
    <div class="box">
      <h2>🎯 Last 20</h2>
      <p class="nums">{last_20}</p>
    </div>
    
    <div class="box">
      <h2>📈 Patterns</h2>
      <table>
        <tr><th>Pattern</th><th>All WR</th><th>Accel WR</th><th>Count</th></tr>
        {pat_rows}
      </table>
    </div>
    
    <div class="box">
      <h2>📅 Last Period</h2>
      <p>{a.last_period} → {a.last_number} → {a.last_result}</p>
      <p>Signal: {a.last_signal}</p>
    </div>
    </body></html>
    """


# ==========================================
# ONLINE LEARNER
# ==========================================
class OnlineLearner:
    def __init__(self, lr=0.05):
        self.weights = defaultdict(lambda: 1.0)
        self.lr = lr
    
    def update(self, pattern_name, was_correct):
        if was_correct:
            self.weights[pattern_name] += self.lr
        else:
            self.weights[pattern_name] -= self.lr
        self.weights[pattern_name] = max(0.3, min(2.0, self.weights[pattern_name]))
    
    def get_weight(self, pattern_name):
        return self.weights[pattern_name]


# ==========================================
# DATA ENGINE
# ==========================================
class DataEngine:
    def __init__(self, db_path='wingo_v444.db'):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.cursor = self.conn.cursor()
        
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                period TEXT UNIQUE,
                number INTEGER,
                result TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS pattern_stats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pattern TEXT,
                signal TEXT,
                actual TEXT,
                win INTEGER,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        self.conn.commit()
    
    def save_result(self, period, number, result):
        try:
            self.cursor.execute(
                'INSERT OR IGNORE INTO history (period, number, result) VALUES (?, ?, ?)',
                (str(period), number, result)
            )
            self.conn.commit()
        except Exception as e:
            print(f"DB Save Err: {e}", flush=True)
    
    def save_pattern_stat(self, pattern, signal, actual, win):
        try:
            self.cursor.execute('''
                INSERT INTO pattern_stats (pattern, signal, actual, win)
                VALUES (?, ?, ?, ?)
            ''', (pattern, signal, actual, 1 if win else 0))
            self.conn.commit()
        except Exception as e:
            print(f"DB Pattern Err: {e}", flush=True)
    
    def get_history(self, limit=500):
        try:
            self.cursor.execute(
                'SELECT result FROM history ORDER BY id DESC LIMIT ?',
                (limit,)
            )
            return [row[0] for row in self.cursor.fetchall()][::-1]
        except:
            return []


# ==========================================
# 🚀 HYBRID v4.4.4 ENGINE
# ==========================================
class HybridEngineV444:
    def __init__(self):
        global global_agent
        global_agent = self
        
        self.data_engine = DataEngine()
        self.history = deque(maxlen=500)
        self.load_history_from_db()
        
        self.online_learner = OnlineLearner(lr=0.05)
        
        # State
        self.current_step = 0
        self.active_prediction = None
        self.active_patterns_used = []
        self.active_bayesian = 0
        self.is_paused = False
        self.consecutive_losses = 0
        self.consecutive_wins = 0
        self.trap_count = 0
        
        self.last_period = "None"
        self.last_number = 0
        self.last_result = "None"
        self.last_signal = "None"
        self.last_reason = "None"
        
        # Stats
        self.total_signals = 0
        self.total_wins = 0
        self.total_losses = 0
        self.total_skips = 0
        self.win_by_step = {0: 0, 1: 0, 2: 0, 3: 0}
        
        # Pattern
        self.pattern_stats = Counter()
        self.pattern_wr = defaultdict(lambda: 0.5)
        self.pattern_win = defaultdict(int)
        self.pattern_total = defaultdict(int)
        self.pattern_weight = defaultdict(lambda: 1.0)
        self.pattern_recent = defaultdict(lambda: deque(maxlen=100))
        
        # Volatility
        self.volatility_index = 0.5
    
    def load_history_from_db(self):
        hist = self.data_engine.get_history(500)
        for r in hist:
            self.history.append(r)
        print(f"📁 Loaded {len(self.history)} from DB", flush=True)
    
    def send_telegram(self, message):
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {"chat_id": CHAT_ID, "text": message, "parse_mode": "HTML"}
        try:
            r = requests.post(url, json=payload, timeout=10)
            print(f"📤 TG: {r.status_code}", flush=True)
        except Exception as e:
            print(f"❌ TG: {e}", flush=True)
    
    # =========================================================
    # ACCELERATED WR
    # =========================================================
    def get_accelerated_wr(self, pattern_name):
        recent = list(self.pattern_recent[pattern_name])
        if len(recent) < 5:
            return self.pattern_wr[pattern_name]
        
        last5 = recent[-5:]
        last10 = recent[-10:] if len(recent) >= 10 else recent
        last20 = recent[-20:] if len(recent) >= 20 else recent
        
        wr5 = sum(last5) / len(last5) if last5 else 0.5
        wr10 = sum(last10) / len(last10) if last10 else 0.5
        wr20 = sum(last20) / len(last20) if last20 else 0.5
        
        return wr5 * 0.6 + wr10 * 0.3 + wr20 * 0.1
    
    def time_decay_weight(self, pattern_name):
        recent = list(self.pattern_recent[pattern_name])
        if len(recent) < 3:
            return 1.0
        recent = recent[-20:]
        weights = [0.9 ** i for i in range(len(recent) - 1, -1, -1)]
        weighted_wr = sum(w * r for w, r in zip(weights, recent)) / sum(weights)
        return max(0.3, min(2.0, weighted_wr / 0.5))
    
    def calculate_volatility(self):
        if len(self.history) < 20:
            self.volatility_index = 0.5
            return 0.5
        arr = list(self.history)
        alt = sum(1 for i in range(-20, -1) if arr[i] != arr[i+1])
        self.volatility_index = alt / 19
        return self.volatility_index
    
    def trap_filter(self, arr):
        if len(arr) < 15: return False
        
        last10 = arr[-10:]
        b10 = last10.count("Big")
        
        if 4 <= b10 <= 6:
            self.trap_count += 1
            if self.trap_count >= 3:
                self.trap_count = 0
                return False
            return True
        else:
            self.trap_count = 0
            return False
    
    def correlation_filter(self, patterns):
        if len(patterns) < 4:
            return False
        
        big_signals = [p for p in patterns if p[0] == "Big"]
        small_signals = [p for p in patterns if p[0] == "Small"]
        
        strong_big = [p for p in big_signals if p[1] >= 80]
        strong_small = [p for p in small_signals if p[1] >= 80]
        
        if len(strong_big) >= 3 and len(strong_small) >= 3:
            return True
        
        if len(big_signals) >= 5 and len(small_signals) >= 5:
            big_total = sum(p[1] for p in big_signals)
            small_total = sum(p[1] for p in small_signals)
            if abs(big_total - small_total) < 30:
                return True
        
        return False
    
    def multi_layer_confirm(self, arr):
        layer1 = self.p_frequency(arr)
        layer2 = self.p_markov2(arr)
        layer3 = self.p_mean_reversion(arr)
        
        signals = [s for s, _, _ in [layer1, layer2, layer3] if s]
        
        if len(signals) == 3 and len(set(signals)) == 1:
            return signals[0], 95, "🎯 Multi-Layer"
        
        return None, 0, "Multi-Layer"
    
    def bias_conflict_filter(self, arr, signal):
        if len(arr) < 50:
            return 1.0
        
        recent_bias = arr[-50:].count("Big") / 50
        
        if signal == "Big" and recent_bias < 0.35:
            return 0.65
        if signal == "Small" and recent_bias > 0.65:
            return 0.65
        if signal == "Big" and recent_bias > 0.65:
            return 1.15
        if signal == "Small" and recent_bias < 0.35:
            return 1.15
        
        return 1.0
    
    def bayesian_inference(self, patterns):
        log_big = math.log(0.5)
        log_small = math.log(0.5)
        
        for pat_name, sig, conf in patterns:
            wr = self.get_accelerated_wr(pat_name)
            wr = max(0.1, min(0.9, wr))
            
            if sig == "Big":
                log_big += math.log(wr)
                log_small += math.log(1 - wr)
            else:
                log_small += math.log(wr)
                log_big += math.log(1 - wr)
        
        max_log = max(log_big, log_small)
        p_big = math.exp(log_big - max_log)
        p_small = math.exp(log_small - max_log)
        posterior_big = p_big / (p_big + p_small)
        
        if posterior_big >= 0.5:
            return "Big", posterior_big * 100
        else:
            return "Small", (1 - posterior_big) * 100
    
    def adapt_by_volatility(self, patterns, vol):
        adjusted = []
        for sig, conf, pat_name in patterns:
            if sig is None: continue
            
            if vol > 0.7:
                if pat_name in ["mean_rev", "extreme20", "zone", "mtf", "dgap"]:
                    conf = min(95, conf * 1.3)
                elif pat_name in ["markov2", "cycle", "alt", "pingpong"]:
                    conf *= 0.7
            elif vol < 0.3:
                if pat_name in ["dragon_mo", "freq", "markov4", "markov3"]:
                    conf = min(95, conf * 1.3)
                elif pat_name in ["mean_rev", "break3"]:
                    conf *= 0.8
            
            adjusted.append((sig, conf, pat_name))
        return adjusted
    
    # =========================================================
    # PATTERNS
    # =========================================================
    def p_extreme_20(self, arr):
        if len(arr) < 20: return None, 0, "extreme20"
        b20 = arr[-20:].count("Big")
        if b20 >= 18: return "Small", 92, "extreme20"
        if b20 <= 2: return "Big", 92, "extreme20"
        if b20 >= 17: return "Small", 88, "extreme20"
        if b20 <= 3: return "Big", 88, "extreme20"
        return None, 0, "extreme20"
    
    def p_mean_reversion(self, arr):
        if len(arr) < 15: return None, 0, "mean_rev"
        b15 = arr[-15:].count("Big")
        b10 = arr[-10:].count("Big")
        if b15 >= 13: return "Small", 88, "mean_rev"
        if b15 <= 2: return "Big", 88, "mean_rev"
        if b15 >= 12: return "Small", 85, "mean_rev"
        if b15 <= 3: return "Big", 85, "mean_rev"
        if b15 >= 11 and b10 >= 7: return "Small", 82, "mean_rev"
        if b15 <= 4 and b10 <= 3: return "Big", 82, "mean_rev"
        return None, 0, "mean_rev"
    
    def p_dragon_ex(self, arr):
        if len(arr) < 7: return None, 0, "dragon_ex"
        streak = 1
        for x in reversed(arr[:-1]):
            if x == arr[-1]: streak += 1
            else: break
        if streak >= 9: return "Small" if arr[-1]=="Big" else "Big", 92, "dragon_ex"
        if streak >= 8: return "Small" if arr[-1]=="Big" else "Big", 90, "dragon_ex"
        if streak >= 7: return "Small" if arr[-1]=="Big" else "Big", 85, "dragon_ex"
        return None, 0, "dragon_ex"
    
    def p_dragon_mo(self, arr):
        if len(arr) < 5: return None, 0, "dragon_mo"
        streak = 1
        for x in reversed(arr[:-1]):
            if x == arr[-1]: streak += 1
            else: break
        if streak == 6: return arr[-1], 85, "dragon_mo"
        if streak == 5: return arr[-1], 82, "dragon_mo"
        return None, 0, "dragon_mo"
    
    def p_zone(self, arr):
        if len(arr) < 8: return None, 0, "zone"
        b8 = arr[-8:].count("Big")
        if b8 >= 7: return "Small", 82, "zone"
        if b8 <= 1: return "Big", 82, "zone"
        if b8 >= 6: return "Small", 78, "zone"
        if b8 <= 2: return "Big", 78, "zone"
        return None, 0, "zone"
    
    def p_markov4(self, arr):
        if len(arr) < 25: return None, 0, "markov4"
        last4 = tuple(arr[-4:])
        next_after = []
        for i in range(len(arr) - 5):
            if tuple(arr[i:i+4]) == last4:
                next_after.append(arr[i+4])
        if len(next_after) < 2: return None, 0, "markov4"
        counter = Counter(next_after)
        most_common, count = counter.most_common(1)[0]
        ratio = count / len(next_after)
        if ratio >= 0.70:
            return most_common, min(88, 70 + ratio * 20), "markov4"
        return None, 0, "markov4"
    
    def p_frequency(self, arr):
        if len(arr) < 20: return None, 0, "freq"
        b20 = arr[-20:].count("Big")
        b10 = arr[-10:].count("Big")
        if b20 >= 15: return "Small", 82, "freq"
        if b20 <= 5: return "Big", 82, "freq"
        if b20 >= 14 and b10 >= 7: return "Small", 78, "freq"
        if b20 <= 6 and b10 <= 3: return "Big", 78, "freq"
        return None, 0, "freq"
    
    def p_double_gap(self, arr):
        if len(arr) < 10: return None, 0, "dgap"
        last = arr[-1]
        gap = 0
        for x in reversed(arr):
            if x == last: gap += 1
            else: break
        if gap >= 6: return "Small" if last=="Big" else "Big", 85, "dgap"
        if gap >= 5: return "Small" if last=="Big" else "Big", 80, "dgap"
        return None, 0, "dgap"
    
    def p_mtf(self, arr):
        if len(arr) < 30: return None, 0, "mtf"
        b20 = arr[-20:].count("Big")
        b10 = arr[-10:].count("Big")
        b5 = arr[-5:].count("Big")
        if b20 >= 16 and b10 >= 8 and b5 >= 4: return "Small", 88, "mtf"
        if b20 <= 4 and b10 <= 2 and b5 <= 1: return "Big", 88, "mtf"
        return None, 0, "mtf"
    
    def p_anti_cycle(self, arr):
        if len(arr) < 8: return None, 0, "anti_cycle"
        last8 = arr[-8:]
        alt = sum(1 for i in range(len(last8)-1) if last8[i] != last8[i+1])
        if alt >= 7:
            nxt = "Small" if last8[-1]=="Big" else "Big"
            return nxt, 78, "anti_cycle"
        return None, 0, "anti_cycle"
    
    def p_markov3(self, arr):
        if len(arr) < 20: return None, 0, "markov3"
        last3 = tuple(arr[-3:])
        next_after = []
        for i in range(len(arr) - 4):
            if tuple(arr[i:i+3]) == last3:
                next_after.append(arr[i+3])
        if len(next_after) < 2: return None, 0, "markov3"
        counter = Counter(next_after)
        most_common, count = counter.most_common(1)[0]
        ratio = count / len(next_after)
        if ratio >= 0.65:
            return most_common, min(85, 68 + ratio * 20), "markov3"
        return None, 0, "markov3"
    
    def p_markov2(self, arr):
        if len(arr) < 15: return None, 0, "markov2"
        last2 = tuple(arr[-2:])
        next_after = []
        for i in range(len(arr) - 3):
            if tuple(arr[i:i+2]) == last2:
                next_after.append(arr[i+2])
        if len(next_after) < 3: return None, 0, "markov2"
        counter = Counter(next_after)
        most_common, count = counter.most_common(1)[0]
        ratio = count / len(next_after)
        if ratio >= 0.60:
            return most_common, min(82, 65 + ratio * 20), "markov2"
        return None, 0, "markov2"
    
    def p_cycle4(self, arr):
        if len(arr) < 4: return None, 0, "cycle"
        last4 = tuple(arr[-4:])
        cycles = {
            ("Big", "Big", "Small", "Big"): "Small",
            ("Small", "Small", "Big", "Small"): "Big",
            ("Big", "Small", "Big", "Small"): "Big",
            ("Small", "Big", "Small", "Big"): "Small",
            ("Big", "Big", "Big", "Small"): "Small",
            ("Small", "Small", "Small", "Big"): "Big",
            ("Big", "Small", "Small", "Big"): "Big",
            ("Small", "Big", "Big", "Small"): "Small",
            ("Big", "Big", "Small", "Small"): "Big",
            ("Small", "Small", "Big", "Big"): "Small",
        }
        if last4 in cycles:
            return cycles[last4], 70, "cycle"
        return None, 0, "cycle"
    
    def p_break3(self, arr):
        if len(arr) < 3: return None, 0, "break3"
        last3 = arr[-3:]
        if last3 == ["Big"] * 3: return "Small", 70, "break3"
        if last3 == ["Small"] * 3: return "Big", 70, "break3"
        return None, 0, "break3"
    
    def p_break4(self, arr):
        if len(arr) < 4: return None, 0, "break4"
        last4 = arr[-4:]
        if last4 == ["Big"] * 4: return "Small", 78, "break4"
        if last4 == ["Small"] * 4: return "Big", 78, "break4"
        return None, 0, "break4"
    
    def p_alt(self, arr):
        if len(arr) < 6: return None, 0, "alt"
        alt = sum(1 for i in range(-5, -1) if arr[i] != arr[i+1])
        if alt >= 4:
            nxt = "Small" if arr[-1]=="Big" else "Big"
            return nxt, 72, "alt"
        return None, 0, "alt"
    
    def p_pingpong(self, arr):
        if len(arr) < 6: return None, 0, "pingpong"
        alt = sum(1 for i in range(-5, -1) if arr[i] != arr[i+1])
        if alt >= 5:
            nxt = "Small" if arr[-1]=="Big" else "Big"
            return nxt, 70, "pingpong"
        return None, 0, "pingpong"
    
    def p_gap(self, arr):
        if len(arr) < 10: return None, 0, "gap"
        last = arr[-1]
        gap = 0
        for x in reversed(arr):
            if x == last: gap += 1
            else: break
        if gap >= 4:
            return "Small" if last=="Big" else "Big", 72, "gap"
        return None, 0, "gap"
    
    def p_time(self, arr):
        if len(arr) < 10: return None, 0, "time"
        hour = datetime.now().hour
        if 9 <= hour <= 12:
            b10 = arr[-10:].count("Big")
            if b10 >= 7: return "Small", 68, "time"
        elif 18 <= hour <= 21:
            b10 = arr[-10:].count("Big")
            if b10 <= 3: return "Big", 68, "time"
        return None, 0, "time"
    
    def p_sum(self, arr):
        if len(arr) < 5: return None, 0, "sum"
        big = arr[-5:].count("Big")
        if big >= 5: return "Small", 70, "sum"
        if big <= 0: return "Big", 70, "sum"
        return None, 0, "sum"
    
    def p_hl5(self, arr):
        if len(arr) < 5: return None, 0, "hl5"
        b5 = arr[-5:].count("Big")
        if b5 >= 5: return "Small", 68, "hl5"
        if b5 <= 0: return "Big", 68, "hl5"
        return None, 0, "hl5"
    
    def p_pairs(self, arr):
        if len(arr) < 20: return None, 0, "pairs"
        bb = sum(1 for i in range(-19, 0) if arr[i]=="Big" and arr[i+1]=="Big")
        ss = sum(1 for i in range(-19, 0) if arr[i]=="Small" and arr[i+1]=="Small")
        if bb >= 8: return "Small", 68, "pairs"
        if ss >= 8: return "Big", 68, "pairs"
        return None, 0, "pairs"
    
    def p_palindrome(self, arr):
        if len(arr) < 5: return None, 0, "palindrome"
        l5 = arr[-5:]
        if l5[:2] == l5[-2:][::-1]:
            return "Small" if l5[-1]=="Big" else "Big", 65, "palindrome"
        return None, 0, "palindrome"
    
    def p_block222(self, arr):
        if len(arr) < 6: return None, 0, "block222"
        bl = [arr[-6:-4], arr[-4:-2], arr[-2:]]
        if bl[0] == bl[2] and bl[0] != bl[1]:
            return bl[0][0], 65, "block222"
        return None, 0, "block222"
    
    def p_last_rev(self, arr):
        if len(arr) < 1: return None, 0, "last_rev"
        return "Small" if arr[-1]=="Big" else "Big", 62, "last_rev"
    
    def p_symmetry(self, arr):
        if len(arr) < 10: return None, 0, "symmetry"
        last4 = arr[-4:]
        prev4 = arr[-8:-4]
        mirrored = [("Small" if x == "Big" else "Big") for x in prev4]
        if last4 == mirrored:
            nxt = "Small" if last4[-1] == "Big" else "Big"
            return nxt, 68, "symmetry"
        return None, 0, "symmetry"
    
    def p_cluster(self, arr):
        if len(arr) < 8: return None, 0, "cluster"
        last4 = arr[-4:]
        if last4[:2] == last4[2:]:
            nxt = "Small" if last4[0] == "Big" else "Big"
            return nxt, 70, "cluster"
        last8 = arr[-8:]
        if last8[:4] == last8[4:]:
            nxt = "Small" if last8[0] == "Big" else "Big"
            return nxt, 72, "cluster"
        return None, 0, "cluster"
    
    def p_triple(self, arr):
        if len(arr) < 6: return None, 0, "triple"
        last6 = arr[-6:]
        if last6[:3] == last6[3:]:
            nxt = "Small" if last6[0] == "Big" else "Big"
            return nxt, 75, "triple"
        return None, 0, "triple"
    
    # =========================================================
    # 🎯 SIGNAL GENERATOR
    # =========================================================
    def generate_signal(self, arr):
        vol = self.calculate_volatility()
        
        ml_sig, ml_conf, ml_reason = self.multi_layer_confirm(arr)
        if ml_sig and ml_conf >= 90:
            return ml_sig, ml_conf, f"🎯 {ml_reason}", [("multi_layer", ml_sig)], vol, 0
        
        raw_patterns = [
            self.p_extreme_20(arr),
            self.p_mean_reversion(arr),
            self.p_dragon_ex(arr),
            self.p_dragon_mo(arr),
            self.p_zone(arr),
            self.p_markov4(arr),
            self.p_frequency(arr),
            self.p_double_gap(arr),
            self.p_mtf(arr),
            self.p_anti_cycle(arr),
            self.p_markov3(arr),
            self.p_markov2(arr),
            self.p_cycle4(arr),
            self.p_break3(arr),
            self.p_break4(arr),
            self.p_alt(arr),
            self.p_pingpong(arr),
            self.p_gap(arr),
            self.p_time(arr),
            self.p_sum(arr),
            self.p_hl5(arr),
            self.p_pairs(arr),
            self.p_palindrome(arr),
            self.p_block222(arr),
            self.p_last_rev(arr),
            self.p_symmetry(arr),
            self.p_cluster(arr),
            self.p_triple(arr),
        ]
        
        patterns = self.adapt_by_volatility(raw_patterns, vol)
        valid = [(sig, conf, pat) for sig, conf, pat in patterns if sig is not None]
        
        if len(valid) < 2:
            return None, 0, f"Low patterns ({len(valid)})", [], vol, 0
        
        if self.correlation_filter(valid):
            return None, 0, "🚫 Correlation Conflict", [], vol, 0
        
        bay_signal, bay_conf = self.bayesian_inference(valid)
        
        big_score = 0.0
        small_score = 0.0
        reasons = []
        
        for sig, conf, pat_name in valid:
            acc_wr = self.get_accelerated_wr(pat_name)
            decay_w = self.time_decay_weight(pat_name)
            online_w = self.online_learner.get_weight(pat_name)
            
            weight = (conf / 100.0) * (0.5 + acc_wr) * decay_w * online_w
            
            if sig == "Big":
                big_score += weight
                reasons.append(f"B({pat_name[:5]})")
            else:
                small_score += weight
                reasons.append(f"S({pat_name[:5]})")
        
        total = big_score + small_score
        if total < 1.0:
            return None, 0, f"No pattern ({total:.2f})", [], vol, 0
        
        big_pct = big_score / total
        vote_conf = max(big_pct, 1 - big_pct) * 100
        vote_signal = "Big" if big_pct >= 0.5 else "Small"
        
        if abs(bay_conf - 50) < 5:
            if vote_conf >= 75:
                final_signal = vote_signal
                final_conf = vote_conf * 0.9
                fusion_type = "📊 Vote Only"
            else:
                return None, 0, f"Weak Vote ({vote_conf:.0f}%)", [], vol, 0
        elif bay_signal == vote_signal:
            final_signal = bay_signal
            final_conf = max(bay_conf, vote_conf)
            fusion_type = "🎯 Fusion"
        else:
            final_signal = bay_signal
            final_conf = bay_conf * 0.85
            fusion_type = "🧮 Bayesian"
        
        bias_mult = self.bias_conflict_filter(arr, final_signal)
        final_conf *= bias_mult
        bias_note = " ⚠️" if bias_mult < 1.0 else (" ✅" if bias_mult > 1.0 else "")
        
        reason = f"{fusion_type}{bias_note} | Bay:{bay_conf:.0f}% Vote:{vote_conf:.0f}%"
        
        patterns_used_2tuple = [(pat_name, sig) for sig, conf, pat_name in valid]
        
        return final_signal, final_conf, reason, patterns_used_2tuple, vol, bay_conf
    
    # =========================================================
    # 🎯 ANALYZE ROUND (Loss Hidden + Win Simple)
    # =========================================================
    def analyze_round(self, period, number):
        self.last_period = str(period)
        self.last_number = number
        current_result = "Big" if number >= 5 else "Small"
        self.last_result = current_result
        
        if self.is_paused: return
        
        short = "..." + str(period)[-3:]
        
        # 1. Evaluate Previous Signal
        if self.active_prediction:
            win = (self.active_prediction == current_result)
            
            for pat_data in self.active_patterns_used:
                pat_name = pat_data[0]
                sig = pat_data[1]
                
                self.pattern_total[pat_name] += 1
                if sig == current_result:
                    self.pattern_win[pat_name] += 1
                self.pattern_recent[pat_name].append(1 if sig == current_result else 0)
                
                t = self.pattern_total[pat_name]
                if t > 0:
                    self.pattern_wr[pat_name] = self.pattern_win[pat_name] / t
                
                self.online_learner.update(pat_name, sig == current_result)
                self.data_engine.save_pattern_stat(
                    pat_name, sig, current_result, sig == current_result
                )
            
            if win:
                self.total_wins += 1
                self.consecutive_wins += 1
                self.consecutive_losses = 0
                
                prev_step = self.current_step
                step_key = min(prev_step, 3)
                self.win_by_step[step_key] += 1
                self.current_step = 0
                
                # ✅ Win Only — Simple
                self.send_telegram(
                    f"✅ <b>WIN</b> — Step {prev_step + 1}\n"
                    f"📊 WR: {self.get_wr():.1f}% | Win3: {self.get_win3_rate():.1f}%"
                )
            else:
                # ❌ Loss — Silent
                self.total_losses += 1
                self.consecutive_losses += 1
                self.consecutive_wins = 0
                self.current_step += 1
                # Telegram ပို့ မလုပ်
            
            self.active_prediction = None
            self.active_patterns_used = []
        
        # 2. Save & Append
        self.data_engine.save_result(period, number, current_result)
        self.history.append(current_result)
        
        # 3. Warm-up
        if len(self.history) < 20:
            self.send_telegram(f"⏳ Warm-up {short} ({len(self.history)}/20)")
            return
        
        # 4. Trap Filter
        arr = list(self.history)
        if self.trap_filter(arr):
            self.total_skips += 1
            self.send_telegram(f"⏸️ <b>SKIP</b> {short}\n🚨 Trap")
            return
        
        # 5. Signal
        signal, conf, reason, patterns_used, vol, bay = self.generate_signal(arr)
        
        self.last_signal = signal if signal else "SKIP"
        self.last_reason = reason
        self.active_bayesian = bay
        
        # 6. Threshold
        threshold = self.get_dynamic_threshold()
        
        if signal is None or conf < threshold:
            self.total_skips += 1
            self.send_telegram(f"⏸️ <b>SKIP</b> {short}\n{reason}")
            return
        
        # 7. Emit Signal
        self.active_prediction = signal
        self.active_patterns_used = patterns_used
        self.total_signals += 1
        
        next_bet = BASE_BET * (2 ** self.current_step)
        
        stars = "⭐" * min(int(conf / 20), 5)
        self.send_telegram(
            f"🚀 <b>HYBRID v4.4.4 SIGNAL</b> {stars}\n"
            f"📅 Period: {short}\n"
            f"📌 {reason}\n"
            f"🎯 <b>{signal.upper()}</b>\n"
            f"💰 Step {self.current_step+1} ({2**self.current_step}x) = ${next_bet:.2f}"
        )
    
    def get_dynamic_threshold(self):
        total = self.total_wins + self.total_losses
        if total < 10: return 65
        wr = self.get_wr()
        if wr >= 75: return 72
        elif wr >= 65: return 70
        elif wr >= 55: return 68
        else: return 65
    
    def get_wr(self):
        t = self.total_wins + self.total_losses
        return (self.total_wins/t*100) if t>0 else 0.0
    
    def get_win3_rate(self):
        t = sum(self.win_by_step.values())
        if t == 0: return 0.0
        w3 = self.win_by_step[0] + self.win_by_step[1] + self.win_by_step[2]
        return (w3/t)*100
    
    def auto_optimize(self):
        for pat, wr in list(self.pattern_wr.items()):
            total = self.pattern_total[pat]
            if total < 5: continue
            acc_wr = self.get_accelerated_wr(pat)
            if acc_wr > wr + 0.1:
                self.pattern_weight[pat] = min(2.0, self.pattern_weight[pat] * 1.15)
            elif acc_wr < wr - 0.1:
                self.pattern_weight[pat] = max(0.3, self.pattern_weight[pat] * 0.85)
        
        top = sorted(self.pattern_wr.items(), key=lambda x: x[1], reverse=True)[:5]
        top_str = "\n".join([f"{p}: {w*100:.0f}%" for p, w in top])
        
        self.send_telegram(
            f"🔧 <b>OPTIMIZE</b>\n\n🏆 Top 5:\n{top_str}\n\n"
            f"📊 WR: {self.get_wr():.1f}%\n🎯 Win3: {self.get_win3_rate():.1f}%"
        )


# ==========================================
# TELEGRAM COMMANDS
# ==========================================
def poll_telegram(agent):
    global BASE_BET          # ✅ FIX — Function အပေါ်ဆုံးမှာ
    
    try:
        requests.get(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/deleteWebhook?drop_pending_updates=true",
            timeout=10
        )
    except: pass
    
    offset = 0
    while True:
        try:
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates?offset={offset}&timeout=20"
            r = requests.get(url, timeout=25)
            if r.status_code == 200:
                for u in r.json().get("result", []):
                    offset = u["update_id"] + 1
                    m = u.get("message", {}) or u.get("edited_message", {})
                    cid = str(m.get("chat", {}).get("id", ""))
                    txt = m.get("text", "").strip().lower()
                    if cid != CHAT_ID: continue
                    
                    if txt == "/status":
                        agent.send_telegram(
                            f"🚀 <b>HYBRID v4.4.4 STATUS</b>\n\n"
                            f"⚙️ {'PAUSED 🛑' if agent.is_paused else 'RUNNING 🟢'}\n"
                            f"Signals: {agent.total_signals} | Skips: {agent.total_skips}\n"
                            f"✅ W: {agent.total_wins} | ❌ L: {agent.total_losses}\n"
                            f"📈 WR: {agent.get_wr():.2f}%\n"
                            f"🎯 Win3: {agent.get_win3_rate():.1f}%\n"
                            f"💰 Step: {agent.current_step+1} ({2**agent.current_step}x)\n"
                            f"📊 Base Bet: ${BASE_BET}"
                        )
                    elif txt == "/patterns":
                        s = "📈 <b>Pattern WR</b>\n"
                        for k, v in sorted(agent.pattern_wr.items(), key=lambda x: x[1], reverse=True)[:15]:
                            t = agent.pattern_total[k]
                            acc = agent.get_accelerated_wr(k)
                            s += f"{k}: {v*100:.0f}% | Acc:{acc*100:.0f}% ({t}x)\n"
                        agent.send_telegram(s)
                    elif txt == "/pause":
                        agent.is_paused = True
                        agent.send_telegram("🛑 Paused")
                    elif txt == "/resume":
                        agent.is_paused = False
                        agent.send_telegram("🟢 Resumed")
                    elif txt == "/reset":
                        agent.current_step = 0
                        agent.send_telegram("🔄 Step Reset")
                    elif txt.startswith("/base"):
                        parts = txt.split()
                        if len(parts) == 2:
                            try:
                                BASE_BET = float(parts[1])   # ✅ global မလို — အပေါ်မှာ ရှိပြီး
                                agent.send_telegram(f"✅ Base Bet = ${BASE_BET}")
                            except:
                                agent.send_telegram("❌ Invalid")
                        else:
                            agent.send_telegram(f"Base Bet: ${BASE_BET}")
        except Exception as e:
            print(f"TG Poll: {e}", flush=True)
        time.sleep(1)


# ==========================================
# MAIN LOOP
# ==========================================
def run_bot():
    print("🚀 HYBRID v4.4.4 (Syntax Fixed) starting...", flush=True)
    agent = HybridEngineV444()
    threading.Thread(target=poll_telegram, args=(agent,), daemon=True).start()
    
    last_period = ""
    rounds_since_opt = 0
    headers = {
        "accept": "application/json, text/plain, */*",
        "authorization": f"Bearer {API_AUTH}",
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
            r = requests.post(API_URL, headers=headers, json=payload, timeout=10)
            if r.status_code == 200:
                d = r.json()
                lst = d.get("data", {}).get("list", [])
                if lst:
                    latest = lst[0]
                    raw = str(latest.get("issueNumber"))
                    period = str(int(raw) + 2)
                    number = int(latest.get("number"))
                    
                    if period != last_period:
                        last_period = period
                        print(f"🚀 Sync {period} → {number}", flush=True)
                        agent.analyze_round(period, number)
                        
                        rounds_since_opt += 1
                        if rounds_since_opt >= 50:
                            agent.auto_optimize()
                            rounds_since_opt = 0
        except Exception as e:
            print(f"API Err: {e}", flush=True)
        time.sleep(1.5)


threading.Thread(target=run_bot, daemon=True).start()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
