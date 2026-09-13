import requests
import time
import os
import threading
from collections import deque, Counter, defaultdict
from datetime import datetime
from flask import Flask, jsonify

# ==========================================
# TELEGRAM CONFIG
# ==========================================
TELEGRAM_TOKEN = "8913070806:AAF3rP0zKJtofE-5KVesqcdoHzn7Go0avho"
CHAT_ID = "-1004402480797"
# ==========================================

app = Flask(__name__)
global_agent = None


# ==========================================
# 📊 DASHBOARD
# ==========================================
@app.route('/')
def home():
    global global_agent
    if not global_agent:
        return "<h3>🔢 Number Bot v3.0 starting...</h3>"
    
    a = global_agent
    total = a.total_wins + a.total_losses
    wr = (a.total_wins / total * 100) if total > 0 else 0.0
    win3 = a.get_win3_rate()
    
    last_nums = " → ".join([str(n) for n in list(a.number_window)[-20:]])
    
    freq = Counter(a.number_window)
    freq_str = " | ".join([f"{i}:{freq.get(i, 0)}" for i in range(10)])
    
    pat_rows = "".join([
        f"<tr><td>{k}</td><td>{v}</td><td>{a.pattern_wr.get(k, 0)*100:.1f}%</td></tr>"
        for k, v in a.pattern_stats.most_common(15)
    ])
    
    return f"""
    <html><head><title>Number Bot v3.0</title>
    <meta http-equiv="refresh" content="15">
    <style>
    body{{background:#0a0e27;color:#0ff;font-family:monospace;padding:20px}}
    h1,h2{{color:#0ff;text-shadow:0 0 10px #0ff}}
    .box{{background:#1a1f3a;border:1px solid #0ff;padding:15px;margin:10px 0;border-radius:8px}}
    .big{{font-size:32px;color:#0f0;font-weight:bold}}
    .nums{{font-size:18px;color:#ff0;word-wrap:break-word}}
    table{{width:100%;border-collapse:collapse}}
    th,td{{padding:8px;border:1px solid #0ff;text-align:left}}
    th{{background:#0ff;color:#000}}
    </style></head><body>
    <h1>🔢 NUMBER PATTERN BOT v3.0</h1>
    
    <div class="box">
      <h2>📊 Performance</h2>
      <p>Status: <b>{'PAUSED 🛑' if a.is_paused else 'RUNNING 🟢'}</b></p>
      <p>Signals: {a.total_signals} | Skips: {a.total_skips}</p>
      <p>Wins: {a.total_wins} | Losses: {a.total_losses}</p>
      <p>Win Rate: <span class="big">{wr:.2f}%</span></p>
      <p>Win-in-3: <span class="big">{win3:.1f}%</span></p>
      <p>Current Step: {a.current_step + 1} ({a.get_multiplier()}x)</p>
    </div>
    
    <div class="box">
      <h2>🎯 Last 20 Numbers</h2>
      <p class="nums">{last_nums}</p>
    </div>
    
    <div class="box">
      <h2>📊 Number Frequency</h2>
      <p>{freq_str}</p>
    </div>
    
    <div class="box">
      <h2>🎲 Pattern Statistics</h2>
      <table>
        <tr><th>Pattern</th><th>Count</th><th>WR</th></tr>
        {pat_rows}
      </table>
    </div>
    
    <div class="box">
      <h2>📅 Last Period</h2>
      <p>{a.last_period} → Number: {a.last_number} → {a.last_result}</p>
      <p>Signal Source: {a.last_triggered_reason}</p>
    </div>
    </body></html>
    """

@app.route('/api/stats')
def api_stats():
    global global_agent
    a = global_agent
    if not a: return jsonify({"error": "not ready"})
    total = a.total_wins + a.total_losses
    return jsonify({
        "wr": (a.total_wins/total*100) if total else 0,
        "win3": a.get_win3_rate(),
        "wins": a.total_wins,
        "losses": a.total_losses,
        "signals": a.total_signals,
        "skips": a.total_skips,
        "step": a.current_step,
    })


