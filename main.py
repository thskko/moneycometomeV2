import requests
import time
import os
import json
import threading
from collections import deque, Counter
from datetime import datetime, timedelta
from flask import Flask, jsonify

TELEGRAM_TOKEN = "8771982889:AAFzEnu7-DSl4gNktrGfpS1p28haP8-hoMs"
CHAT_ID = " -1004357168336"

app = Flask(__name__)
global_agent = None

# =========================================================
# 📊 DASHBOARD
# =========================================================
@app.route('/')
def home():
    global global_agent
    if not global_agent:
        return "<h3>🚀 AI Sniper v3.0 starting...</h3>"
    
    a = global_agent
    total = a.total_wins + a.total_losses
    wr = (a.total_wins / total * 100) if total > 0 else 0.0
    win3 = a.get_win3_rate()
    
    # Bot leaderboard
    top_bots = sorted(a.bot_stats.items(), key=lambda x: x[1]["wr"], reverse=True)[:10]
    bot_rows = "".join([
        f"<tr><td>{bid}</td><td>{s['wins']}</td><td>{s['losses']}</td>"
        f"<td>{s['wr']*100:.1f}%</td><td>{s['weight']:.2f}</td></tr>"
        for bid, s in top_bots
    ])
    
    # Pattern stats
    pat_stats = "<br>".join([f"{k}: {v}" for k, v in a.pattern_stats.items()])
    
    # Confusion matrix
    cm = a.confusion_matrix
    
    return f"""
    <html><head><title>AI Sniper v3.0</title>
    <meta http-equiv="refresh" content="15">
    <style>
    body{{background:#0a0e27;color:#0ff;font-family:monospace;padding:20px}}
    h1,h2{{color:#0ff;text-shadow:0 0 10px #0ff}}
    .box{{background:#1a1f3a;border:1px solid #0ff;padding:15px;margin:10px 0;border-radius:8px}}
    .big{{font-size:32px;color:#0f0;font-weight:bold}}
    .red{{color:#f44}}
    table{{width:100%;border-collapse:collapse}}
    th,td{{padding:8px;border:1px solid #0ff;text-align:left}}
    th{{background:#0ff;color:#000}}
    </style></head><body>
    <h1>🚀 AI SNIPER ENGINE v3.0</h1>
    
    <div class="box">
      <h2>📊 Performance</h2>
      <p>Status: <b>{'PAUSED 🛑' if a.is_paused else 'RUNNING 🟢'}</b></p>
      <p>Signals: {a.total_signals} | Skips: {a.total_skips}</p>
      <p>Wins: {a.total_wins} | Losses: {a.total_losses}</p>
      <p>Win Rate: <span class="big">{wr:.2f}%</span></p>
      <p>Win-in-1-3-Steps: <span class="big">{win3:.1f}%</span></p>
      <p>Current Step: {a.current_step + 1} ({a.get_current_multiplier()}x)</p>
    </div>
    
    <div class="box">
      <h2>💰 Bankroll</h2>
      <p>{a.bankroll.get_status()}</p>
      <p>Peak: {a.bankroll.session_peak:.2f}</p>
      <p>Max Drawdown: {a.bankroll.max_drawdown:.2f}</p>
      <p>Daily Loss: {a.bankroll.daily_loss:.2f}</p>
    </div>
    
    <div class="box">
      <h2>🎯 Win by Step</h2>
      <p>S1: {a.win_by_step[0]} | S2: {a.win_by_step[1]} | S3: {a.win_by_step[2]} | S4+: {a.win_by_step[3]}</p>
    </div>
    
    <div class="box">
      <h2>📈 Confusion Matrix</h2>
      <p>Big→Big: {cm['BB']} | Big→Small: {cm['BS']}</p>
      <p>Small→Big: {cm['SB']} | Small→Small: {cm['SS']}</p>
      <p>Precision: {a.get_precision():.1f}% | Recall: {a.get_recall():.1f}% | F1: {a.get_f1():.1f}%</p>
    </div>
    
    <div class="box">
      <h2>🎲 Pattern Stats</h2>
      <p>{pat_stats}</p>
    </div>
    
    <div class="box">
      <h2>🏆 Top 10 Bots</h2>
      <table>
        <tr><th>Bot</th><th>W</th><th>L</th><th>WR</th><th>Weight</th></tr>
        {bot_rows}
      </table>
    </div>
    
    <div class="box">
      <h2>📅 Last Period</h2>
      <p>{a.last_period} → {a.last_result}</p>
      <p>Signal Source: {a.last_triggered_bot}</p>
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
        "balance": a.bankroll.balance
    })


# =========================================================
# 💰 BANKROLL TRACKER
# =========================================================
class BankrollTracker:
    def __init__(self, initial=1000):
        self.initial = initial
        self.balance = initial
        self.session_peak = initial
        self.max_drawdown = 0
        self.daily_loss = 0
        self.daily_reset = datetime.now().date()
    
    def reset_daily(self):
        today = datetime.now().date()
        if today != self.daily_reset:
            self.daily_loss = 0
            self.daily_reset = today
    
    def update(self, win, step, base_bet=1):
        self.reset_daily()
        bet = base_bet * (2 ** step)
        if win:
            self.balance += bet
        else:
            self.balance -= bet
            self.daily_loss += bet
        
        if self.balance > self.session_peak:
            self.session_peak = self.balance
        dd = self.session_peak - self.balance
        if dd > self.max_drawdown:
            self.max_drawdown = dd
    
    def should_stop(self):
        """10% loss ဆိုရင် ရပ်"""
        return self.daily_loss >= self.initial * 0.10
    
    def get_status(self):
        pnl = self.balance - self.initial
        pnl_pct = (pnl / self.initial) * 100
        icon = "🟢" if pnl >= 0 else "🔴"
        return f"{icon} {self.balance:.2f} ({pnl_pct:+.1f}%)"


# =========================================================
# 🎯 MAIN ENGINE
# =========================================================
class AISniperEngineV3:
    def __init__(self):
        global global_agent
        global_agent = self
        
        self.window = deque(maxlen=300)
        self.current_step = 0
        self.active_prediction = None
        self.is_paused = False
        self.last_period = "None"
        self.last_result = "None"
        self.last_triggered_bot = "None"
        
        self.total_signals = 0
        self.total_wins = 0
        self.total_losses = 0
        self.total_skips = 0
        self.consecutive_losses = 0
        self.max_consecutive_losses = 0
        
        self.win_by_step = {0: 0, 1: 0, 2: 0, 3: 0}
        
        self.bankroll = BankrollTracker(initial=1000)
        
        # Confusion matrix
        self.confusion_matrix = {"BB": 0, "BS": 0, "SB": 0, "SS": 0}
        
        # Pattern stats
        self.pattern_stats = Counter()
        
        # 50 Bots
        self.num_bots = 50
        self.bot_stats = {
            f"Bot_{i+1}": {"wins": 0, "losses": 0, "wr": 0.0, "weight": 1.0, "last_pred": None}
            for i in range(self.num_bots)
        }
        
        # Auto-optimizer counter
        self.rounds_since_optimize = 0
        
        # Confidence history
        self.confidence_history = deque(maxlen=50)

    def get_current_multiplier(self):
        return 2 ** self.current_step
    
    def send_telegram(self, message):
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {"chat_id": CHAT_ID, "text": message, "parse_mode": "HTML"}
        try:
            requests.post(url, json=payload, timeout=5)
        except Exception as e:
            print(f"TG Err: {e}", flush=True)
    
    # =========================================================
    # 🧠 50 BOT STRATEGIES
    # =========================================================
    def run_bot(self, bot_idx, arr):
        n = len(arr)
        if n < 15: return None
        
        # --- Group 1: Trend (0-9) ---
        if bot_idx == 0: return arr[-1]
        elif bot_idx == 1: return "Small" if arr[-1]=="Big" else "Big"
        elif bot_idx == 2: return "Big" if arr[-3:].count("Big")>=2 else "Small"
        elif bot_idx == 3: return "Small" if arr[-3:].count("Big")>=2 else "Big"
        elif bot_idx == 4: return "Big" if arr[-5:].count("Big")>=3 else "Small"
        elif bot_idx == 5: return "Small" if arr[-5:].count("Big")>=3 else "Big"
        elif bot_idx == 6:
            s=1
            for x in reversed(arr[:-1]):
                if x==arr[-1]: s+=1
                else: break
            return arr[-1] if s>=2 else ("Small" if arr[-1]=="Big" else "Big")
        elif bot_idx == 7:
            s=1
            for x in reversed(arr[:-1]):
                if x==arr[-1]: s+=1
                else: break
            return ("Small" if arr[-1]=="Big" else "Big") if s>=2 else arr[-1]
        elif bot_idx == 8:
            b=sum(1 for x in arr[-7:] if x=="Big")
            return "Big" if b>=4 else "Small"
        elif bot_idx == 9:
            b=sum(1 for x in arr[-10:] if x=="Big")
            return "Big" if b>=6 else "Small"
        
        # --- Group 2: Markov (10-19) ---
        elif bot_idx == 10:
            last=arr[-1]
            nxt=[arr[i+1] for i in range(n-1) if arr[i]==last]
            if len(nxt)>=3: return Counter(nxt).most_common(1)[0][0]
            return None
        elif bot_idx == 11:
            if n<20: return None
            p=tuple(arr[-2:])
            nxt=[arr[i+2] for i in range(n-2) if tuple(arr[i:i+2])==p]
            if len(nxt)>=3: return Counter(nxt).most_common(1)[0][0]
            return None
        elif bot_idx == 12:
            if n<25: return None
            p=tuple(arr[-3:])
            nxt=[arr[i+3] for i in range(n-3) if tuple(arr[i:i+3])==p]
            if len(nxt)>=2: return Counter(nxt).most_common(1)[0][0]
            return None
        elif bot_idx == 13:
            if n<30: return None
            p=tuple(arr[-4:])
            nxt=[arr[i+4] for i in range(n-4) if tuple(arr[i:i+4])==p]
            if len(nxt)>=2: return Counter(nxt).most_common(1)[0][0]
            return None
        elif bot_idx == 14:
            alt=sum(1 for i in range(-6,-1) if arr[i]!=arr[i+1])
            if alt>=5: return "Small" if arr[-1]=="Big" else "Big"
            return None
        elif bot_idx == 15:
            if arr[-2:]==["Big","Big"]:
                s=[arr[i+2] for i in range(n-2) if arr[i:i+2]==["Big","Big"]]
                if s: return Counter(s).most_common(1)[0][0]
            return None
        elif bot_idx == 16:
            if arr[-2:]==["Small","Small"]:
                b=[arr[i+2] for i in range(n-2) if arr[i:i+2]==["Small","Small"]]
                if b: return Counter(b).most_common(1)[0][0]
            return None
        elif bot_idx == 17:
            last=arr[-1]; gap=1
            for x in reversed(arr[:-1]):
                if x==last: gap+=1
                else: break
            if gap>=4: return "Small" if last=="Big" else "Big"
            return None
        elif bot_idx == 18:
            b=arr[-20:].count("Big")
            if b>=13: return "Small"
            if b<=7: return "Big"
            return None
        elif bot_idx == 19:
            b=arr[-30:].count("Big") if n>=30 else arr.count("Big")
            if b>=18: return "Small"
            if b<=12: return "Big"
            return None
        
        # --- Group 3: Statistical (20-29) ---
        elif bot_idx == 20:
            b=arr[-10:].count("Big")+1
            s=arr[-10:].count("Small")+1
            p=b/(b+s)
            if p>=0.65: return "Big"
            if p<=0.35: return "Small"
            return None
        elif bot_idx == 21:
            if n<20: return None
            b=arr[-20:].count("Big")+1
            s=arr[-20:].count("Small")+1
            p=b/(b+s)
            if p>=0.62: return "Big"
            if p<=0.38: return "Small"
            return None
        elif bot_idx == 22:
            b=arr[-15:].count("Big") if n>=15 else arr.count("Big")
            if b>=11: return "Small"
            if b<=4: return "Big"
            return None
        elif bot_idx == 23:
            bb=sum(1 for i in range(-15,0) if arr[i]=="Big" and arr[i+1]=="Big")
            if bb>=6: return "Small"
            return None
        elif bot_idx == 24:
            ss=sum(1 for i in range(-15,0) if arr[i]=="Small" and arr[i+1]=="Small")
            if ss>=6: return "Big"
            return None
        elif bot_idx == 25:
            s=1
            for x in reversed(arr[:-1]):
                if x==arr[-1]: s+=1
                else: break
            if s==3: return "Small" if arr[-1]=="Big" else "Big"
            return None
        elif bot_idx == 26:
            s=1
            for x in reversed(arr[:-1]):
                if x==arr[-1]: s+=1
                else: break
            if s==4: return "Small" if arr[-1]=="Big" else "Big"
            return None
        elif bot_idx == 27:
            if n<15: return None
            f5=arr[-10:-5].count("Big"); l5=arr[-5:].count("Big")
            if f5<=1 and l5>=3: return "Big"
            if f5>=3 and l5<=1: return "Small"
            return None
        elif bot_idx == 28:
            if n<20: return None
            b10=arr[-10:].count("Big"); b20=arr[-20:].count("Big")
            if b10>b20*0.6: return "Big"
            if b10<b20*0.4: return "Small"
            return None
        elif bot_idx == 29:
            b=arr[-25:].count("Big") if n>=25 else arr.count("Big")
            tn=min(25,n)
            if b>=tn-3: return "Small"
            if b<=3: return "Big"
            return None
        
        # --- Group 4: Pattern (30-39) ---
        elif bot_idx == 30:
            if arr[-3:]==["Big","Small","Small"]: return "Big"
            return None
        elif bot_idx == 31:
            if arr[-3:]==["Small","Big","Big"]: return "Small"
            return None
        elif bot_idx == 32:
            if arr[-3:]==["Big","Small","Big"]: return "Small"
            return None
        elif bot_idx == 33:
            if arr[-3:]==["Small","Big","Small"]: return "Big"
            return None
        elif bot_idx == 34:
            if arr[-4:]==["Big","Big","Small","Big"]: return "Small"
            return None
        elif bot_idx == 35:
            if arr[-4:]==["Small","Small","Big","Small"]: return "Big"
            return None
        elif bot_idx == 36:
            l5=arr[-5:]
            if l5[:2]==l5[-2:][::-1]:
                return "Small" if l5[-1]=="Big" else "Big"
            return None
        elif bot_idx == 37:
            if n<6: return None
            bl=[arr[-6:-4],arr[-4:-2],arr[-2:]]
            if bl[0]==bl[2] and bl[0]!=bl[1]:
                return bl[0][0]
            return None
        elif bot_idx == 38:
            sc=0
            for i,x in enumerate(arr[-10:]):
                w=1+(i/10)
                sc+=w if x=="Big" else -w
            if sc>2: return "Big"
            if sc<-2: return "Small"
            return None
        elif bot_idx == 39:
            if n<20: return None
            l5=arr[-5:].count("Big"); l20=arr[-20:].count("Big")
            if l5>=4 and l20<=8: return "Big"
            if l5<=1 and l20>=12: return "Small"
            return None
        
        # --- Group 5: AI/Adaptive (40-49) ---
        elif bot_idx == 40: return "Big" if arr.count("Big")>=n/2 else "Small"
        elif bot_idx == 41: return "Small" if arr.count("Big")>=n/2 else "Big"
        elif bot_idx == 42: return arr[-1]
        elif bot_idx == 43: return "Small" if arr[-1]=="Big" else "Big"
        elif bot_idx == 44:
            b=arr[:10].count("Big") if n>=10 else arr.count("Big")
            return "Big" if b>=5 else "Small"
        elif bot_idx == 45: return arr[-2] if n>=2 else "Big"
        elif bot_idx == 46: return "Small" if arr[-2]=="Big" else "Big" if n>=2 else "Small"
        elif bot_idx == 47: return arr[-3] if n>=3 else "Big"
        elif bot_idx == 48: return "Small" if arr[-4]=="Big" else "Big" if n>=4 else "Small"
        else:  # Bot 50
            bigs=sum(1 for s in self.bot_stats.values() if s.get("last_pred")=="Big")
            return "Small" if bigs>=25 else "Big"
    
    # =========================================================
    # 🎯 PATTERN DETECTION (Powerful)
    # =========================================================
    def detect_patterns(self, arr):
        """Special high-confidence patterns"""
        if len(arr) < 10: return None, 0
        
        # Dragon (5+ streak)
        s=1
        for x in reversed(arr[:-1]):
            if x==arr[-1]: s+=1
            else: break
        if s >= 5:
            return arr[-1], 85  # High confidence continue
        if s >= 7:
            return ("Small" if arr[-1]=="Big" else "Big"), 90  # Reverse
        
        # Ping-pong (6+ alternation)
        alt=sum(1 for i in range(-7,-1) if arr[i]!=arr[i+1])
        if alt >= 6:
            nxt = "Small" if arr[-1]=="Big" else "Big"
            return nxt, 80
        
        # Double-top/bottom
        if len(arr) >= 4:
            if arr[-1]==arr[-2]=="Big" and arr[-3]==arr[-4]=="Small":
                return "Small", 75
            if arr[-1]==arr[-2]=="Small" and arr[-3]==arr[-4]=="Big":
                return "Big", 75
        
        # Triple pattern (BBB after SSS)
        if len(arr) >= 6:
            if arr[-3:]==["Big","Big","Big"] and arr[-6:-3]==["Small","Small","Small"]:
                return "Small", 78
        
        return None, 0
    
    # =========================================================
    # 🎯 MULTI-TIMEFRAME FILTER
    # =========================================================
    def multi_timeframe(self, arr):
        """Short + Medium + Long trend တူမှ high confidence"""
        if len(arr) < 100: return None, 0
        
        s_big = arr[-10:].count("Big")
        short = "Big" if s_big>=7 else "Small" if s_big<=3 else None
        
        m_big = arr[-30:].count("Big")
        medium = "Big" if m_big>=20 else "Small" if m_big<=10 else None
        
        l_big = arr[-100:].count("Big")
        long_t = "Big" if l_big>=60 else "Small" if l_big<=40 else None
        
        if short and medium and long_t and short==medium==long_t:
            return short, 88  # Very high confidence
        return None, 0
    
    # =========================================================
    # 🎯 MAIN SIGNAL GENERATOR
    # =========================================================
    def generate_signal(self, arr):
        """Signal + Confidence (0-100)"""
        
        # 1) Pattern detection (highest priority)
        pat_sig, pat_conf = self.detect_patterns(arr)
        if pat_sig and pat_conf >= 80:
            return pat_sig, pat_conf, "Pattern"
        
        # 2) Multi-timeframe
        mtf_sig, mtf_conf = self.multi_timeframe(arr)
        if mtf_sig:
            return mtf_sig, mtf_conf, "Multi-TF"
        
        # 3) 50-Bot weighted voting
        valid = {}
        for i in range(self.num_bots):
            b_id = f"Bot_{i+1}"
            pred = self.run_bot(i, arr)
            if pred:
                valid[b_id] = pred
                self.bot_stats[b_id]["last_pred"] = pred
        
        if len(valid) < 20:
            return None, 0, f"Low bots ({len(valid)})"
        
        big_s = 0.0; small_s = 0.0
        for b_id, pred in valid.items():
            w = self.bot_stats[b_id]["weight"]
            if pred == "Big": big_s += w
            else: small_s += w
        
        total = big_s + small_s
        if total == 0: return None, 0, "No score"
        
        big_pct = big_s / total
        conf = max(big_pct, 1-big_pct) * 100
        
        # 4) Confidence threshold 75%
        if big_pct >= 0.75:
            return "Big", conf, f"Consensus Big"
        elif big_pct <= 0.25:
            return "Small", conf, f"Consensus Small"
        
        # 5) Extreme fallback
        if len(arr) >= 20:
            b20 = arr[-20:].count("Big")
            if b20 >= 17: return "Small", 85, "Extreme 17+"
            if b20 <= 3: return "Big", 85, "Extreme 3-"
        
        # Skip
        return None, conf, "Low confidence"
    
    # =========================================================
    # 🎯 ANALYZE ROUND
    # =========================================================
    def analyze_round(self, period, current_result):
        self.last_period = str(period)
        self.last_result = current_result
        if self.is_paused: return
        
        short = "..." + str(period)[-3:]
        
        # 1) Evaluate previous prediction
        if self.active_prediction:
            pred = self.active_prediction
            win = (current_result.lower() == pred.lower())
            
            # Confusion matrix
            if pred == "Big" and current_result == "Big": self.confusion_matrix["BB"] += 1
            elif pred == "Big" and current_result == "Small": self.confusion_matrix["BS"] += 1
            elif pred == "Small" and current_result == "Big": self.confusion_matrix["SB"] += 1
            else: self.confusion_matrix["SS"] += 1
            
            # Bankroll update
            self.bankroll.update(win, self.current_step)
            
            if win:
                self.total_wins += 1
                step_key = min(self.current_step, 3)
                self.win_by_step[step_key] += 1
                
                self.send_telegram(
                    f"✅ <b>WIN at Step {self.current_step+1}</b>\n"
                    f"📅 Period: {short} | Result: {current_result}\n"
                    f"📊 WR: {self.get_wr():.1f}% | Win3: {self.get_win3_rate():.1f}%\n"
                    f"💰 {self.bankroll.get_status()}"
                )
                self.current_step = 0
                self.consecutive_losses = 0
            else:
                self.total_losses += 1
                self.current_step += 1
                self.consecutive_losses += 1
                if self.consecutive_losses > self.max_consecutive_losses:
                    self.max_consecutive_losses = self.consecutive_losses
                
                warn = ""
                if self.current_step == 3: warn = "\n⚠️ <b>Step 4 (16x) — HIGH RISK</b>"
                if self.current_step == 5: warn = "\n🚨 <b>Step 6 (64x) — DANGER</b>"
                
                self.send_telegram(
                    f"❌ <b>LOSS</b> Period: {short} (Result: {current_result})\n"
                    f"Step {self.current_step+1} | {self.get_current_multiplier()}x{warn}\n"
                    f"💰 {self.bankroll.get_status()}"
                )
                
                # Bankroll protection alert
                if self.bankroll.should_stop():
                    self.send_telegram("🛑 <b>DAILY LOSS LIMIT REACHED!</b> Pausing...")
                    self.is_paused = True
            
            self.active_prediction = None
        
        # 2) Update bot performance
        if len(self.window) > 0:
            self.update_bot_performance(current_result)
        
        self.window.append(current_result)
        
        # 3) Warm-up
        if len(self.window) < 20:
            self.send_telegram(f"⏳ Warm-up {short} ({len(self.window)}/20)")
            return
        
        arr = list(self.window)
        
        # 4) Generate signal
        signal, conf, reason = self.generate_signal(arr)
        
        # 5) Auto-optimize every 50 rounds
        self.rounds_since_optimize += 1
        if self.rounds_since_optimize >= 50:
            self.auto_optimize()
            self.rounds_since_optimize = 0
        
        # 6) Skip if low confidence
        if signal is None:
            self.total_skips += 1
            self.send_telegram(
                f"⏸️ <b>SKIP</b> {short}\n"
                f"Reason: {reason} ({conf:.0f}%)"
            )
            return
        
        # 7) Emit signal
        self.active_prediction = signal
        self.total_signals += 1
        self.last_triggered_bot = reason
        self.confidence_history.append(conf)
        
        stars = "⭐" * int(conf / 20)
        msg = (
            f"🎯 <b>HIGH-CONFIDENCE SIGNAL</b> {stars}\n"
            f"📅 Period: {short}\n"
            f"📌 {reason} ({conf:.0f}%)\n"
            f"🎯 <b>{signal.upper()}</b>\n"
            f"💰 Step {self.current_step+1} ({self.get_current_multiplier()}x)\n"
            f"📊 WR: {self.get_wr():.1f}% | Win3: {self.get_win3_rate():.1f}%"
        )
        self.send_telegram(msg)
    
    # =========================================================
    # 🔧 AUTO-OPTIMIZER
    # =========================================================
    def update_bot_performance(self, actual):
        for b_id, stats in self.bot_stats.items():
            pred = stats.get("last_pred")
            if not pred: continue
            
            if pred.lower() == actual.lower():
                stats["wins"] += 1
            else:
                stats["losses"] += 1
            
            t = stats["wins"] + stats["losses"]
            stats["wr"] = stats["wins"]/t if t>0 else 0.0
            
            if t >= 5:
                if stats["wr"] >= 0.60: stats["weight"] = 2.0
                elif stats["wr"] >= 0.55: stats["weight"] = 1.5
                elif stats["wr"] >= 0.50: stats["weight"] = 1.0
                elif stats["wr"] >= 0.45: stats["weight"] = 0.7
                else: stats["weight"] = 0.3
    
    def auto_optimize(self):
        """Every 50 rounds — performance report"""
        top = sorted(self.bot_stats.items(), key=lambda x: x[1]["wr"], reverse=True)
        top5 = top[:5]
        bot5 = top[-5:]
        
        top_str = "\n".join([f"  {bid}: {s['wr']*100:.0f}%" for bid, s in top5])
        bot_str = "\n".join([f"  {bid}: {s['wr']*100:.0f}%" for bid, s in bot5])
        
        self.send_telegram(
            f"🔧 <b>AUTO-OPTIMIZE REPORT</b>\n\n"
            f"🏆 <b>Top 5 Bots:</b>\n{top_str}\n\n"
            f"📉 <b>Worst 5 Bots:</b>\n{bot_str}\n\n"
            f"📊 Overall WR: {self.get_wr():.1f}%\n"
            f"🎯 Win3: {self.get_win3_rate():.1f}%"
        )
    
    # =========================================================
    # 📊 METRICS
    # =========================================================
    def get_wr(self):
        t = self.total_wins + self.total_losses
        return (self.total_wins/t*100) if t>0 else 0.0
    
    def get_win3_rate(self):
        t = sum(self.win_by_step.values())
        if t == 0: return 0.0
        w3 = self.win_by_step[0] + self.win_by_step[1] + self.win_by_step[2]
        return (w3/t)*100
    
    def get_precision(self):
        cm = self.confusion_matrix
        tp = cm["BB"] + cm["SS"]
        fp = cm["BS"] + cm["SB"]
        return (tp/(tp+fp)*100) if (tp+fp)>0 else 0.0
    
    def get_recall(self):
        cm = self.confusion_matrix
        return self.get_precision()  # Same for binary
    
    def get_f1(self):
        p = self.get_precision(); r = self.get_recall()
        return (2*p*r/(p+r)) if (p+r)>0 else 0.0


# =========================================================
# 📱 TELEGRAM COMMANDS
# =========================================================
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
                        cm = agent.confusion_matrix
                        agent.send_telegram(
                            f"📊 <b>AI SNIPER v3.0 STATUS</b>\n\n"
                            f"⚙️ {'PAUSED 🛑' if agent.is_paused else 'RUNNING 🟢'}\n"
                            f"Signals: {agent.total_signals} | Skips: {agent.total_skips}\n"
                            f"✅ W: {agent.total_wins} | ❌ L: {agent.total_losses}\n"
                            f"📈 <b>WR: {agent.get_wr():.2f}%</b>\n"
                            f"🎯 <b>Win-in-3: {agent.get_win3_rate():.1f}%</b>\n"
                            f"📉 Max Loss Streak: {agent.max_consecutive_losses}\n\n"
                            f"💰 {agent.bankroll.get_status()}\n\n"
                            f"<b>Win by Step:</b>\n"
                            f"  S1: {agent.win_by_step[0]}\n"
                            f"  S2: {agent.win_by_step[1]}\n"
                            f"  S3: {agent.win_by_step[2]}\n"
                            f"  S4+: {agent.win_by_step[3]}\n\n"
                            f"<b>Confusion Matrix:</b>\n"
                            f"  BB:{cm['BB']} BS:{cm['BS']}\n"
                            f"  SB:{cm['SB']} SS:{cm['SS']}\n"
                            f"  Precision: {agent.get_precision():.1f}%\n"
                            f"  F1: {agent.get_f1():.1f}%"
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
                    elif txt == "/top":
                        top = sorted(agent.bot_stats.items(), key=lambda x: x[1]["wr"], reverse=True)[:10]
                        s = "\n".join([f"{bid}: {st['wr']*100:.0f}% ({st['wins']}W)" for bid, st in top])
                        agent.send_telegram(f"🏆 <b>Top 10 Bots</b>\n{s}")
                    elif txt == "/bank":
                        b = agent.bankroll
                        agent.send_telegram(
                            f"💰 <b>Bankroll Status</b>\n"
                            f"Balance: {b.balance:.2f}\n"
                            f"P/L: {b.balance - b.initial:+.2f}\n"
                            f"Peak: {b.session_peak:.2f}\n"
                            f"Max DD: {b.max_drawdown:.2f}\n"
                            f"Daily Loss: {b.daily_loss:.2f}"
                        )
                    elif txt == "/help":
                        agent.send_telegram(
                            "🤖 <b>Commands</b>\n"
                            "/status - Full stats\n"
                            "/top - Top 10 bots\n"
                            "/bank - Bankroll info\n"
                            "/pause - Pause bot\n"
                            "/resume - Resume bot\n"
                            "/reset - Reset martingale step"
                        )
        except Exception as e:
            print(f"TG Poll: {e}", flush=True)
        time.sleep(1)


# =========================================================
# 🚀 BACKTESTING MODE
# =========================================================
def run_backtest():
    """Historical data နဲ့ test (100 rounds)"""
    print("🔬 Starting Backtest...", flush=True)
    
    url = "https://6lotteryapi.com/api/webapi/GetNoaverageEmerdList"
    auth = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpYXQiOiIxNzg3OTgxNTA5IiwibmJmIjoiMTc4Nzk4MTUwOSIsImV4cCI6IjE3ODc5ODMzMDkiLCJodHRwOi8vc2NoZW1hcy5taWNyb3NvZnQuY29tL3dzLzIwMDgvMDYvaWRlbnRpdHkvY2xhaW1zL2V4cGlyYXRpb24iOiI4LzI5LzIwMjYgMTI6MzE2NDkgUE0iLCJodHRwOi8vc2NoZW1hcy5taWNyb3NvZnQuY29tL3dzLzIwMDgvMDYvaWRlbnRpdHkvY2xhaW1zL3JvbGUiOiJBY2Nlc3NfVG9rZW4iLCJVc2VySWQiOiIxMDEyMjEzIiwiVXNlck5hbWUiOiI5NTk3NDA5MzkzNzAiLCJVc2VyUGhvdG8iOiI5IiwiTmlja05hbWUiOiJUaetsR3lpIiwiQW1vdW50IjoiODcuMzAiLCJJbnRlZ3JhbCI6IjAiLCJMb2dpbk1hcmsiOiJINSIsImxvZ2luVGltZSI6IjcvMjkvMjAyNiAxMjowMTo0OSBQTSIsImxvZ2luSVBBZGRyZXNzIjoiNDUuNDEuMTA0LjI0MCIsImRiTnVtYmVyIjoiMCIsIklzdmFsaWRhdG9yIjoiMCIsIktleUNvZGUiOiIzMjMzMiIsImRva2VuVHlwZSI6IjJBY2Nlc3NfVG9rZW4iLCJob25lVHlwZSI6IjAiLCJVc2VyVHlwZSI6IjAiLCJVc2VyTmFtZ2UiOiIuIiwiaXNzIjoiand0SXNzdWVyIiwiYXVkIjoibG90dGVyeVRpY2tldCJ9.ZL0Y9gexUTCsKwWeZhCLAAw8AABEYJt0GnIzIviMG4g"
    
    headers = {
        "accept": "application/json, text/plain, */*",
        "authorization": f"Bearer {auth}",
        "content-type": "application/json;charset=UTF-8",
        "origin": "https://6win598.com",
        "referer": "https://6win598.com/",
        "user-agent": "Mozilla/5.0"
    }
    
    try:
        payload = {
            "pageSize": 100, "pageNo": 1, "typeId": 30, "language": 7,
            "random": "036263f367384d418be07465793c8da8",
            "signature": "55F4FD150F15F090B943374F3C9BE78B",
            "timestamp": int(time.time())
        }
        r = requests.post(url, headers=headers, json=payload, timeout=10)
        if r.status_code == 200:
            data = r.json()
            lst = data.get("data", {}).get("list", [])
            
            # Old → New order
            results = []
            for item in reversed(lst):
                num = int(item.get("number"))
                results.append("Big" if num >= 5 else "Small")
            
            print(f"📊 Got {len(results)} historical rounds", flush=True)
            
            # Test
            engine = AISniperEngineV3()
            wins = 0; losses = 0; skips = 0
            step = 0
            active = None
            win_by_step = {0:0,1:0,2:0,3:0}
            
            for i in range(20, len(results)):
                arr = results[:i]
                actual = results[i]
                
                # Evaluate
                if active:
                    if actual.lower() == active.lower():
                        wins += 1
                        k = min(step, 3)
                        win_by_step[k] += 1
                        step = 0
                    else:
                        losses += 1
                        step += 1
                    active = None
                
                # Generate
                sig, conf, reason = engine.generate_signal(arr)
                if sig:
                    active = sig
                else:
                    skips += 1
            
            total = wins + losses
            wr = (wins/total*100) if total else 0
            w3 = sum(win_by_step.values())
            w3r = ((win_by_step[0]+win_by_step[1]+win_by_step[2])/w3*100) if w3 else 0
            
            print(f"\n{'='*50}", flush=True)
            print(f"🔬 BACKTEST RESULT", flush=True)
            print(f"{'='*50}", flush=True)
            print(f"Total Rounds: {len(results)-20}", flush=True)
            print(f"Signals: {total} | Skips: {skips}", flush=True)
            print(f"Wins: {wins} | Losses: {losses}", flush=True)
            print(f"Win Rate: {wr:.2f}%", flush=True)
            print(f"Win-in-3-Steps: {w3r:.2f}%", flush=True)
            print(f"Win by Step: S1={win_by_step[0]} S2={win_by_step[1]} S3={win_by_step[2]} S4+={win_by_step[3]}", flush=True)
            print(f"{'='*50}\n", flush=True)
            
            # Send to Telegram
            if global_agent:
                global_agent.send_telegram(
                    f"🔬 <b>BACKTEST RESULT</b>\n\n"
                    f"Rounds: {len(results)-20}\n"
                    f"Signals: {total} | Skips: {skips}\n"
                    f"W: {wins} | L: {losses}\n"
                    f"<b>WR: {wr:.2f}%</b>\n"
                    f"<b>Win-in-3: {w3r:.2f}%</b>\n\n"
                    f"S1:{win_by_step[0]} S2:{win_by_step[1]}\n"
                    f"S3:{win_by_step[2]} S4+:{win_by_step[3]}"
                )
    except Exception as e:
        print(f"Backtest error: {e}", flush=True)


# =========================================================
# 🚀 MAIN LOOP
# =========================================================
def run_bot():
    print("🚀 AI Sniper v3.0 starting...", flush=True)
    agent = AISniperEngineV3()
    threading.Thread(target=poll_telegram, args=(agent,), daemon=True).start()
    
    # Backtest once at start (background)
    threading.Thread(target=run_backtest, daemon=True).start()
    
    last_period = ""
    url = "https://6lotteryapi.com/api/webapi/GetNoaverageEmerdList"
    auth = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpYXQiOiIxNzg3OTgxNTA5IiwibmJmIjoiMTc4Nzk4MTUwOSIsImV4cCI6IjE3ODc5ODMzMDkiLCJodHRwOi8vc2NoZW1hcy5taWNyb3NvZnQuY29tL3dzLzIwMDgvMDYvaWRlbnRpdHkvY2xhaW1zL2V4cGlyYXRpb24iOiI4LzI5LzIwMjYgMTI6MzE2NDkgUE0iLCJodHRwOi8vc2NoZW1hcy5taWNyb3NvZnQuY29tL3dzLzIwMDgvMDYvaWRlbnRpdHkvY2xhaW1zL3JvbGUiOiJBY2Nlc3NfVG9rZW4iLCJVc2VySWQiOiIxMDEyMjEzIiwiVXNlck5hbWUiOiI5NTk3NDA5MzkzNzAiLCJVc2VyUGhvdG8iOiI5IiwiTmlja05hbWUiOiJUaetsR3lpIiwiQW1vdW50IjoiODcuMzAiLCJJbnRlZ3JhbCI6IjAiLCJMb2dpbk1hcmsiOiJINSIsImxvZ2luVGltZSI6IjcvMjkvMjAyNiAxMjowMTo0OSBQTSIsImxvZ2luSVBBZGRyZXNzIjoiNDUuNDEuMTA0LjI0MCIsImRiTnVtYmVyIjoiMCIsIklzdmFsaWRhdG9yIjoiMCIsIktleUNvZGUiOiIzMjMzMiIsImRva2VuVHlwZSI6IjJBY2Nlc3NfVG9rZW4iLCJob25lVHlwZSI6IjAiLCJVc2VyVHlwZSI6IjAiLCJVc2VyTmFtZ2UiOiIuIiwiaXNzIjoiand0SXNzdWVyIiwiYXVkIjoibG90dGVyeVRpY2tldCJ9.ZL0Y9gexUTCsKwWeZhCLAAw8AABEYJt0GnIzIviMG4g"
    
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
            r = requests.post(url, headers=headers, json=payload, timeout=5)
            if r.status_code == 200:
                d = r.json()
                lst = d.get("data", {}).get("list", [])
                if lst:
                    latest = lst[0]
                    raw = str(latest.get("issueNumber"))
                    period = str(int(raw) + 2)
                    num = int(latest.get("number"))
                    result = "Big" if num >= 5 else "Small"
                    
                    if period != last_period:
                        last_period = period
                        print(f"Sync {period} → {result}", flush=True)
                        agent.analyze_round(period, result)
        except Exception as e:
            print(f"API Err: {e}", flush=True)
        time.sleep(1.5)


threading.Thread(target=run_bot, daemon=True).start()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
