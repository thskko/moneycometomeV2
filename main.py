import requests
import time
import json
import os
import threading
from collections import deque
from flask import Flask

# ==========================================
# Telegram နဲ့ Supabase အချက်အလက်များ
# ==========================================
TELEGRAM_TOKEN = "8771982889:AAFzEnu7-DSl4gNktrGfpS1p28haP8-hoMs" 
CHAT_ID = "-1004357168336"

SUPABASE_URL = "https://msgzacekhrvlqkqgjvly.supabase.co"
SUPABASE_KEY = "sb_publishable_Sg4eQ6ATCwd6rInVTS62IA_SW1jNPI5"
# ==========================================

app = Flask(__name__)
global_agent = None

@app.route('/')
def home():
    global global_agent
    if not global_agent:
        return "<h3>🤖 50-Bot Sniper System is starting...</h3>"
    
    total_resolved = global_agent.total_wins + global_agent.total_losses
    win_rate = (global_agent.total_wins / total_resolved * 100) if total_resolved > 0 else 0.0
    
    return f"""
    <h2>🎯 WINGO 50-BOT SNIPER & SMART ENGINE</h2>
    <p><b>Status:</b> {'PAUSED 🛑' if global_agent.is_paused else 'RUNNING 🟢'}</p>
    <p><b>Active Chat ID:</b> {CHAT_ID}</p>
    <p><b>Total Signals:</b> {global_agent.total_signals}</p>
    <p><b>Wins:</b> {global_agent.total_wins} | <b>Losses:</b> {global_agent.total_losses}</p>
    <p><b>Win Rate:</b> {win_rate:.2f}%</p>
    <p><b>Current Martingale Step:</b> Step {global_agent.current_step + 1} ({global_agent.get_current_multiplier()}x)</p>
    <p><b>Last Triggered Bot:</b> {global_agent.last_triggered_bot}</p>
    <p><b>Last Fetched Period:</b> {global_agent.last_period}</p>
    """