# ==========================================
# 🎯 NUMBER PATTERN ENGINE v3.0
# ==========================================
class NumberPatternEngineV3:
    def __init__(self):
        global global_agent
        global_agent = self
        
        self.number_window = deque(maxlen=300)
        
        self.current_step = 0
        self.active_prediction = None
        self.active_patterns_used = []
        self.is_paused = False
        self.last_period = "None"
        self.last_number = 0
        self.last_result = "None"
        self.last_triggered_reason = "None"
        
        self.total_signals = 0
        self.total_wins = 0
        self.total_losses = 0
        self.total_skips = 0
        self.consecutive_losses = 0
        self.win_by_step = {0: 0, 1: 0, 2: 0, 3: 0}
        
        self.pattern_stats = Counter()
        
        # 🆕 Pattern WR default 60%
        self.pattern_wr = defaultdict(lambda: 0.60)
        self.pattern_win = defaultdict(int)
        self.pattern_total = defaultdict(int)
        
        self.transition_matrix = defaultdict(lambda: defaultdict(int))
        
        self.number_freq = Counter()
    
    def get_multiplier(self):
        return 2 ** self.current_step
    
    def send_telegram(self, message):
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {"chat_id": CHAT_ID, "text": message, "parse_mode": "HTML"}
        try:
            r = requests.post(url, json=payload, timeout=10)
            print(f"📤 TG: {r.status_code}", flush=True)
        except Exception as e:
            print(f"❌ TG Err: {e}", flush=True)
    
    def update_pattern_wr(self, actual):
        for pat_name, pat_sig in self.active_patterns_used:
            self.pattern_total[pat_name] += 1
            if pat_sig == actual:
                self.pattern_win[pat_name] += 1
            
            total = self.pattern_total[pat_name]
            if total > 0:
                self.pattern_wr[pat_name] = self.pattern_win[pat_name] / total
    
    # =========================================================
    # 🎯 PATTERNS 1-10
    # =========================================================
    def pattern_odd_even(self, nums):
        if len(nums) < 5: return None, 0, "odd_even"
        last5 = nums[-5:]
        odds = sum(1 for x in last5 if x % 2 == 1)
        evens = 5 - odds
        if odds >= 4:
            self.pattern_stats["odd_4+"] += 1
            return "Small", 72, "odd_even"
        if evens >= 4:
            self.pattern_stats["even_4+"] += 1
            return "Big", 72, "odd_even"
        return None, 0, "odd_even"
    
    def pattern_high_low(self, nums):
        if len(nums) < 5: return None, 0, "high_low"
        last5 = nums[-5:]
        highs = sum(1 for x in last5 if x >= 5)
        if highs >= 4:
            self.pattern_stats["high_4+"] += 1
            return "Small", 78, "high_low"
        if highs <= 1:
            self.pattern_stats["low_4+"] += 1
            return "Big", 78, "high_low"
        return None, 0, "high_low"
    
    def pattern_number_repeat(self, nums):
        if len(nums) < 3: return None, 0, "repeat"
        last = nums[-1]
        repeat = 1
        for x in reversed(nums[:-1]):
            if x == last: repeat += 1
            else: break
        if repeat >= 3:
            self.pattern_stats[f"repeat_{last}"] += 1
            if last >= 5:
                return "Small", 82, "repeat"
            else:
                return "Big", 82, "repeat"
        return None, 0, "repeat"
    
    def pattern_number_pair(self, nums):
        if len(nums) < 15: return None, 0, "pair"
        last2 = tuple(nums[-2:])
        next_after = []
        for i in range(len(nums) - 3):
            if tuple(nums[i:i+2]) == last2:
                next_after.append(nums[i+2])
        if len(next_after) < 3: return None, 0, "pair"
        counter = Counter(next_after)
        most_common, count = counter.most_common(1)[0]
        if count / len(next_after) >= 0.60:
            self.pattern_stats["pair_markov"] += 1
            if most_common >= 5:
                return "Big", 78, "pair"
            else:
                return "Small", 78, "pair"
        return None, 0, "pair"
    
    def pattern_sum_analysis(self, nums):
        if len(nums) < 5: return None, 0, "sum"
        s = sum(nums[-5:])
        if s >= 32:
            self.pattern_stats["sum_high"] += 1
            return "Small", 76, "sum"
        if s <= 13:
            self.pattern_stats["sum_low"] += 1
            return "Big", 76, "sum"
        return None, 0, "sum"
    
    def pattern_distance(self, nums):
        if len(nums) < 6: return None, 0, "distance"
        distances = [abs(nums[i] - nums[i+1]) for i in range(-5, -1)]
        avg_dist = sum(distances) / len(distances)
        if avg_dist <= 2:
            if nums[-1] >= 5:
                return "Small", 72, "distance"
            else:
                return "Big", 72, "distance"
        if avg_dist >= 6:
            return "Big" if nums[-1] < 5 else "Small", 72, "distance"
        return None, 0, "distance"
    
    def pattern_zone(self, nums):
        if len(nums) < 10: return None, 0, "zone"
        last10 = nums[-10:]
        zone_a = sum(1 for x in last10 if x <= 4)
        zone_b = 10 - zone_a
        if zone_b >= 8:
            self.pattern_stats["zone_b_8+"] += 1
            return "Small", 88, "zone"
        if zone_a >= 8:
            self.pattern_stats["zone_a_8+"] += 1
            return "Big", 88, "zone"
        return None, 0, "zone"
    
    def pattern_bs_streak(self, nums):
        if len(nums) < 5: return None, 0, "bs_streak"
        bs = ["Big" if n >= 5 else "Small" for n in nums]
        streak = 1
        for x in reversed(bs[:-1]):
            if x == bs[-1]: streak += 1
            else: break
        if streak >= 6:
            self.pattern_stats["bs_continue_6+"] += 1
            return bs[-1], 88, "bs_streak"
        if streak == 4:
            self.pattern_stats["bs_reverse_4"] += 1
            return "Small" if bs[-1] == "Big" else "Big", 80, "bs_streak"
        return None, 0, "bs_streak"
    
    def pattern_transition(self, nums):
        if len(nums) < 30: return None, 0, "transition"
        for i in range(len(nums) - 1):
            self.transition_matrix[nums[i]][nums[i+1]] += 1
        last = nums[-1]
        next_counts = self.transition_matrix[last]
        if not next_counts or sum(next_counts.values()) < 5:
            return None, 0, "transition"
        big_votes = sum(c for n, c in next_counts.items() if n >= 5)
        small_votes = sum(c for n, c in next_counts.items() if n < 5)
        total = big_votes + small_votes
        if total == 0: return None, 0, "transition"
        big_pct = big_votes / total
        if big_pct >= 0.70:
            self.pattern_stats["transition_big"] += 1
            return "Big", min(big_pct * 100, 90), "transition"
        elif big_pct <= 0.30:
            self.pattern_stats["transition_small"] += 1
            return "Small", min((1 - big_pct) * 100, 90), "transition"
        return None, 0, "transition"
    
    def pattern_frequency(self, nums):
        if len(nums) < 30: return None, 0, "frequency"
        recent100 = nums[-100:] if len(nums) >= 100 else nums
        freq = Counter(recent100)
        
        rare_big = sum(1 for n in range(5, 10) if freq.get(n, 0) < 8)
        rare_small = sum(1 for n in range(0, 5) if freq.get(n, 0) < 8)
        common_big = sum(1 for n in range(5, 10) if freq.get(n, 0) > 13)
        common_small = sum(1 for n in range(0, 5) if freq.get(n, 0) > 13)
        
        if rare_big >= 3:
            self.pattern_stats["freq_rare_big"] += 1
            return "Big", 78, "frequency"
        if rare_small >= 3:
            self.pattern_stats["freq_rare_small"] += 1
            return "Small", 78, "frequency"
        if common_big >= 4:
            self.pattern_stats["freq_common_big"] += 1
            return "Big", 76, "frequency"
        if common_small >= 4:
            self.pattern_stats["freq_common_small"] += 1
            return "Small", 76, "frequency"
        return None, 0, "frequency"
    
    # =========================================================
    # 🆕 TOP NUMBERS
    # =========================================================
    def get_top_numbers(self, nums, signal, top_n=3):
        if signal == "Big":
            candidates = [5, 6, 7, 8, 9]
        else:
            candidates = [0, 1, 2, 3, 4]
        
        if len(nums) < 30:
            if signal == "Big":
                default = [(7, 30), (8, 25), (6, 22), (5, 13), (9, 10)]
            else:
                default = [(2, 30), (3, 25), (1, 22), (4, 13), (0, 10)]
            return default[:top_n]
        
        recent = nums[-100:] if len(nums) >= 100 else nums
        freq = Counter(recent)
        candidate_total = sum(freq.get(n, 0) for n in candidates)
        
        if candidate_total == 0:
            if signal == "Big":
                return [(7, 30), (8, 25), (6, 22)][:top_n]
            else:
                return [(2, 30), (3, 25), (1, 22)][:top_n]
        
        probs = []
        for n in candidates:
            count = freq.get(n, 0)
            prob = (count / candidate_total) * 100
            probs.append((n, prob))
        
        probs.sort(key=lambda x: x[1], reverse=True)
        
        result = []
        for n, p in probs[:top_n]:
            result.append((n, max(p, 5)))
        
        return result
    
    # =========================================================
    # 🎯 MAIN SIGNAL GENERATOR (v3.0)
    # =========================================================
    def generate_signal(self, nums):
        patterns = [
            self.pattern_odd_even(nums),
            self.pattern_high_low(nums),
            self.pattern_number_repeat(nums),
            self.pattern_number_pair(nums),
            self.pattern_sum_analysis(nums),
            self.pattern_distance(nums),
            self.pattern_zone(nums),
            self.pattern_bs_streak(nums),
            self.pattern_transition(nums),
            self.pattern_frequency(nums),
        ]
        
        # 🆕 SOLO MODE — Pattern 1 ခု 88%+ + WR 60%+
        for sig, conf, pat_name in patterns:
            if sig is None: continue
            if conf >= 88 and self.pattern_wr[pat_name] >= 0.60:
                return sig, conf, f"Solo {pat_name} ({conf:.0f}%)", [(pat_name, sig)]
        
        # Weighted Vote
        big_score = 0.0
        small_score = 0.0
        patterns_used = []
        
        for sig, conf, pat_name in patterns:
            if sig is None: continue
            
            pat_wr = self.pattern_wr[pat_name]
            wr_weight = 0.5 + pat_wr
            base_weight = conf / 100.0
            final_weight = base_weight * wr_weight
            
            if sig == "Big":
                big_score += final_weight
            else:
                small_score += final_weight
            
            patterns_used.append((pat_name, sig))
        
        total = big_score + small_score
        if total < 0.5:
            return None, 0, "No pattern", []
        
        big_pct = big_score / total
        
        # 🆕 TRIPLE CONFIRMATION
        big_count = sum(1 for _, sig in patterns_used if sig == "Big")
        small_count = sum(1 for _, sig in patterns_used if sig == "Small")
        
        if big_count >= 3 and small_count == 0:
            return "Big", 95, f"Triple Confirm ({big_count}x)", patterns_used
        if small_count >= 3 and big_count == 0:
            return "Small", 95, f"Triple Confirm ({small_count}x)", patterns_used
        
        # 🆕 Threshold 85% (STRICT)
        if big_pct >= 0.85:
            return "Big", big_pct * 100, f"High Conf ({big_pct*100:.0f}%)", patterns_used
        elif big_pct <= 0.15:
            return "Small", (1 - big_pct) * 100, f"High Conf ({(1-big_pct)*100:.0f}%)", patterns_used
        
        return None, 0, f"Low conf ({big_pct*100:.0f}%)", patterns_used
    
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
            self.update_pattern_wr(current_result)
            
            if win:
                self.total_wins += 1
                step_key = min(self.current_step, 3)
                self.win_by_step[step_key] += 1
                self.consecutive_losses = 0
                self.current_step = 0
                
                self.send_telegram(
                    f"✅ <b>WIN at Step {self.current_step+1 if False else step_key+1}</b>\n"
                    f"🔢 Number: {number} ({current_result})\n"
                    f"📊 WR: {self.get_wr():.1f}% | Win3: {self.get_win3_rate():.1f}%"
                )
            else:
                self.total_losses += 1
                self.current_step += 1
                self.consecutive_losses += 1
                
                # 🆕 Step 3+ Alert (Martingale မထိ)
                if self.current_step >= 3:
                    self.send_telegram(
                        f"⚠️ <b>Step {self.current_step+1} ({self.get_multiplier()}x)</b>\n"
                        f"Continuing to win..."
                    )
            
            self.active_prediction = None
            self.active_patterns_used = []
        
        self.number_window.append(number)
        self.number_freq[number] += 1
        
        if len(self.number_window) < 10:
            self.send_telegram(f"⏳ Warm-up {short} ({len(self.number_window)}/10)")
            return
        
        nums = list(self.number_window)
        signal, conf, reason, patterns_used = self.generate_signal(nums)
        
        if signal is None:
            self.total_skips += 1
            self.send_telegram(f"⏸️ <b>SKIP</b> {short}\nReason: {reason}")
            return
        
        # Top 3 Numbers
        top_numbers = self.get_top_numbers(nums, signal, top_n=3)
        top_str = "\n".join([
            f"   {i+1}️⃣ <b>{num}</b> ({prob:.0f}%)"
            for i, (num, prob) in enumerate(top_numbers)
        ])
        
        self.active_prediction = signal
        self.active_patterns_used = patterns_used
        self.total_signals += 1
        self.last_triggered_reason = reason
        
        stars = "⭐" * min(int(conf / 20), 5)
        self.send_telegram(
            f"🔢 <b>NUMBER BOT v3.0 SIGNAL</b> {stars}\n"
            f"📅 Period: {short}\n"
            f"📌 {reason}\n"
            f"🎯 <b>{signal.upper()}</b>\n\n"
            f"📊 <b>Top 3 Numbers:</b>\n"
            f"{top_str}\n\n"
            f"💰 Step {self.current_step+1} ({self.get_multiplier()}x)\n"
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
                            f"📊 <b>NUMBER BOT v3.0 STATUS</b>\n\n"
                            f"⚙️ {'PAUSED 🛑' if agent.is_paused else 'RUNNING 🟢'}\n"
                            f"Signals: {agent.total_signals} | Skips: {agent.total_skips}\n"
                            f"✅ W: {agent.total_wins} | ❌ L: {agent.total_losses}\n"
                            f"📈 WR: {agent.get_wr():.2f}%\n"
                            f"🎯 Win3: {agent.get_win3_rate():.1f}%\n"
                            f"💰 Step: {agent.current_step+1} ({agent.get_multiplier()}x)"
                        )
                    elif txt == "/pause":
                        agent.is_paused = True
                        agent.send_telegram("🛑 Paused")
                    elif txt == "/resume":
                        agent.is_paused = False
                        agent.send_telegram("🟢 Resumed")
                    elif txt == "/reset":
                        agent.current_step = 0
                        agent.consecutive_losses = 0
                        agent.send_telegram("🔄 Step reset")
                    elif txt == "/patterns":
                        top = sorted(agent.pattern_wr.items(), key=lambda x: x[1], reverse=True)
                        s = "\n".join([
                            f"{name}: {wr*100:.0f}% ({agent.pattern_total[name]}x)"
                            for name, wr in top[:10]
                        ])
                        agent.send_telegram(f"🎯 <b>Pattern WR</b>\n{s}")
                    elif txt == "/help":
                        agent.send_telegram(
                            "🤖 <b>Commands</b>\n"
                            "/status - Stats\n"
                            "/patterns - Pattern WR\n"
                            "/pause - Pause\n"
                            "/resume - Resume\n"
                            "/reset - Reset step"
                        )
        except Exception as e:
            print(f"TG Poll: {e}", flush=True)
        time.sleep(1)


