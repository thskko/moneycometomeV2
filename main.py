import requests
import time
import os
import threading
from collections import deque, Counter, defaultdict
from datetime import datetime
from flask import Flask, jsonify

TELEGRAM_TOKEN = "8913070806:AAF3rP0zKJtofE-5KVesqcdoHzn7Go0avho"
CHAT_ID = "-1004402480797"

app = Flask(__name__)
global_agent = None

# Dynamic Settings
BASE_THRESHOLD = 70


# ==========================================
# 📊 DASHBOARD
# ==========================================
@app.route('/')
def home():
    global global_agent
    if not global_agent:
        return "<h3>📊 Mean Reversion v2.0 starting...</h3>"
    
    a = global_agent
    total = a.total_wins + a.total_losses
    wr = (a.total_wins / total * 100) if total > 0 else 0.0
    win3 = a.get_win3_rate()
    
    last_20 = " ".join([("B" if n >= 5 else "S") for n in list(a.number_window)[-20:]])
    
    pat_stats = ""
    for k, v in a.pattern_stats.most_common(10):
        pat_stats += f"<tr><td>{k}</td><td>{v}</td></tr>"
    
    pat_wr = ""
    for k, v in sorted(a.pattern_wr.items(), key=lambda x: x[1], reverse=True)[:10]:
        pat_wr += f"<tr><td>{k}</td><td>{v*100:.1f}%</td></tr>"
    
    return f"""
    <html><head><title>Mean Reversion v2.0</title>
    <meta http-equiv="refresh" content="15">
    <style>
    body{{background:#0a0e27;color:#0ff;font-family:monospace;padding:20px}}
    h1,h2{{color:#0ff;text-shadow:0 0 10px #0ff}}
    .box{{background:#1a1f3a;border:1px solid #0ff;padding:15px;margin:10px 0;border-radius:8px}}
    .big{{font-size:32px;color:#0f0;font-weight:bold}}
    .nums{{font-size:18px;color:#ff0;word-wrap:break-word;letter-spacing:3px}}
    table{{width:100%;border-collapse:collapse}}
    th,td{{padding:6px;border:1px solid #0ff;text-align:left;font-size:12px}}
    th{{background:#0ff;color:#000}}
    </style></head><body>
    <h1>📊 MEAN REVERSION v2.0</h1>
    
    <div class="box">
      <h2>📊 Performance</h2>
      <p>Status: <b>{'PAUSED 🛑' if a.is_paused else 'RUNNING 🟢'}</b></p>
      <p>Signals: {a.total_signals} | Skips: {a.total_skips}</p>
      <p>Wins: {a.total_wins} | Losses: {a.total_losses}</p>
      <p>Win Rate: <span class="big">{wr:.2f}%</span></p>
      <p>Win-in-3: <span class="big">{win3:.1f}%</span></p>
      <p>Current Step: {a.current_step + 1} ({a.get_multiplier()}x)</p>
      <p>Threshold: <b>{a.get_dynamic_threshold():.0f}%</b></p>
    </div>
    
    <div class="box">
      <h2>🎯 Last 20</h2>
      <p class="nums">{last_20}</p>
    </div>
    
    <div class="box">
      <h2>📈 Pattern Count</h2>
      <table>
        <tr><th>Pattern</th><th>Count</th></tr>
        {pat_stats}
      </table>
    </div>
    
    <div class="box">
      <h2>🎯 Pattern WR</h2>
      <table>
        <tr><th>Pattern</th><th>WR</th></tr>
        {pat_wr}
      </table>
    </div>
    
    <div class="box">
      <h2>📅 Last Period</h2>
      <p>{a.last_period} → Number: {a.last_number} → {a.last_result}</p>
      <p>Signal: {a.last_signal} | Reason: {a.last_reason}</p>
    </div>
    </body></html>
    """


