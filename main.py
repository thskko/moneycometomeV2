import requests
import time
import os
import threading
from collections import deque, Counter, defaultdict
from datetime import datetime
from flask import Flask

TELEGRAM_TOKEN = "8913070806:AAF3rP0zKJtofE-5KVesqcdoHzn7Go0avho"
CHAT_ID = "-1004402480797"

app = Flask(__name__)
global_agent = None

API_URL = "https://6lotteryapi.com/api/webapi/GetNoaverageEmerdList"
API_AUTH = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpYXQiOiIxNzg3OTgxNTA5IiwibmJmIjoiMTc4Nzk4MTUwOSIsImV4cCI6IjE3ODc5ODMzMDkiLCJodHRwOi8vc2NoZW1hcy5taWNyb3NvZnQuY29tL3dzLzIwMDgvMDYvaWRlbnRpdHkvY2xhaW1zL2V4cGlyYXRpb24iOiI4LzI5LzIwMjYgMTI6MzE2NDkgUE0iLCJodHRwOi8vc2NoZW1hcy5taWNyb3NvZnQuY29tL3dzLzIwMDgvMDYvaWRlbnRpdHkvY2xhaW1zL3JvbGUiOiJBY2Nlc3NfVG9rZW4iLCJVc2VySWQiOiIxMDEyMjEzIiwiVXNlck5hbWUiOiI5NTk3NDA5MzkzNzAiLCJVc2VyUGhvdG8iOiI5IiwiTmlja05hbWUiOiJUaGVrR3lpIiwiQW1vdW50IjoiODcuMzAiLCJJbnRlZ3JhbCI6IjAiLCJsb2dpbk1hcmsiOiJINSIsImxvZ2luVGltZSI6IjcvMjkvMjAyNiAxMjowMTo0OSBQTSIsImxvZ2luSVBBZGRyZXNzIjoiNDUuNDEuMTA0LjI0MCIsImRiTnVtYmVyIjoiMCIsIklzdmFsaWRhdG9yIjoiMCIsIktleUNvZGUiOiIzMjMzMiIsImRva2VuVHlwZSI6IjJBY2Nlc3NfVG9rZW4iLCJob25lVHlwZSI6IjAiLCJVc2VyVHlwZSI6IjAiLCJVc2VyTmFtZ2UiOiIuIiwiaXNzIjoiand0SXNzdWVyIiwiYXVkIjoibG90dGVyeVRpY2tldCJ9.ZL0Y9gexUTCsKwWeZhCLAAw8AABEYJt0GnIzIviMG4g"