# ==========================================
# 🚀 MAIN LOOP
# ==========================================
def run_bot():
    print("🔢 Number Bot v3.0 (Triple Goal) starting...", flush=True)
    agent = NumberPatternEngineV3()
    threading.Thread(target=poll_telegram, args=(agent,), daemon=True).start()
    
    last_period = ""
    url = "https://6lotteryapi.com/api/webapi/GetNoaverageEmerdList"
    auth = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpYXQiOiIxNzg3OTgxNTA5IiwibmJmIjoiMTc4Nzk4MTUwOSIsImV4cCI6IjE3ODc5ODMzMDkiLCJodHRwOi8vc2NoZW1hcy5taWNyb3NvZnQuY29tL3dzLzIwMDgvMDYvaWRlbnRpdHkvY2xhaW1zL2V4cGlyYXRpb24iOiI4LzI5LzIwMjYgMTI6MzE2NDkgUE0iLCJodHRwOi8vc2NoZW1hcy5taWNyb3NvZnQuY29tL3dzLzIwMDgvMDYvaWRlbnRpdHkvY2xhaW1zL3JvbGUiOiJBY2Nlc3NfVG9rZW4iLCJVc2VySWQiOiIxMDEyMjEzIiwiVXNlck5hbWUiOiI5NTk3NDA5MzkzNzAiLCJVc2VyUGhvdG8iOiI5IiwiTmlja05hbWUiOiJUaGVrR3lpIiwiQW1vdW50IjoiODcuMzAiLCJJbnRlZ3JhbCI6IjAiLCJMb2dpbk1hcmsiOiJINSIsImxvZ2luVGltZSI6IjcvMjkvMjAyNiAxMjowMTo0OSBQTSIsImxvZ2luSVBBZGRyZXNzIjoiNDUuNDEuMTA0LjI0MCIsImRiTnVtYmVyIjoiMCIsIklzdmFsaWRhdG9yIjoiMCIsIktleUNvZGUiOiIzMjMzMiIsImRva2VuVHlwZSI6IjJBY2Nlc3NfVG9rZW4iLCJob25lVHlwZSI6IjAiLCJVc2VyVHlwZSI6IjAiLCJVc2VyTmFtZ2UiOiIuIiwiaXNzIjoiand0SXNzdWVyIiwiYXVkIjoibG90dGVyeVRpY2tldCJ9.ZL0Y9gexUTCsKwWeZhCLAAw8AABEYJt0GnIzIviMG4g"
    
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
            r = requests.post(url, headers=headers, json=payload, timeout=10)
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
                        print(f"🔢 Sync {period} → {number}", flush=True)
                        agent.analyze_round(period, number)
        except Exception as e:
            print(f"API Err: {e}", flush=True)
        time.sleep(1.5)


threading.Thread(target=run_bot, daemon=True).start()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