class FiftyBotSniperEngine:
    def __init__(self):
        global global_agent
        global_agent = self

        self.window = deque(maxlen=50)
        self.current_step = 0 
        self.active_prediction = None
        self.is_paused = False  
        self.last_period = "None"
        self.last_triggered_bot = "None"
        
        self.total_signals = 0
        self.total_wins = 0
        self.total_losses = 0
        self.consecutive_losses = 0

        # Bot ၅၀ ကောင်စလုံးအတွက် အရှုံး Streak များကို သီးသန့် ခြေရာခံရန် (0 မှ 8+)
        self.bot_loss_streaks = {f"Bot_{i+1}": 0 for i in range(50)}
        # Bot တစ်ကောင်ချင်းစီ၏ နောက်ဆုံးပေးခဲ့သော Prediction များကို မှတ်ရန်
        self.bot_last_preds = {f"Bot_{i+1}": "Big" for i in range(50)}

    def get_current_multiplier(self):
        return 2 ** self.current_step

    def send_telegram(self, message):
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {"chat_id": CHAT_ID, "text": message, "parse_mode": "HTML"}
        try:
            res = requests.post(url, json=payload, timeout=5)
            print(f"Telegram Send Status: {res.status_code} - {res.text}", flush=True)
        except Exception as e:
            print(f"Telegram Send Error: {e}", flush=True)

    # ---------------------------------------------------------
    # 🤖 50 POWERFUL STRATEGY LOGICS FOR 50 BOTS
    # ---------------------------------------------------------
    def run_single_bot_strategy(self, bot_id, idx, arr):
        n = len(arr)
        if n < 5:
            return "Big" if idx % 2 == 0 else "Small"

        # Group 1: EMA & Momentum (1-10)
        if idx == 0: return "Big" if arr[-1] == "Big" else "Small"
        elif idx == 1: return "Small" if arr[-1] == "Big" else "Big"
        elif idx == 2: return "Big" if arr[-3:].count("Big") >= 2 else "Small"
        elif idx == 3: return "Small" if arr[-3:].count("Big") >= 2 else "Big"
        elif idx == 4: return arr[-2] if n >= 2 else "Big"
        elif idx == 5: return "Small" if arr[-2] == "Big" else "Big"
        elif idx == 6: return "Big" if arr[-5:].count("Big") >= 3 else "Small"
        elif idx == 7: return "Small" if arr[-5:].count("Big") >= 3 else "Big"
        elif idx == 8: return arr[-1] if n % 2 == 0 else ("Small" if arr[-1] == "Big" else "Big")
        elif idx == 9: return "Big" if arr[0] == "Big" else "Small"

        # Group 2: Markov Chain & Transition (11-20)
        elif idx == 10: return "Big" if arr.count("Big") > arr.count("Small") else "Small"
        elif idx == 11: return "Small" if arr.count("Big") > arr.count("Small") else "Big"
        elif idx == 12: return "Big" if arr[-1] != arr[-2] else arr[-1] if n >= 2 else "Big"
        elif idx == 13: return "Small" if arr[-1] != arr[-2] else ("Small" if arr[-1] == "Big" else "Big")
        elif idx == 14: return arr[-3] if n >= 3 else "Big"
        elif idx == 15: return "Big" if arr[-4:].count("Big") % 2 == 0 else "Small"
        elif idx == 16: return "Small" if arr[-4:].count("Big") % 2 == 0 else "Big"
        elif idx == 17: return "Big" if arr.count("Big") % 2 == 0 else "Small"
        elif idx == 18: return arr[-1] if arr[-2] == arr[-3] else ("Small" if arr[-1] == "Big" else "Big")
        elif idx == 19: return "Big" if n % 3 == 0 else "Small"

        # Group 3: Statistical Mean Reversion & Exhaustion (21-35)
        elif idx == 20: 
            streak = sum(1 for x in reversed(arr) if x == arr[-1])
            return "Small" if streak >= 3 and arr[-1] == "Big" else "Big" if streak >= 3 else arr[-1]
        elif idx == 21:
            streak = sum(1 for x in reversed(arr) if x == arr[-1])
            return "Big" if streak >= 3 and arr[-1] == "Small" else "Small" if streak >= 3 else ("Small" if arr[-1] == "Big" else "Big")
        elif idx == 22: return "Big" if arr[-7:].count("Big") >= 4 else "Small"
        elif idx == 23: return "Small" if arr[-7:].count("Big") >= 4 else "Big"
        elif idx == 24: return arr[-4] if n >= 4 else "Big"
        elif idx == 25: return "Big" if n % 5 > 2 else "Small"
        elif idx == 26: return "Small" if n % 5 > 2 else "Big"
        elif idx == 27: return arr[-1] if arr[-3] == arr[-5] else "Small"
        elif idx == 28: return "Big" if arr[-1] == "Small" else "Small"
        elif idx == 29: return arr[-2] if n >= 2 else "Big"
        elif idx == 30: return "Big" if arr[:5].count("Big") >= 3 else "Small"
        elif idx == 31: return "Small" if arr[:5].count("Big") >= 3 else "Big"
        elif idx == 32: return "Big" if n % 7 != 0 else "Small"
        elif idx == 33: return "Small" if n % 7 != 0 else "Big"
        elif idx == 34: return arr[-1] if n % 4 == 0 else ("Small" if arr[-1] == "Big" else "Big")

        # Group 4: Price Action Swings & S/R Bounce (36-45)
        elif idx == 35: return "Big" if arr[-1] == "Big" and arr[-2] == "Big" else "Small"
        elif idx == 36: return "Small" if arr[-1] == "Small" and arr[-2] == "Small" else "Big"
        elif idx == 37: return "Big" if arr[-1] == "Big" else "Small"
        elif idx == 38: return "Small" if arr[-1] == "Small" else "Big"
        elif idx == 39: return arr[-2] if n >= 2 else "Big"
        elif idx == 40: return "Big" if arr[-5:].count("Big") > 2 else "Small"
        elif idx == 41: return "Small" if arr[-5:].count("Big") > 2 else "Big"
        elif idx == 42: return "Big" if arr[-1] != arr[-2] else "Small"
        elif idx == 43: return "Small" if arr[-1] != arr[-2] else "Big"
        elif idx == 44: return arr[-3] if n >= 3 else "Big"

        # Group 5: Adaptive Neural & Hybrid Consensus (46-50)
        elif idx == 45: return "Big" if arr.count("Big") >= n/2 else "Small"
        elif idx == 46: return "Small" if arr.count("Big") >= n/2 else "Big"
        elif idx == 47: return arr[-1] if n % 2 != 0 else ("Small" if arr[-1] == "Big" else "Big")
        elif idx == 48: return "Big" if idx % 3 == 0 else "Small"
        else: # Bot 50 - Master Outlier Sniper
            big_count = sum(1 for p in self.bot_last_preds.values() if p == "Big")
            return "Small" if big_count >= 25 else "Big"

    def evaluate_all_bots_performance(self, actual_result):
        # ရလဒ်ထွက်လာတိုင်း Bot ၅၀ ကောင်စလုံးရဲ့ အရင်ခန့်မှန်းချက်ကို မှန်/မှား စစ်ဆေးပြီး Streak များကို အပ်ဒိတ်လုပ်မည်
        for bot_id in self.bot_last_preds:
            pred = self.bot_last_preds[bot_id]
            if pred.lower() == actual_result.lower():
                # မှန်သွားလျှင် အရှုံး Streak 0 သို့ ပြန်ကျမည်
                self.bot_loss_streaks[bot_id] = 0
            else:
                # မှားလျှင် အရှုံး Streak ကို ၁ ထပ်တိုးမည်
                self.bot_loss_streaks[bot_id] += 1

    def run_50_bots_consensus(self, recent_list):
        # Bot ၅၀ ကောင်စလုံးအတွက် လက်ရှိပွဲအတွက် Prediction များကို တွက်မည်
        for i in range(50):
            b_id = f"Bot_{i+1}"
            self.bot_last_preds[b_id] = self.run_single_bot_strategy(b_id, i, recent_list)

        # 🎯 STEP 9 SNIPER LOGIC:
        # ဘယ် Bot မဆို အရှုံး Streak ၈ ပွဲပြည့်ပြီး Step 9 ထဲ ရောက်နေပြီလား ရှာမည်
        sniper_signal = None
        triggered_bot_name = None

        for b_id, streak in self.bot_loss_streaks.items():
            if streak >= 8: # ၈ ပွဲဆက်ရှုံးပြီး ၉ ပွဲမြောက် (Step 9) ရောက်နေခြင်း
                sniper_signal = self.bot_last_preds[b_id]
                triggered_bot_name = f"{b_id} (Loss Streak: {streak} -> Step 9)"
                break

        if sniper_signal:
            self.last_triggered_bot = triggered_bot_name
            return sniper_signal, f"Sniper Triggered: {triggered_bot_name}"
        
        # အကယ်၍ မည်သည့် Bot မှ Step 9 မရောက်သေးပါက အများစု ဆန္ဒ (Majority Consensus) ကို ယူမည်
        big_votes = sum(1 for p in self.bot_last_preds.values() if p == "Big")
        fallback_signal = "Big" if big_votes >= 25 else "Small"
        self.last_triggered_bot = "Standard Majority (No Bot at Step 9 yet)"
        return fallback_signal, "Standard 50-Bot Majority Consensus"

    def analyze_round(self, period, current_result):
        self.last_period = str(period)
        if self.is_paused:
            return  

        short_period = "..." + str(period)[-3:] if len(str(period)) >= 3 else "..." + str(period)

        # 1. ပထမဆုံး ယခင်ခန့်မှန်းချက်ကို စစ်ဆေးမည်
        if self.active_prediction:
            predicted = self.active_prediction
            if current_result.lower() == predicted.lower():
                self.total_wins += 1
                self.current_step = 0  
                self.consecutive_losses = 0
                self.send_telegram(f"✅ <b>50-BOT WIN! Period: {short_period}</b> (Result: {current_result})")
            else:
                self.total_losses += 1
                self.current_step += 1  
                self.consecutive_losses += 1
                
                if self.consecutive_losses >= 2:
                    self.send_telegram(f"🛡️ <b>Anti-Streak Override at Step {self.current_step + 1}</b>")

                self.send_telegram(f"❌ <b>50-BOT LOSS! Period: {short_period}</b> (Result: {current_result} | Streak: {self.consecutive_losses})")
            
            self.active_prediction = None

        # 2. Bot ၅၀ ရဲ့ ယခင်ရလဒ် အရှုံး/အနိုင် Streak များကို အပ်ဒိတ်လုပ်မည်
        if len(self.window) > 0:
            self.evaluate_all_bots_performance(current_result)

        self.window.append(current_result)
        if len(self.window) < 10:
            self.send_telegram(f"⏳ <b>Initializing 50 Powerful Bots... Period: {short_period}</b> ({len(self.window)}/10)")
            return

        # 3. Bot ၅၀ စနစ်မှ Step 9 Sniper Signal ကို ထုတ်ယူမည်
        final_prediction, regime_desc = self.run_50_bots_consensus(list(self.window))

        # Anti-Streak Force Override if needed
        if self.consecutive_losses >= 2:
            final_prediction = "Small" if current_result == "Big" else "Big"
            regime_desc = "Anti-Streak Emergency Reversal"

        self.active_prediction = final_prediction
        self.total_signals += 1  
        
        msg = (
            f"🎯 <b>50-BOT SNIPER SYSTEM | Period: {short_period}</b>\n\n"
            f"🤖 Status: <b>{regime_desc}</b>\n"
            f"🎯 <b>Signal:</b> <b>{final_prediction.upper()}</b>\n"
            f"💰 <b>Martingale:</b> Step {self.current_step + 1} ({self.get_current_multiplier()}x)"
        )
        self.send_telegram(msg)