# ==========================================
# 📊 DASHBOARD
# ==========================================
@app.route('/')
def home():
    global global_agent
    if not global_agent:
        return "<h3>⚡ GH-0X v3.0 starting...</h3>"
    
    a = global_agent
    total = a.total_wins + a.total_losses
    wr = (a.total_wins / total * 100) if total > 0 else 0.0
    
    last_20 = " ".join([("B" if r == "Big" else "S") for r in list(a.history)[-20:]])
    
    pat_rows = ""
    for k, v in a.pattern_stats.most_common(20):
        pat_rows += f"<tr><td>{k}</td><td>{v}</td></tr>"
    
    return f"""
    <html><head><title>GH-0X v3.0</title>
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
    <h1>⚡ GH-0X ENGINE v3.0 (25 Patterns)</h1>
    
    <div class="box">
      <h2>📊 Performance</h2>
      <p>Status: <b>{'PAUSED 🛑' if a.is_paused else 'RUNNING 🟢'}</b></p>
      <p>Signals: {a.total_signals} | Skips: {a.total_skips}</p>
      <p>Wins: {a.total_wins} | Losses: {a.total_losses}</p>
      <p>Win Rate: <span class="big">{wr:.2f}%</span></p>
      <p>Win3: <span class="big">{a.get_win3_rate():.1f}%</span></p>
      <p>Current Step: {a.current_step + 1} ({2**a.current_step}x)</p>
    </div>
    
    <div class="box">
      <h2>🎯 Last 20</h2>
      <p class="nums">{last_20}</p>
    </div>
    
    <div class="box">
      <h2>📈 Pattern Stats</h2>
      <table>
        <tr><th>Pattern</th><th>Count</th></tr>
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
# ⚡ GH-0X ENGINE v3.0
# ==========================================
class GH0XEngineV3:
    def __init__(self):
        global global_agent
        global_agent = self
        
        self.history = deque(maxlen=200)
        
        self.current_step = 0
        self.active_prediction = None
        self.is_paused = False
        self.last_period = "None"
        self.last_number = 0
        self.last_result = "None"
        self.last_signal = "None"
        
        self.total_signals = 0
        self.total_wins = 0
        self.total_losses = 0
        self.total_skips = 0
        self.win_by_step = {0: 0, 1: 0, 2: 0, 3: 0}
        
        self.pattern_stats = Counter()
    
    def send_telegram(self, message):
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {"chat_id": CHAT_ID, "text": message, "parse_mode": "HTML"}
        try:
            r = requests.post(url, json=payload, timeout=10)
            print(f"📤 TG: {r.status_code}", flush=True)
        except Exception as e:
            print(f"❌ TG: {e}", flush=True)
    
    # =========================================================
    # 🏆 TIER 1 — 10 PATTERNS
    # =========================================================
    
    def p_extreme_20(self, arr):
        if len(arr) < 20: return None, 0, "extreme20"
        b20 = arr[-20:].count("Big")
        if b20 >= 18:
            self.pattern_stats["extreme20_18+"] += 1
            return "Small", 92, "extreme20"
        if b20 <= 2:
            self.pattern_stats["extreme20_2-"] += 1
            return "Big", 92, "extreme20"
        if b20 >= 17:
            self.pattern_stats["extreme20_17+"] += 1
            return "Small", 88, "extreme20"
        if b20 <= 3:
            self.pattern_stats["extreme20_3-"] += 1
            return "Big", 88, "extreme20"
        return None, 0, "extreme20"
    
    def p_dragon_exhaustion(self, arr):
        if len(arr) < 7: return None, 0, "dragon_ex"
        streak = 1
        for x in reversed(arr[:-1]):
            if x == arr[-1]: streak += 1
            else: break
        if streak >= 9:
            self.pattern_stats["dragon_ex_9+"] += 1
            return "Small" if arr[-1]=="Big" else "Big", 92, "dragon_ex"
        if streak >= 8:
            self.pattern_stats["dragon_ex_8"] += 1
            return "Small" if arr[-1]=="Big" else "Big", 90, "dragon_ex"
        if streak >= 7:
            self.pattern_stats["dragon_ex_7"] += 1
            return "Small" if arr[-1]=="Big" else "Big", 85, "dragon_ex"
        return None, 0, "dragon_ex"
    
    def p_mean_reversion(self, arr):
        if len(arr) < 15: return None, 0, "mean_rev"
        b15 = arr[-15:].count("Big")
        b10 = arr[-10:].count("Big")
        if b15 >= 13:
            self.pattern_stats["mr_13+"] += 1
            return "Small", 88, "mean_rev"
        if b15 <= 2:
            self.pattern_stats["mr_2-"] += 1
            return "Big", 88, "mean_rev"
        if b15 >= 12:
            self.pattern_stats["mr_12+"] += 1
            return "Small", 85, "mean_rev"
        if b15 <= 3:
            self.pattern_stats["mr_3-"] += 1
            return "Big", 85, "mean_rev"
        if b15 >= 11 and b10 >= 7:
            self.pattern_stats["mr_multi"] += 1
            return "Small", 82, "mean_rev"
        if b15 <= 4 and b10 <= 3:
            self.pattern_stats["mr_multi_low"] += 1
            return "Big", 82, "mean_rev"
        return None, 0, "mean_rev"
    
    def p_dragon_momentum(self, arr):
        if len(arr) < 5: return None, 0, "dragon_mo"
        streak = 1
        for x in reversed(arr[:-1]):
            if x == arr[-1]: streak += 1
            else: break
        if streak == 6:
            self.pattern_stats["dragon_mo_6"] += 1
            return arr[-1], 85, "dragon_mo"
        if streak == 5:
            self.pattern_stats["dragon_mo_5"] += 1
            return arr[-1], 82, "dragon_mo"
        return None, 0, "dragon_mo"
    
    def p_zone_rejection(self, arr):
        if len(arr) < 8: return None, 0, "zone"
        b8 = arr[-8:].count("Big")
        if b8 >= 7:
            self.pattern_stats["zone_7+"] += 1
            return "Small", 82, "zone"
        if b8 <= 1:
            self.pattern_stats["zone_1-"] += 1
            return "Big", 82, "zone"
        if b8 >= 6:
            self.pattern_stats["zone_6+"] += 1
            return "Small", 78, "zone"
        if b8 <= 2:
            self.pattern_stats["zone_2-"] += 1
            return "Big", 78, "zone"
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
            self.pattern_stats["markov4_hit"] += 1
            return most_common, min(88, 70 + ratio * 20), "markov4"
        return None, 0, "markov4"
    
    def p_frequency_bias(self, arr):
        if len(arr) < 20: return None, 0, "freq"
        b20 = arr[-20:].count("Big")
        b10 = arr[-10:].count("Big")
        if b20 >= 15:
            self.pattern_stats["freq_15+"] += 1
            return "Small", 82, "freq"
        if b20 <= 5:
            self.pattern_stats["freq_5-"] += 1
            return "Big", 82, "freq"
        if b20 >= 14 and b10 >= 7:
            self.pattern_stats["freq_multi"] += 1
            return "Small", 78, "freq"
        if b20 <= 6 and b10 <= 3:
            self.pattern_stats["freq_multi_low"] += 1
            return "Big", 78, "freq"
        return None, 0, "freq"
    
    def p_double_gap(self, arr):
        if len(arr) < 10: return None, 0, "dgap"
        last = arr[-1]
        gap = 0
        for x in reversed(arr):
            if x == last: gap += 1
            else: break
        if gap >= 6:
            self.pattern_stats["dgap_6+"] += 1
            return "Small" if last=="Big" else "Big", 85, "dgap"
        if gap >= 5:
            self.pattern_stats["dgap_5"] += 1
            return "Small" if last=="Big" else "Big", 80, "dgap"
        return None, 0, "dgap"
    
    def p_multi_tf_extreme(self, arr):
        if len(arr) < 30: return None, 0, "mtf"
        b20 = arr[-20:].count("Big")
        b10 = arr[-10:].count("Big")
        b5 = arr[-5:].count("Big")
        if b20 >= 16 and b10 >= 8 and b5 >= 4:
            self.pattern_stats["mtf_high"] += 1
            return "Small", 88, "mtf"
        if b20 <= 4 and b10 <= 2 and b5 <= 1:
            self.pattern_stats["mtf_low"] += 1
            return "Big", 88, "mtf"
        return None, 0, "mtf"
    
    def p_anti_cycle(self, arr):
        if len(arr) < 8: return None, 0, "anti_cycle"
        last8 = arr[-8:]
        # Pattern: B,S,B,S,B,S,B,S → Break
        alt_count = sum(1 for i in range(len(last8)-1) if last8[i] != last8[i+1])
        if alt_count >= 7:
            self.pattern_stats["anti_cycle_hit"] += 1
            nxt = "Small" if last8[-1]=="Big" else "Big"
            return nxt, 78, "anti_cycle"
        return None, 0, "anti_cycle"
    
    # =========================================================
    # 🥈 TIER 2 — 10 PATTERNS
    # =========================================================
    
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
            self.pattern_stats["markov3_hit"] += 1
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
            self.pattern_stats["markov2_hit"] += 1
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
            self.pattern_stats["cycle_hit"] += 1
            return cycles[last4], 70, "cycle"
        return None, 0, "cycle"
    
    def p_streak_break3(self, arr):
        if len(arr) < 3: return None, 0, "break3"
        last3 = arr[-3:]
        if last3 == ["Big"] * 3:
            self.pattern_stats["break3_big"] += 1
            return "Small", 70, "break3"
        if last3 == ["Small"] * 3:
            self.pattern_stats["break3_small"] += 1
            return "Big", 70, "break3"
        return None, 0, "break3"
    
    def p_streak_break4(self, arr):
        if len(arr) < 4: return None, 0, "break4"
        last4 = arr[-4:]
        if last4 == ["Big"] * 4:
            self.pattern_stats["break4_big"] += 1
            return "Small", 78, "break4"
        if last4 == ["Small"] * 4:
            self.pattern_stats["break4_small"] += 1
            return "Big", 78, "break4"
        return None, 0, "break4"
    
    def p_alternation(self, arr):
        if len(arr) < 6: return None, 0, "alt"
        alt = sum(1 for i in range(-5, -1) if arr[i] != arr[i+1])
        if alt >= 4:
            self.pattern_stats["alt_4+"] += 1
            nxt = "Small" if arr[-1]=="Big" else "Big"
            return nxt, 72, "alt"
        return None, 0, "alt"
    
    def p_pingpong(self, arr):
        if len(arr) < 6: return None, 0, "pingpong"
        alt = sum(1 for i in range(-5, -1) if arr[i] != arr[i+1])
        if alt >= 5:
            self.pattern_stats["pingpong_5"] += 1
            nxt = "Small" if arr[-1]=="Big" else "Big"
            return nxt, 70, "pingpong"
        return None, 0, "pingpong"
    
    def p_gap_analysis(self, arr):
        if len(arr) < 10: return None, 0, "gap"
        last = arr[-1]
        gap = 0
        for x in reversed(arr):
            if x == last: gap += 1
            else: break
        if gap >= 4:
            self.pattern_stats["gap_4+"] += 1
            return "Small" if last=="Big" else "Big", 72, "gap"
        return None, 0, "gap"
    
    def p_time_pattern(self, arr):
        if len(arr) < 10: return None, 0, "time"
        hour = datetime.now().hour
        if 9 <= hour <= 12:
            b10 = arr[-10:].count("Big")
            if b10 >= 7:
                self.pattern_stats["time_morning"] += 1
                return "Small", 68, "time"
        elif 18 <= hour <= 21:
            b10 = arr[-10:].count("Big")
            if b10 <= 3:
                self.pattern_stats["time_evening"] += 1
                return "Big", 68, "time"
        return None, 0, "time"
    
    def p_sum_analysis(self, arr):
        if len(arr) < 5: return None, 0, "sum"
        last5 = arr[-5:]
        big_count = last5.count("Big")
        if big_count >= 5:
            self.pattern_stats["sum_all_big"] += 1
            return "Small", 70, "sum"
        if big_count <= 0:
            self.pattern_stats["sum_all_small"] += 1
            return "Big", 70, "sum"
        return None, 0, "sum"
    
    # =========================================================
    # 🥉 TIER 3 — 5 PATTERNS
    # =========================================================
    
    def p_highlow5(self, arr):
        if len(arr) < 5: return None, 0, "hl5"
        b5 = arr[-5:].count("Big")
        if b5 >= 5:
            self.pattern_stats["hl5_all_big"] += 1
            return "Small", 68, "hl5"
        if b5 <= 0:
            self.pattern_stats["hl5_all_small"] += 1
            return "Big", 68, "hl5"
        return None, 0, "hl5"
    
    def p_bb_ss_pairs(self, arr):
        if len(arr) < 20: return None, 0, "pairs"
        bb = sum(1 for i in range(-19, 0) if arr[i]=="Big" and arr[i+1]=="Big")
        ss = sum(1 for i in range(-19, 0) if arr[i]=="Small" and arr[i+1]=="Small")
        if bb >= 8:
            self.pattern_stats["pairs_bb_high"] += 1
            return "Small", 68, "pairs"
        if ss >= 8:
            self.pattern_stats["pairs_ss_high"] += 1
            return "Big", 68, "pairs"
        return None, 0, "pairs"
    
    def p_palindrome(self, arr):
        if len(arr) < 5: return None, 0, "palindrome"
        l5 = arr[-5:]
        if l5[:2] == l5[-2:][::-1]:
            self.pattern_stats["palindrome_hit"] += 1
            return "Small" if l5[-1]=="Big" else "Big", 65, "palindrome"
        return None, 0, "palindrome"
    
    def p_block_222(self, arr):
        if len(arr) < 6: return None, 0, "block222"
        bl = [arr[-6:-4], arr[-4:-2], arr[-2:]]
        if bl[0] == bl[2] and bl[0] != bl[1]:
            self.pattern_stats["block222_hit"] += 1
            return bl[0][0], 65, "block222"
        return None, 0, "block222"
    
    def p_last_reverse(self, arr):
        if len(arr) < 1: return None, 0, "last_rev"
        self.pattern_stats["last_rev"] += 1
        return "Small" if arr[-1]=="Big" else "Big", 62, "last_rev"
    
    # =========================================================
    # 🎯 SIGNAL GENERATOR
    # =========================================================
    def generate_signal(self, arr):
        patterns = [
            # Tier 1 (10)
            self.p_extreme_20(arr),
            self.p_dragon_exhaustion(arr),
            self.p_mean_reversion(arr),
            self.p_dragon_momentum(arr),
            self.p_zone_rejection(arr),
            self.p_markov4(arr),
            self.p_frequency_bias(arr),
            self.p_double_gap(arr),
            self.p_multi_tf_extreme(arr),
            self.p_anti_cycle(arr),
            # Tier 2 (10)
            self.p_markov3(arr),
            self.p_markov2(arr),
            self.p_cycle4(arr),
            self.p_streak_break3(arr),
            self.p_streak_break4(arr),
            self.p_alternation(arr),
            self.p_pingpong(arr),
            self.p_gap_analysis(arr),
            self.p_time_pattern(arr),
            self.p_sum_analysis(arr),
            # Tier 3 (5)
            self.p_highlow5(arr),
            self.p_bb_ss_pairs(arr),
            self.p_palindrome(arr),
            self.p_block_222(arr),
            self.p_last_reverse(arr),
        ]
        
        big_score = 0.0
        small_score = 0.0
        reasons = []
        patterns_used = []
        
        for sig, conf, pat_name in patterns:
            if sig is None: continue
            weight = conf / 100.0
            if sig == "Big":
                big_score += weight
                reasons.append(f"B({pat_name[:5]})")
            else:
                small_score += weight
                reasons.append(f"S({pat_name[:5]})")
            patterns_used.append((pat_name, sig))
        
        total = big_score + small_score
        if total < 1.0:
            return None, 0, f"No pattern ({total:.2f})", []
        
        big_pct = big_score / total
        conf = max(big_pct, 1 - big_pct) * 100
        
        if conf < 70:
            return None, conf, f"Weak ({conf:.0f}%)", patterns_used
        
        if len(patterns_used) < 2:
            return None, conf, f"Low patterns ({len(patterns_used)})", patterns_used
        
        final_signal = "Big" if big_pct >= 0.5 else "Small"
        reason = f"⚡ {' + '.join(reasons[:3])} ({conf:.0f}%)"
        return final_signal, conf, reason, patterns_used
    
    # =========================================================
    # 🎯 ANALYZE ROUND
    # =========================================================
    def analyze_round(self, period, number):
        self.last_period = str(period)
        self.last_number = number
        current_result = "Big" if number >= 5 else "Small"
        self.last_result = current_result
        
        if self.is_paused: return
        
        short = "..." + str(period)[-3:]
        
        if self.active_prediction:
            win = (self.active_prediction == current_result)
            
            if win:
                self.total_wins += 1
                step_key = min(self.current_step, 3)
                self.win_by_step[step_key] += 1
                self.current_step = 0
                
                self.send_telegram(
                    f"✅ <b>WIN</b>\n"
                    f"🔢 {number} ({current_result})\n"
                    f"📊 WR: {self.get_wr():.1f}% | Win3: {self.get_win3_rate():.1f}%"
                )
            else:
                self.total_losses += 1
                self.current_step += 1
                
                if self.current_step >= 3:
                    self.send_telegram(f"⚠️ <b>Step {self.current_step+1} ({2**self.current_step}x)</b>")
            
            self.active_prediction = None
        
        self.history.append(current_result)
        
        if len(self.history) < 15:
            self.send_telegram(f"⏳ Warm-up {short} ({len(self.history)}/15)")
            return
        
        arr = list(self.history)
        signal, conf, reason, patterns_used = self.generate_signal(arr)
        
        self.last_signal = signal if signal else "SKIP"
        
        if signal is None:
            self.total_skips += 1
            self.send_telegram(f"⏸️ <b>SKIP</b> {short}\n{reason}")
            return
        
        self.active_prediction = signal
        self.total_signals += 1
        
        stars = "⭐" * min(int(conf / 20), 5)
        self.send_telegram(
            f"⚡ <b>GH-0X v3.0 SIGNAL</b> {stars}\n"
            f"📅 Period: {short}\n"
            f"📌 {reason}\n"
            f"🎯 <b>{signal.upper()}</b>\n"
            f"💰 Step {self.current_step+1} ({2**self.current_step}x)\n"
            f"📊 WR: {self.get_wr():.1f}% | Win3: {self.get_win3_rate():.1f}%"
        )
    
    def get_wr(self):
        t = self.total_wins + self.total_losses
        return (self.total_wins/t*100) if t>0 else 0.0
    
    def get_win3_rate(self):
        t = sum(self.win_by_step.values())
        if t == 0: return 0.0
        w3 = self.win_by_step[0] + self.win_by_step[1] + self.win_by_step[2]
        return (w3/t)*100


# ==========================================
# 📱 TELEGRAM COMMANDS
# ==========================================
def poll_telegram(agent):
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
                            f"📊 <b>GH-0X v3.0 STATUS</b>\n\n"
                            f"⚙️ {'PAUSED 🛑' if agent.is_paused else 'RUNNING 🟢'}\n"
                            f"Signals: {agent.total_signals} | Skips: {agent.total_skips}\n"
                            f"✅ W: {agent.total_wins} | ❌ L: {agent.total_losses}\n"
                            f"📈 WR: {agent.get_wr():.2f}%\n"
                            f"🎯 Win3: {agent.get_win3_rate():.1f}%"
                        )
                    elif txt == "/patterns":
                        s = "📈 <b>Pattern Stats</b>\n"
                        for k, v in agent.pattern_stats.most_common(20):
                            s += f"{k}: {v}\n"
                        agent.send_telegram(s)
                    elif txt == "/pause":
                        agent.is_paused = True
                        agent.send_telegram("🛑 Paused")
                    elif txt == "/resume":
                        agent.is_paused = False
                        agent.send_telegram("🟢 Resumed")
                    elif txt == "/reset":
                        agent.current_step = 0
                        agent.send_telegram("🔄 Reset")
        except Exception as e:
            print(f"TG Poll: {e}", flush=True)
        time.sleep(1)


# ==========================================
# 🚀 MAIN LOOP
# ==========================================
def run_bot():
    print("⚡ GH-0X Engine v3.0 (25 Patterns) starting...", flush=True)
    agent = GH0XEngineV3()
    threading.Thread(target=poll_telegram, args=(agent,), daemon=True).start()
    
    last_period = ""
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
                        print(f"⚡ Sync {period} → {number}", flush=True)
                        agent.analyze_round(period, number)
        except Exception as e:
            print(f"API Err: {e}", flush=True)
        time.sleep(1.5)


threading.Thread(target=run_bot, daemon=True).start()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