# ==========================================
# 📊 MEAN REVERSION v2.0 ENGINE
# ==========================================
class MeanReversionEngineV2:
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
        self.last_signal = "None"
        self.last_reason = "None"
        
        self.total_signals = 0
        self.total_wins = 0
        self.total_losses = 0
        self.total_skips = 0
        self.win_by_step = {0: 0, 1: 0, 2: 0, 3: 0}
        
        self.pattern_stats = Counter()
        
        # 🆕 Pattern WR Tracking
        self.pattern_wr = defaultdict(lambda: 0.5)
        self.pattern_win = defaultdict(int)
        self.pattern_total = defaultdict(int)
    
    def get_multiplier(self):
        return 2 ** self.current_step
    
    # =========================================================
    # 🆕 DYNAMIC THRESHOLD (Update 2)
    # =========================================================
    def get_dynamic_threshold(self):
        """WR အလိုက် Threshold auto-adjust"""
        total = self.total_wins + self.total_losses
        if total < 10:
            return 65  # Data နည်းရင် လျှော့
        
        wr = self.get_wr()
        
        if wr >= 75:
            return 78   # WR ကောင်းရင် တင်း
        elif wr >= 65:
            return 72   # ပုံမှန်
        elif wr >= 55:
            return 68   # လျှော့
        else:
            return 65   # အလွန်လျှော့
    
    def send_telegram(self, message):
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {"chat_id": CHAT_ID, "text": message, "parse_mode": "HTML"}
        try:
            r = requests.post(url, json=payload, timeout=10)
            print(f"📤 TG: {r.status_code}", flush=True)
        except Exception as e:
            print(f"❌ TG Err: {e}", flush=True)
    
    # =========================================================
    # 🆕 STATISTICAL CONFIRMATION (Update 1)
    # =========================================================
    def statistical_confirmation(self, arr, signal):
        """Z-score Test — Signal Confirm"""
        if len(arr) < 30:
            return True, 50  # Data နည်းရင် pass
        
        recent = arr[-50:]
        n = len(recent)
        
        if signal == "Big":
            count = recent.count("Big")
            expected = n / 2
            std = (n * 0.25) ** 0.5
            z_score = (count - expected) / std if std > 0 else 0
            
            # Z-score > 1.5 → Strong
            if z_score > 1.5:
                return True, min(95, 70 + z_score * 5)
            elif z_score > 0.5:
                return True, 65
            else:
                return False, 0
        
        else:  # Small
            count = recent.count("Small")
            expected = n / 2
            std = (n * 0.25) ** 0.5
            z_score = (count - expected) / std if std > 0 else 0
            
            if z_score > 1.5:
                return True, min(95, 70 + z_score * 5)
            elif z_score > 0.5:
                return True, 65
            else:
                return False, 0
    
    # =========================================================
    # 🆕 MULTI-TIMEFRAME CONSENSUS (Update 3)
    # =========================================================
    def multi_tf_consensus(self, arr):
        """Short + Medium + Long — 3 ခုလုံး တူရင် Signal"""
        if len(arr) < 100:
            return None, 0, "mtf"
        
        s_big = arr[-10:].count("Big")
        m_big = arr[-30:].count("Big")
        l_big = arr[-100:].count("Big")
        
        # Short (10) — Big 7+ or 3-
        short = "Big" if s_big >= 7 else "Small" if s_big <= 3 else None
        
        # Medium (30) — Big 20+ or 10-
        medium = "Big" if m_big >= 20 else "Small" if m_big <= 10 else None
        
        # Long (100) — Big 60+ or 40-
        long_t = "Big" if l_big >= 60 else "Small" if l_big <= 40 else None
        
        # 3 ခုလုံး တူ
        if short and medium and long_t and short == medium == long_t:
            self.pattern_stats["mtf_consensus"] += 1
            return short, 90, "mtf"
        
        return None, 0, "mtf"
    
    # =========================================================
    # PATTERN 1: MEAN REVERSION
    # =========================================================
    def pattern_mean_reversion(self, arr):
        if len(arr) < 20: return None, 0, "mean_rev"
        
        b20 = arr[-20:].count("Big")
        b10 = arr[-10:].count("Big")
        
        # Extreme
        if b20 >= 18:
            self.pattern_stats["mr_18+"] += 1
            return "Small", 92, "mean_rev"
        if b20 <= 2:
            self.pattern_stats["mr_2-"] += 1
            return "Big", 92, "mean_rev"
        
        if b20 >= 17:
            self.pattern_stats["mr_17+"] += 1
            return "Small", 88, "mean_rev"
        if b20 <= 3:
            self.pattern_stats["mr_3-"] += 1
            return "Big", 88, "mean_rev"
        
        if b20 >= 16 and b10 >= 8:
            self.pattern_stats["mr_multi"] += 1
            return "Small", 85, "mean_rev"
        if b20 <= 4 and b10 <= 2:
            self.pattern_stats["mr_multi_low"] += 1
            return "Big", 85, "mean_rev"
        
        return None, 0, "mean_rev"
    
    # =========================================================
    # PATTERN 2: ZONE REJECTION
    # =========================================================
    def pattern_zone(self, arr):
        if len(arr) < 10: return None, 0, "zone"
        
        b10 = arr[-10:].count("Big")
        
        if b10 >= 8:
            self.pattern_stats["zone_8+"] += 1
            return "Small", 82, "zone"
        if b10 <= 2:
            self.pattern_stats["zone_2-"] += 1
            return "Big", 82, "zone"
        
        return None, 0, "zone"
    
    # =========================================================
    # PATTERN 3: DRAGON
    # =========================================================
    def pattern_dragon(self, arr):
        if len(arr) < 8: return None, 0, "dragon"
        
        streak = 1
        for x in reversed(arr[:-1]):
            if x == arr[-1]: streak += 1
            else: break
        
        if streak >= 8:
            self.pattern_stats["dragon_rev_8+"] += 1
            return "Small" if arr[-1]=="Big" else "Big", 90, "dragon"
        if streak >= 6:
            self.pattern_stats["dragon_cont_6+"] += 1
            return arr[-1], 88, "dragon"
        if streak >= 5:
            self.pattern_stats["dragon_rev_5"] += 1
            return "Small" if arr[-1]=="Big" else "Big", 80, "dragon"
        
        return None, 0, "dragon"
    
    # =========================================================
    # PATTERN 4: MARKOV 2
    # =========================================================
    def pattern_markov2(self, arr):
        if len(arr) < 15: return None, 0, "markov2"
        
        last2 = tuple(arr[-2:])
        next_after = []
        for i in range(len(arr) - 3):
            if tuple(arr[i:i+2]) == last2:
                next_after.append(arr[i+2])
        
        if len(next_after) < 3:
            return None, 0, "markov2"
        
        counter = Counter(next_after)
        most_common, count = counter.most_common(1)[0]
        
        if count / len(next_after) >= 0.60:
            self.pattern_stats["markov2_hit"] += 1
            return most_common, 78, "markov2"
        
        return None, 0, "markov2"
    
    # =========================================================
    # PATTERN 5: FREQUENCY BIAS
    # =========================================================
    def pattern_frequency(self, arr):
        if len(arr) < 30: return None, 0, "freq"
        
        b30 = arr[-30:].count("Big")
        b10 = arr[-10:].count("Big")
        
        if b30 >= 22:
            self.pattern_stats["freq_22+"] += 1
            return "Small", 80, "freq"
        if b30 <= 8:
            self.pattern_stats["freq_8-"] += 1
            return "Big", 80, "freq"
        
        if b30 >= 20 and b10 >= 8:
            self.pattern_stats["freq_multi_high"] += 1
            return "Small", 78, "freq"
        if b30 <= 10 and b10 <= 2:
            self.pattern_stats["freq_multi_low"] += 1
            return "Big", 78, "freq"
        
        return None, 0, "freq"
    
    # =========================================================
    # 🆕 UPDATE PATTERN WR
    # =========================================================
    def update_pattern_wr(self, actual):
        for pat_name, sig in self.active_patterns_used:
            self.pattern_total[pat_name] += 1
            if sig == actual:
                self.pattern_win[pat_name] += 1
            
            t = self.pattern_total[pat_name]
            if t > 0:
                self.pattern_wr[pat_name] = self.pattern_win[pat_name] / t
    
    # =========================================================
    # 🎯 MAIN SIGNAL GENERATOR v2.0
    # =========================================================
    def generate_signal(self, arr):
        """
        Mean Reversion + 3 Updates:
        1. Statistical Confirmation
        2. Dynamic Threshold
        3. Multi-Timeframe Consensus
        """
        
        # 🆕 1) Multi-TF Consensus (Highest Priority)
        mtf_sig, mtf_conf, _ = self.multi_tf_consensus(arr)
        if mtf_sig and mtf_conf >= 85:
            return mtf_sig, mtf_conf, "🌐 Multi-TF Consensus", [("mtf", mtf_sig)]
        
        # 2) Run Pattern 5
        patterns = [
            self.pattern_mean_reversion(arr),
            self.pattern_zone(arr),
            self.pattern_dragon(arr),
            self.pattern_markov2(arr),
            self.pattern_frequency(arr),
        ]
        
        # Weighted Vote
        big_score = 0.0
        small_score = 0.0
        patterns_used = []
        reasons = []
        
        for sig, conf, pat_name in patterns:
            if sig is None: continue
            
            # 🆕 Pattern WR Weight
            pat_wr = self.pattern_wr[pat_name]
            wr_weight = 0.5 + pat_wr
            
            weight = (conf / 100.0) * wr_weight
            if sig == "Big":
                big_score += weight
                reasons.append(f"B({pat_name[:4]})")
            else:
                small_score += weight
                reasons.append(f"S({pat_name[:4]})")
            
            patterns_used.append((pat_name, sig))
        
        total = big_score + small_score
        if total < 1.0:
            return None, 0, f"No pattern (score {total:.2f})", []
        
        big_pct = big_score / total
        conf = max(big_pct, 1 - big_pct) * 100
        
        # Preliminary Signal
        if big_pct >= 0.5:
            final_signal = "Big"
        else:
            final_signal = "Small"
        
        # 🆕 2) Statistical Confirmation
        stat_ok, stat_conf = self.statistical_confirmation(arr, final_signal)
        if not stat_ok:
            return None, conf, f"Statistical fail ({stat_conf:.0f}%)", patterns_used
        
        # 🆕 3) Dynamic Threshold
        threshold = self.get_dynamic_threshold()
        if conf < threshold:
            return None, conf, f"Weak ({conf:.0f}% < {threshold}%)", patterns_used
        
        reason = f"MR: {' + '.join(reasons)} ({conf:.0f}%)"
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
        
        # 1) Evaluate
        if self.active_prediction:
            win = (self.active_prediction == current_result)
            
            # 🆕 Update Pattern WR
            self.update_pattern_wr(current_result)
            
            if win:
                self.total_wins += 1
                step_key = min(self.current_step, 3)
                self.win_by_step[step_key] += 1
                self.current_step = 0
                
                self.send_telegram(
                    f"✅ <b>WIN</b>\n"
                    f"🔢 Number: {number} ({current_result})\n"
                    f"📊 WR: {self.get_wr():.1f}% | Win3: {self.get_win3_rate():.1f}%"
                )
            else:
                self.total_losses += 1
                self.current_step += 1
                
                if self.current_step >= 3:
                    self.send_telegram(
                        f"⚠️ <b>Step {self.current_step+1} ({self.get_multiplier()}x)</b>"
                    )
            
            self.active_prediction = None
            self.active_patterns_used = []
        
        # 2) Append
        self.number_window.append(number)
        
        # 3) Warm-up
        if len(self.number_window) < 20:
            self.send_telegram(f"⏳ Warm-up {short} ({len(self.number_window)}/20)")
            return
        
        # 4) Signal
        arr = ["Big" if n >= 5 else "Small" for n in self.number_window]
        signal, conf, reason, patterns_used = self.generate_signal(arr)
        
        self.last_signal = signal if signal else "SKIP"
        self.last_reason = reason
        
        # 5) Skip
        if signal is None:
            self.total_skips += 1
            self.send_telegram(f"⏸️ <b>SKIP</b> {short}\nReason: {reason}")
            return
        
        # 6) Signal
        self.active_prediction = signal
        self.active_patterns_used = patterns_used
        self.total_signals += 1
        
        stars = "⭐" * min(int(conf / 20), 5)
        self.send_telegram(
            f"📊 <b>MEAN REVERSION v2.0</b> {stars}\n"
            f"📅 Period: {short}\n"
            f"📌 {reason}\n"
            f"🎯 <b>{signal.upper()}</b>\n"
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
# TELEGRAM COMMANDS
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
                            f"📊 <b>MEAN REVERSION v2.0</b>\n\n"
                            f"⚙️ {'PAUSED 🛑' if agent.is_paused else 'RUNNING 🟢'}\n"
                            f"Signals: {agent.total_signals} | Skips: {agent.total_skips}\n"
                            f"✅ W: {agent.total_wins} | ❌ L: {agent.total_losses}\n"
                            f"📈 WR: {agent.get_wr():.2f}%\n"
                            f"🎯 Win3: {agent.get_win3_rate():.1f}%\n"
                            f"📊 Threshold: {agent.get_dynamic_threshold():.0f}%"
                        )
                    elif txt == "/patterns":
                        s = "📈 <b>Pattern WR</b>\n"
                        for k, v in sorted(agent.pattern_wr.items(), key=lambda x: x[1], reverse=True)[:10]:
                            total = agent.pattern_total[k]
                            s += f"{k}: {v*100:.0f}% ({total}x)\n"
                        agent.send_telegram(s)
                    elif txt == "/pause":
                        agent.is_paused = True
                        agent.send_telegram("🛑 Paused")
                    elif txt == "/resume":
                        agent.is_paused = False
                        agent.send_telegram("🟢 Resumed")
                    elif txt == "/reset":
                        agent.current_step = 0
                        agent.send_telegram("🔄 Step reset")
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
# MAIN LOOP
# ==========================================
def run_bot():
    print("📊 Mean Reversion v2.0 (3 Updates) starting...", flush=True)
    agent = MeanReversionEngineV2()
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
                        print(f"📊 Sync {period} → {number}", flush=True)
                        agent.analyze_round(period, number)
        except Exception as e:
            print(f"API Err: {e}", flush=True)
        time.sleep(1.5)


threading.Thread(target=run_bot, daemon=True).start()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