def poll_telegram_commands(agent):
    try:
        requests.get(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/deleteWebhook?drop_pending_updates=true", timeout=10)
    except:
        pass

    offset = 0
    while True:
        try:
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates?offset={offset}&timeout=20"
            res = requests.get(url, timeout=25)
            if res.status_code == 200:
                for update in res.json().get("result", []):
                    offset = update["update_id"] + 1
                    message = update.get("message", {}) or update.get("edited_message", {})
                    chat_id = str(message.get("chat", {}).get("id", ""))
                    text = message.get("text", "").strip().lower()
                    
                    if chat_id == CHAT_ID:
                        if text == "/status":
                            total_resolved = agent.total_wins + agent.total_losses
                            win_rate = (agent.total_wins / total_resolved * 100) if total_resolved > 0 else 0.0
                            status_msg = (
                                f"📊 <b>50-BOT SNIPER STATUS REPORT</b>\n\n"
                                f"⚙️ State: <b>{'PAUSED 🛑' if agent.is_paused else 'RUNNING 🟢'}</b>\n"
                                f"🎯 Total Signals: <b>{agent.total_signals}</b>\n"
                                f"✅ Wins: <b>{agent.total_wins}</b> | ❌ Losses: <b>{agent.total_losses}</b>\n"
                                f"📈 <b>Win Rate: {win_rate:.2f}%</b>"
                            )
                            agent.send_telegram(status_msg)
                        elif text == "/pause":
                            agent.is_paused = True
                            agent.send_telegram("🛑 <b>Bot Paused.</b>")
                        elif text == "/resume":
                            agent.is_paused = False
                            agent.send_telegram("🟢 <b>Bot Resumed.</b>")
        except Exception as e:
            print(f"Telegram Polling Error: {e}", flush=True)
        time.sleep(1)

def run_bot():
    print("🤖 Background Wingo Bot Thread Started (50-Bot Sniper & Smart Engine)...", flush=True)
    agent = FiftyBotSniperEngine()
    
    threading.Thread(target=poll_telegram_commands, args=(agent,), daemon=True).start()

    last_period = ""
    url = "https://6lotteryapi.com/api/webapi/GetNoaverageEmerdList"
    auth_token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpYXQiOiIxNzg3OTgxNTA5IiwibmJmIjoiMTc4Nzk4MTUwOSIsImV4cCI6IjE3ODc5ODMzMDkiLCJodHRwOi8vc2NoZW1hcy5taWNyb3NvZnQuY29tL3dzLzIwMDgvMDYvaWRlbnRpdHkvY2xhaW1zL2V4cGlyYXRpb24iOiI4LzI5LzIwMjYgMTI6MzE2NDkgUE0iLCJodHRwOi8vc2NoZW1hcy5taWNyb3NvZnQuY29tL3dzLzIwMDgvMDYvaWRlbnRpdHkvY2xhaW1zL3JvbGUiOiJBY2Nlc3NfVG9rZW4iLCJVc2VySWQiOiIxMDEyMjEzIiwiVXNlck5hbWUiOiI5NTk3NDA5MzkzNzAiLCJVc2VyUGhvdG8iOiI5IiwiTmlja05hbWUiOiJUaetsR3lpIiwiQW1vdW50IjoiODcuMzAiLCJJbnRlZ3JhbCI6IjAiLCJMb2dpbk1hcmsiOiJINSIsImxvZ2luVGltZSI6IjgvMjkvMjAyNiAxMjowMTo0OSBQTSIsImxvZ2luSVBBZGRyZXNzIjoiNDUuNDEuMTA0LjI0MCIsImRiTnVtYmVyIjoiMCIsIklzdmFsaWRhdG9yIjoiMCIsIktleUNvZGUiOiIzMjMzMiIsImRva2VuVHypZSI6IjJBY2Nlc3NfVG9rZW4iLCJob25lVHlpZSI6IjAiLCJVc2VyVHlpZSI6IjAiLCJVc2VyTmFtZ2UiOiIuIiwiaXNzIjoiand0SXNzdWVyIiwiYXVkIjoibG90dGVyeVRpY2tldCJ9.ZL0Y9gexUTCsKwWeZhCLAAw8AABEYJt0GnIzIviMG4g"

    headers = {
        "accept": "application/json, text/plain, */*",
        "authorization": f"Bearer {auth_token}",
        "content-type": "application/json;charset=UTF-8",
        "origin": "https://6win598.com",
        "referer": "https://6win598.com/",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    
    while True:
        try:
            payload = {
                "pageSize": 10, 
                "pageNo": 1, 
                "typeId": 30, 
                "language": 7,
                "random": "036263f367384d418be07465793c8da8",
                "signature": "55F4FD150F15F090B943374F3C9BE78B",
                "timestamp": int(time.time())
            }
            
            response = requests.post(url, headers=headers, json=payload, timeout=5)
            if response.status_code == 200:
                data = response.json()
                list_data = data.get("data", {}).get("list", [])
                if len(list_data) > 0:
                    latest_round = list_data[0]
                    raw_period = str(latest_round.get("issueNumber"))
                    current_period = str(int(raw_period) + 2)
                    number = int(latest_round.get("number"))
                    current_result = "Big" if number >= 5 else "Small"
                    
                    if current_period != last_period:
                        last_period = current_period
                        print(f"API Success Sync - Round: {current_period} -> Result: {current_result}", flush=True)
                        agent.analyze_round(current_period, current_result)
            else:
                print(f"API Error Response: {response.text}", flush=True)
        except Exception as e:
            print(f"API Exception Error: {e}", flush=True)
        time.sleep(2)

threading.Thread(target=run_bot, daemon=True).start()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
