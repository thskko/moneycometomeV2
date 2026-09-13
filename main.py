import requests
import time
import os
import threading
from collections import deque, Counter
from datetime import datetime
from flask import Flask, jsonify

TELEGRAM_TOKEN = "8913070806:AAF3rP0zKJtofE-5KVesqcdoHzn7Go0avho"
CHAT_ID = "-1004402480797"

app = Flask(__name__)
global_agent = None

HOT_STREAK = 7          # Base threshold


# ==========================================
# 📊 DASHBOARD
# ==========================================
@app.route('/')
def home():
    global global_agent
    if not global_agent:
        return "<h3>🔥 Max Streak Lock v2.6 starting...</h3>"
    
    a = global_agent
    total = a.total_wins + a.total_losses
    wr = (a.total_wins / total * 100) if total > 0 else 0.0
    
    bot_rows = ""
    sorted_bots = sorted(a.bot_stats.items(), key=lambda x: x[1]["win_streak"], reverse=True)
    for b_id, s in sorted_bots[:20]:
        streak_icon = "🔥" if s["win_streak"] >= HOT_STREAK else ("⚡" if s["win_streak"] >= 4 else "")
        lock_icon = "🔒" if b_id == a.locked_bot else ""
        bot_rows += f"<tr><td>{b_id} {lock_icon}</td><td>{s['wins']}</td><td>{s['losses']}</td><td>{s['wr']*100:.1f}%</td><td><b>{s['win_streak']}</b> {streak_icon}</td></tr>"
    
    lock_status = f"🔒 {a.locked_bot} ({a.locked_streak}W)" if a.locked_bot else "None"
    
    return f"""
    <html><head><title>Max Streak Lock v2.6</title>
    <meta http-equiv="refresh" content="15">
    <style>
    body{{background:#0a0e27;color:#0ff;font-family:monospace;padding:20px}}
    h1,h2{{color:#0ff;text-shadow:0 0 10px #0ff}}
    .box{{background:#1a1f3a;border:1px solid #0ff;padding:15px;margin:10px 0;border-radius:8px}}
    .big{{font-size:32px;color:#0f0;font-weight:bold}}
    .lock{{font-size:24px;color:#f44;font-weight:bold}}
    table{{width:100%;border-collapse:collapse}}
    th,td{{padding:6px;border:1px solid #0ff;text-align:left;font-size:12px}}
    th{{background:#0ff;color:#000}}
    </style></head><body>
    <h1>🔒 MAX STREAK LOCK v2.6</h1>
    <p>Base Threshold: <b>{HOT_STREAK}+</b> Win Streak</p>
    
    <div class="box">
      <h2>📊 Performance</h2>
      <p>Status: <b>{'PAUSED 🛑' if a.is_paused else 'RUNNING 🟢'}</b></p>
      <p>Signals: {a.total_signals} | Skips: {a.total_skips}</p>
      <p>Wins: {a.total_wins} | Losses: {a.total_losses}</p>
      <p>Win Rate: <span class="big">{wr:.2f}%</span></p>
      <p>Current Step: {a.current_step + 1} ({a.get_multiplier()}x)</p>
    </div>
    
    <div class="box">
      <h2>🔒 Current Lock</h2>
      <p class="lock">{lock_status}</p>
    </div>
    
    <div class="box">
      <h2>🏆 Bot Leaderboard (by Streak)</h2>
      <table>
        <tr><th>Bot</th><th>W</th><th>L</th><th>WR</th><th>Streak</th></tr>
        {bot_rows}
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
# 🎯 MAX STREAK LOCK ENGINE v2.6
# ==========================================
class MaxStreakLockEngine:
    def __init__(self):
        global global_agent
        global_agent = self
        
        self.number_window = deque(maxlen=300)
        
        self.current_step = 0
        self.active_prediction = None
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
        
        # 🆕 Max Streak Lock
        self.locked_bot = None
        self.locked_streak = 0
        
        self.num_bots = 50
        self.bot_stats = {}
        for i in range(1, 51):
            b_id = f"Bot_{i}"
            self.bot_stats[b_id] = {
                "wins": 0,
                "losses": 0,
                "wr": 0.0,
                "win_streak": 0,
                "loss_streak": 0,
                "max_win_streak": 0,
                "last_pred": None,
            }
    
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
    
    # =========================================================
    # 50 BOT STRATEGIES
    # =========================================================
    def run_bot(self, bot_idx, arr):
        n = len(arr)
        if n < 15: return None
        
        idx = (bot_idx - 1) % 50
        
        # Trend (0-9)
        if idx == 0: return arr[-1]
        elif idx == 1: return "Small" if arr[-1]=="Big" else "Big"
        elif idx == 2: return "Big" if arr[-3:].count("Big")>=2 else "Small"
        elif idx == 3: return "Small" if arr[-3:].count("Big")>=2 else "Big"
        elif idx == 4: return "Big" if arr[-5:].count("Big")>=3 else "Small"
        elif idx == 5: return "Small" if arr[-5:].count("Big")>=3 else "Big"
        elif idx == 6:
            s=1
            for x in reversed(arr[:-1]):
                if x==arr[-1]: s+=1
                else: break
            return arr[-1] if s>=2 else ("Small" if arr[-1]=="Big" else "Big")
        elif idx == 7:
            s=1
            for x in reversed(arr[:-1]):
                if x==arr[-1]: s+=1
                else: break
            return ("Small" if arr[-1]=="Big" else "Big") if s>=2 else arr[-1]
        elif idx == 8:
            b=sum(1 for x in arr[-7:] if x=="Big")
            return "Big" if b>=4 else "Small"
        elif idx == 9:
            b=sum(1 for x in arr[-10:] if x=="Big")
            return "Big" if b>=6 else "Small"
        
        # Markov (10-19)
        elif idx == 10:
            last=arr[-1]
            nxt=[arr[i+1] for i in range(n-1) if arr[i]==last]
            if len(nxt)>=3: return Counter(nxt).most_common(1)[0][0]
            return None
        elif idx == 11:
            if n<20: return None
            p=tuple(arr[-2:])
            nxt=[arr[i+2] for i in range(n-2) if tuple(arr[i:i+2])==p]
            if len(nxt)>=3: return Counter(nxt).most_common(1)[0][0]
            return None
        elif idx == 12:
            if n<25: return None
            p=tuple(arr[-3:])
            nxt=[arr[i+3] for i in range(n-3) if tuple(arr[i:i+3])==p]
            if len(nxt)>=2: return Counter(nxt).most_common(1)[0][0]
            return None
        elif idx == 13:
            if n<30: return None
            p=tuple(arr[-4:])
            nxt=[arr[i+4] for i in range(n-4) if tuple(arr[i:i+4])==p]
            if len(nxt)>=2: return Counter(nxt).most_common(1)[0][0]
            return None
        elif idx == 14:
            alt=sum(1 for i in range(-6,-1) if arr[i]!=arr[i+1])
            if alt>=5: return "Small" if arr[-1]=="Big" else "Big"
            return None
        elif idx == 15:
            if arr[-2:]==["Big","Big"]:
                s=[arr[i+2] for i in range(n-2) if arr[i:i+2]==["Big","Big"]]
                if s: return Counter(s).most_common(1)[0][0]
            return None
        elif idx == 16:
            if arr[-2:]==["Small","Small"]:
                b=[arr[i+2] for i in range(n-2) if arr[i:i+2]==["Small","Small"]]
                if b: return Counter(b).most_common(1)[0][0]
            return None
        elif idx == 17:
            last=arr[-1]; gap=1
            for x in reversed(arr[:-1]):
                if x==last: gap+=1
                else: break
            if gap>=4: return "Small" if last=="Big" else "Big"
            return None
        elif idx == 18:
            b=arr[-20:].count("Big")
            if b>=13: return "Small"
            if b<=7: return "Big"
            return None
        elif idx == 19:
            b=arr[-30:].count("Big") if n>=30 else arr.count("Big")
            if b>=18: return "Small"
            if b<=12: return "Big"
            return None
        
        # Statistical (20-29)
        elif idx == 20:
            b=arr[-10:].count("Big")+1
            s=arr[-10:].count("Small")+1
            p=b/(b+s)
            if p>=0.65: return "Big"
            if p<=0.35: return "Small"
            return None
        elif idx == 21:
            if n<20: return None
            b=arr[-20:].count("Big")+1
            s=arr[-20:].count("Small")+1
            p=b/(b+s)
            if p>=0.62: return "Big"
            if p<=0.38: return "Small"
            return None
        elif idx == 22:
            b=arr[-15:].count("Big") if n>=15 else arr.count("Big")
            if b>=11: return "Small"
            if b<=4: return "Big"
            return None
        elif idx == 23:
            bb=sum(1 for i in range(-15,0) if arr[i]=="Big" and arr[i+1]=="Big")
            if bb>=6: return "Small"
            return None
        elif idx == 24:
            ss=sum(1 for i in range(-15,0) if arr[i]=="Small" and arr[i+1]=="Small")
            if ss>=6: return "Big"
            return None
        elif idx == 25:
            s=1
            for x in reversed(arr[:-1]):
                if x==arr[-1]: s+=1
                else: break
            if s==3: return "Small" if arr[-1]=="Big" else "Big"
            return None
        elif idx == 26:
            s=1
            for x in reversed(arr[:-1]):
                if x==arr[-1]: s+=1
                else: break
            if s==4: return "Small" if arr[-1]=="Big" else "Big"
            return None
        elif idx == 27:
            if n<15: return None
            f5=arr[-10:-5].count("Big"); l5=arr[-5:].count("Big")
            if f5<=1 and l5>=3: return "Big"
            if f5>=3 and l5<=1: return "Small"
            return None
        elif idx == 28:
            if n<20: return None
            b10=arr[-10:].count("Big"); b20=arr[-20:].count("Big")
            if b10>b20*0.6: return "Big"
            if b10<b20*0.4: return "Small"
            return None
        elif idx == 29:
            b=arr[-25:].count("Big") if n>=25 else arr.count("Big")
            tn=min(25,n)
            if b>=tn-3: return "Small"
            if b<=3: return "Big"
            return None
        
        # Pattern (30-39)
        elif idx == 30:
            if arr[-3:]==["Big","Small","Small"]: return "Big"
            return None
        elif idx == 31:
            if arr[-3:]==["Small","Big","Big"]: return "Small"
            return None
        elif idx == 32:
            if arr[-3:]==["Big","Small","Big"]: return "Small"
            return None
        elif idx == 33:
            if arr[-3:]==["Small","Big","Small"]: return "Big"
            return None
        elif idx == 34:
            if arr[-4:]==["Big","Big","Small","Big"]: return "Small"
            return None
        elif idx == 35:
            if arr[-4:]==["Small","Small","Big","Small"]: return "Big"
            return None
        elif idx == 36:
            l5=arr[-5:]
            if l5[:2]==l5[-2:][::-1]:
                return "Small" if l5[-1]=="Big" else "Big"
            return None
        elif idx == 37:
            if n<6: return None
            bl=[arr[-6:-4],arr[-4:-2],arr[-2:]]
            if bl[0]==bl[2] and bl[0]!=bl[1]:
                return bl[0][0]
            return None
        elif idx == 38:
            sc=0
            for i,x in enumerate(arr[-10:]):
                w=1+(i/10)
                sc+=w if x=="Big" else -w
            if sc>2: return "Big"
            if sc<-2: return "Small"
            return None
        elif idx == 39:
            if n<20: return None
            l5=arr[-5:].count("Big"); l20=arr[-20:].count("Big")
            if l5>=4 and l20<=8: return "Big"
            if l5<=1 and l20>=12: return "Small"
            return None
        
        # Adaptive (40-49)
        elif idx == 40: return "Big" if arr.count("Big")>=n/2 else "Small"
        elif idx == 41: return "Small" if arr.count("Big")>=n/2 else "Big"
        elif idx == 42: return arr[-1]
        elif idx == 43: return "Small" if arr[-1]=="Big" else "Big"
        elif idx == 44:
            b=arr[:10].count("Big") if n>=10 else arr.count("Big")
            return "Big" if b>=5 else "Small"
        elif idx == 45: return arr[-2] if n>=2 else "Big"
        elif idx == 46: return "Small" if arr[-2]=="Big" else "Big" if n>=2 else "Small"
        elif idx == 47: return arr[-3] if n>=3 else "Big"
        elif idx == 48: return "Small" if arr[-4]=="Big" else "Big" if n>=4 else "Small"
        else:
            bigs=sum(1 for s in self.bot_stats.values() if s.get("last_pred")=="Big")
            return "Small" if bigs>=25 else "Big"
    
    # =========================================================
    # UPDATE BOT STATS
    # =========================================================
    def update_bot_stats(self, actual):
        for b_id, stats in self.bot_stats.items():
            pred = stats.get("last_pred")
            if not pred: continue
            
            if pred == actual:
                stats["wins"] += 1
                stats["win_streak"] += 1
                stats["loss_streak"] = 0
                if stats["win_streak"] > stats["max_win_streak"]:
                    stats["max_win_streak"] = stats["win_streak"]
            else:
                stats["losses"] += 1
                stats["loss_streak"] += 1
                stats["win_streak"] = 0
            
            t = stats["wins"] + stats["losses"]
            stats["wr"] = stats["wins"] / t if t > 0 else 0.0
    
    # =========================================================
    # 🎯 SIGNAL GENERATOR — Max Streak Lock
    # =========================================================
    def generate_signal(self, arr):
        """
        1. Lock ရှိရင် — Lock ဖြစ်တဲ့ Bot ရဲ့ Signal → Reverse
        2. Lock မရှိရင် — 7+ bots ရှာ
        3. Max Streak Bot 1 ကောင်ပဲ ရှိရင် → Lock
        4. Tie ဖြစ်ရင် → စောင့်
        5. 7+ မရှိရင် SKIP
        """
        
        # 1) Bot 50 run
        for i in range(1, 51):
            b_id = f"Bot_{i}"
            pred = self.run_bot(i, arr)
            if pred:
                self.bot_stats[b_id]["last_pred"] = pred
        
        # 2) Lock ရှိလား?
        if self.locked_bot:
            locked_stats = self.bot_stats.get(self.locked_bot)
            if locked_stats:
                locked_pred = locked_stats.get("last_pred")
                if locked_pred:
                    reversed_sig = "Small" if locked_pred == "Big" else "Big"
                    reason = f"🔒 {self.locked_bot} ({locked_stats['win_streak']}W) locked"
                    return reversed_sig, 100, reason, 1
                else:
                    self.locked_bot = None
        
        # 3) 7+ Bots ရှာ
        hot_bots = []
        for b_id, stats in self.bot_stats.items():
            if stats["win_streak"] >= HOT_STREAK:
                last_pred = stats.get("last_pred")
                if last_pred:
                    reversed_sig = "Small" if last_pred == "Big" else "Big"
                    hot_bots.append({
                        "bot": b_id,
                        "streak": stats["win_streak"],
                        "original": last_pred,
                        "reversed": reversed_sig,
                    })
        
        # 4) 7+ မရှိရင် SKIP
        if not hot_bots:
            return None, 0, f"No hot bot (need {HOT_STREAK}+ streak)", 0
        
        # 5) Max Streak ရှာ
        max_streak = max(h["streak"] for h in hot_bots)
        top_bots = [h for h in hot_bots if h["streak"] == max_streak]
        
        # 6) Tie ဖြစ်ရင် — စောင့်
        if len(top_bots) > 1:
            bots_str = ", ".join([f"{h['bot']}({h['streak']}W)" for h in top_bots[:5]])
            reason = f"⏳ Tie at {max_streak}W: {bots_str} — waiting"
            return None, 0, reason, len(top_bots)
        
        # 7) Max Streak Bot 1 ကောင်ပဲ → Lock
        top_bot = top_bots[0]
        self.locked_bot = top_bot["bot"]
        self.locked_streak = top_bot["streak"]
        
        reason = f"🔒 LOCK: {top_bot['bot']} ({top_bot['streak']}W) → Reverse"
        return top_bot["reversed"], 100, reason, 1
    
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
            
            if win:
                self.total_wins += 1
                step_key = min(self.current_step, 3)
                self.win_by_step[step_key] += 1
                self.current_step = 0
                
                # 🆕 Win ဖြစ်ရင် Lock ဖျက်
                unlock_msg = ""
                if self.locked_bot:
                    unlock_msg = f"\n🔓 UNLOCK: {self.locked_bot}"
                    self.locked_bot = None
                    self.locked_streak = 0
                
                self.send_telegram(
                    f"✅ <b>WIN</b>{unlock_msg}\n"
                    f"🔢 Number: {number} ({current_result})\n"
                    f"📊 WR: {self.get_wr():.1f}% | Win3: {self.get_win3_rate():.1f}%"
                )
            else:
                self.total_losses += 1
                self.current_step += 1
                
                # 🆕 Loss — Lock ဆက်ထား
                if self.current_step >= 3:
                    self.send_telegram(
                        f"⚠️ <b>Step {self.current_step+1} ({self.get_multiplier()}x)</b>\n"
                        f"🔒 Locked: {self.locked_bot}"
                    )
            
            self.active_prediction = None
        
        # 2) Update Bot Stats (previous round)
        if len(self.number_window) > 0:
            last_bs = "Big" if self.number_window[-1] >= 5 else "Small"
            self.update_bot_stats(last_bs)
        
        self.number_window.append(number)
        
        # 3) Warm-up
        if len(self.number_window) < 20:
            self.send_telegram(f"⏳ Warm-up {short} ({len(self.number_window)}/20)")
            return
        
        # 4) Signal
        arr = ["Big" if n >= 5 else "Small" for n in self.number_window]
        signal, conf, reason, hot_count = self.generate_signal(arr)
        
        self.last_signal = signal if signal else "SKIP"
        self.last_reason = reason
        
        # 5) Skip
        if signal is None:
            self.total_skips += 1
            self.send_telegram(f"⏸️ <b>SKIP</b> {short}\nReason: {reason}")
            return
        
        # 6) Signal
        self.active_prediction = signal
        self.total_signals += 1
        
        stars = "⭐" * min(int(conf / 20), 5)
        self.send_telegram(
            f"🔥 <b>MAX STREAK SIGNAL</b> {stars}\n"
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
                        lock_info = f"🔒 Locked: {agent.locked_bot} ({agent.locked_streak}W)" if agent.locked_bot else "🔓 No Lock"
                        agent.send_telegram(
                            f"📊 <b>MAX STREAK LOCK STATUS</b>\n\n"
                            f"⚙️ {'PAUSED 🛑' if agent.is_paused else 'RUNNING 🟢'}\n"
                            f"Signals: {agent.total_signals} | Skips: {agent.total_skips}\n"
                            f"✅ W: {agent.total_wins} | ❌ L: {agent.total_losses}\n"
                            f"📈 WR: {agent.get_wr():.2f}%\n"
                            f"🎯 Win3: {agent.get_win3_rate():.1f}%\n\n"
                            f"{lock_info}\n"
                            f"🎚️ Base: {HOT_STREAK}+ Win Streak"
                        )
                    elif txt == "/hot":
                        hot = [(b, s) for b, s in agent.bot_stats.items() if s["win_streak"] >= HOT_STREAK]
                        if hot:
                            s = "\n".join([f"🔥 {b}: {st['win_streak']} wins (pred: {st['last_pred']})" for b, st in hot])
                        else:
                            top = sorted(agent.bot_stats.items(), key=lambda x: x[1]["win_streak"], reverse=True)[:5]
                            s = f"No hot bots yet. Top 5:\n"
                            s += "\n".join([f"{b}: {st['win_streak']}/{HOT_STREAK}" for b, st in top])
                        agent.send_telegram(f"🔥 <b>Hot Bots ({HOT_STREAK}+)</b>\n{s}")
                    elif txt == "/top":
                        top = sorted(agent.bot_stats.items(), key=lambda x: x[1]["win_streak"], reverse=True)[:10]
                        s = "\n".join([f"{b}: streak {st['win_streak']} ({st['wins']}W)" for b, st in top])
                        agent.send_telegram(f"🏆 <b>Top 10 (by streak)</b>\n{s}")
                    elif txt == "/lock":
                        if agent.locked_bot:
                            stats = agent.bot_stats[agent.locked_bot]
                            s = f"🔒 Locked: {agent.locked_bot}\nStreak: {stats['win_streak']}\nPred: {stats['last_pred']}"
                        else:
                            s = "🔓 No bot locked"
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
                    elif txt == "/unlock":
                        if agent.locked_bot:
                            old = agent.locked_bot
                            agent.locked_bot = None
                            agent.locked_streak = 0
                            agent.send_telegram(f"🔓 Manually unlocked: {old}")
                        else:
                            agent.send_telegram("🔓 No lock to unlock")
                    elif txt == "/help":
                        agent.send_telegram(
                            "🤖 <b>Commands</b>\n"
                            "/status - Stats\n"
                            f"/hot - Hot bots ({HOT_STREAK}+)\n"
                            "/top - Top 10\n"
                            "/lock - Current lock info\n"
                            "/unlock - Manual unlock\n"
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
    print(f"🔒 Max Streak Lock v2.6 starting (Base: {HOT_STREAK}+)...", flush=True)
    agent = MaxStreakLockEngine()
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
                        print(f"🔒 Sync {period} → {number}", flush=True)
                        agent.analyze_round(period, number)
        except Exception as e:
            print(f"API Err: {e}", flush=True)
        time.sleep(1.5)


threading.Thread(target=run_bot, daemon=True).start()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
