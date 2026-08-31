import requests
import time
import json
import os
import threading
import logging
from collections import deque
from flask import Flask
from datetime import datetime

# ==========================================
# ⭐ Telegram နဲ့ Supabase အချက်အလက်များ (ပြောင်းပြီး)
# ==========================================

# Telegram Token - အသစ်
TELEGRAM_TOKEN = "8771982889:AAFzEnu7-DSl4gNktrGfpS1p28haP8-hoMs"

# Channel ID (Signal ပို့မယ်) - အသစ်
CHAT_ID = "-1004357168336"

# Admin ID (Command သုံးမယ်) - မပြောင်းဘူး
ADMIN_IDS = ["8745116942"]

# Extra Chats
EXTRA_CHATS = []

# ==========================================
# Supabase (မပြောင်းဘူး)
# ==========================================
SUPABASE_URL = "https://msgzacekhrvlqkqgjvly.supabase.co"
SUPABASE_KEY = "sb_publishable_Sg4eQ6ATCwd6rInVTS62IA_SW1jNPI5"
# ==========================================

# ==========================================
# Logging Setup
# ==========================================
if not os.path.exists('logs'):
    os.makedirs('logs')

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(f'logs/bot_{datetime.now().strftime("%Y%m%d")}.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Error Logger
error_logger = logging.getLogger('error_logger')
error_handler = logging.FileHandler(f'logs/errors_{datetime.now().strftime("%Y%m%d")}.log')
error_handler.setLevel(logging.ERROR)
error_logger.addHandler(error_handler)

app = Flask(__name__)

@app.route('/')
def home():
    return "Pro Fast Signal Dual-Agent AI Bot is Running 24/7!"

# ==========================================
# Telegram Functions
# ==========================================

def send_telegram(message):
    """Signal ကို Channel ကိုပို့တယ်"""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": message, "parse_mode": "HTML"}
    try:
        response = requests.post(url, json=payload, timeout=5)
        if response.status_code == 200:
            return True
        else:
            error_logger.error(f"❌ Telegram send failed: {response.status_code}")
            return False
    except Exception as e:
        error_logger.error(f"❌ Telegram send error: {e}")
        return False

def send_telegram_to_admin(message):
    """Response ကို Admin (Personal Chat) ကိုပို့တယ်"""
    for admin_id in ADMIN_IDS:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {"chat_id": admin_id, "text": message, "parse_mode": "HTML"}
        try:
            requests.post(url, json=payload, timeout=5)
            logger.info(f"✅ Response sent to admin: {admin_id}")
        except Exception as e:
            error_logger.error(f"❌ Failed to send to admin {admin_id}: {e}")

def send_telegram_to_all(message):
    """Signal ကို Channel နဲ့ Extra Chats အားလုံးကိုပို့တယ်"""
    all_chats = [CHAT_ID] + EXTRA_CHATS
    
    for chat_id in all_chats:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {"chat_id": chat_id, "text": message, "parse_mode": "HTML"}
        try:
            requests.post(url, json=payload, timeout=5)
            logger.info(f"✅ Sent to {chat_id}")
        except Exception as e:
            error_logger.error(f"❌ Failed to send to {chat_id}: {e}")

# ==========================================
# Telegram Command Handler
# ==========================================

def poll_telegram_commands():
    """Telegram Command တွေကိုဖမ်းတယ် (Admin ရဲ့ Personal Chat ကနေ)"""
    
    # Webhook ရှင်း
    try:
        requests.get(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/deleteWebhook?drop_pending_updates=true", timeout=5)
        logger.info("✅ Webhook cleared")
    except Exception as e:
        error_logger.error(f"❌ Webhook error: {e}")
    
    offset = 0
    offset_file = "logs/telegram_offset.txt"
    
    try:
        if os.path.exists(offset_file):
            with open(offset_file, 'r') as f:
                offset = int(f.read().strip())
            logger.info(f"📂 Offset loaded: {offset}")
    except:
        pass
    
    logger.info("👀 Polling for Telegram commands from admin...")
    
    while True:
        try:
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates?offset={offset}&timeout=20"
            response = requests.get(url, timeout=25)
            
            if response.status_code == 200:
                data = response.json()
                updates = data.get("result", [])
                
                for update in updates:
                    offset = update["update_id"] + 1
                    
                    try:
                        with open(offset_file, 'w') as f:
                            f.write(str(offset))
                    except:
                        pass
                    
                    message = update.get("message", {})
                    chat_id = str(message.get("chat", {}).get("id", ""))
                    text = message.get("text", "").strip()
                    username = message.get("from", {}).get("username", "Unknown")
                    
                    logger.info(f"📩 From {username} (Chat: {chat_id}): {text}")
                    
                    # Admin ဖြစ်မှ Command သုံးနိုင်
                    if chat_id not in ADMIN_IDS:
                        logger.warning(f"⛔ Unauthorized: {chat_id}")
                        continue
                    
                    # Command Processing
                    if text.lower() == "/test":
                        send_telegram_to_admin("✅ Test command received! Bot is working.")
                        logger.info("✅ Test command executed")
                    
                    elif text.lower() == "/status":
                        send_telegram_to_admin("📊 Bot is running!")
                        logger.info("📊 Status command executed")
                    
                    elif text.lower() == "/chatid":
                        msg = f"📌 <b>Channel ID:</b> <code>{CHAT_ID}</code>\n📌 <b>Your Chat ID:</b> <code>{chat_id}</code>"
                        send_telegram_to_admin(msg)
                        logger.info(f"📌 Chat ID sent: {chat_id}")
                    
                    elif text.lower() == "/help":
                        help_msg = (
                            "📚 <b>Available Commands:</b>\n\n"
                            "/test - Test bot\n"
                            "/status - Check status\n"
                            "/chatid - Get Chat IDs\n"
                            "/help - Show this message\n\n"
                            f"📌 Channel ID: <code>{CHAT_ID}</code>\n"
                            f"📌 Your Chat ID: <code>{chat_id}</code>"
                        )
                        send_telegram_to_admin(help_msg)
                        logger.info("📚 Help command executed")
                    
                    elif text.lower() == "/pause":
                        send_telegram_to_admin("🛑 Bot paused!")
                        logger.info("⏸️ Pause command executed")
                    
                    elif text.lower() == "/resume":
                        send_telegram_to_admin("🟢 Bot resumed!")
                        logger.info("▶️ Resume command executed")
        
        except Exception as e:
            error_logger.error(f"❌ Polling error: {e}")
        
        time.sleep(1)

class EarlySignalDetector:
    def __init__(self):
        self.min_quality = 0.55
        self.patterns = {
            'strong_big': (['Big', 'Big', 'Big'], 'Big', 0.90),
            'strong_small': (['Small', 'Small', 'Small'], 'Small', 0.90),
            'double_top': (['Big', 'Big', 'Small'], 'Small', 0.78),
            'double_bottom': (['Small', 'Small', 'Big'], 'Big', 0.78),
            'reversal_up': (['Small', 'Big', 'Big'], 'Big', 0.72),
            'reversal_down': (['Big', 'Small', 'Small'], 'Small', 0.72),
            'momentum_big': (['Small', 'Big', 'Big'], 'Big', 0.70),
            'momentum_small': (['Big', 'Small', 'Small'], 'Small', 0.70),
        }
    
    def detect_pattern(self, recent):
        if len(recent) < 3:
            return None, 0.0, "Waiting"
        pattern = [str(x).capitalize() for x in recent[-3:]]
        for name, (pat, pred, quality) in self.patterns.items():
            if pattern == pat:
                return pred, quality, name
        return None, 0.0, "No Pattern"
    
    def get_momentum_score(self, recent):
        if len(recent) < 3:
            return 0.50
        pattern = [str(x).capitalize() for x in recent[-3:]]
        big_count = pattern.count('Big')
        if big_count >= 2:
            return 0.65 + (0.05 * (big_count - 1))
        elif big_count <= 1:
            return 0.35 - (0.05 * (1 - big_count))
        return 0.50

class FastProAgent:
    def __init__(self):
        self.window = deque(maxlen=3)
        self.current_step = 0
        self.last_step = 0
        self.active_prediction = None
        self.last_state = None
        self.is_paused = False
        self.last_signal_period = None
        self.min_gap = 2
        self.consecutive_signals = 0
        self.consecutive_losses = 0
        
        self.quality_thresholds = {
            0: 0.52, 1: 0.55, 2: 0.60,
            3: 0.70, 4: 0.75, 5: 0.80,
        }
        self.default_threshold = 0.80
        
        self.total_signals = 0
        self.total_wins = 0
        self.total_losses = 0
        self.max_martingale_step_reached = 0
        self.signals_at_step = {}
        self.wins_at_step = {}
        self.pattern_stats = {}
        
        self.lr = 0.40
        self.q_table = self.load_q_table()
        self.detector = EarlySignalDetector()
        
        logger.info("🚀 FastProAgent Initialized Successfully!")
    
    def get_current_multiplier(self):
        return 2 ** self.current_step
    
    def load_q_table(self):
        headers = {
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}"
        }
        try:
            res = requests.get(f"{SUPABASE_URL}/rest/v1/q_table?select=*", headers=headers, timeout=3)
            if res.status_code == 200:
                data = res.json()
                q_dict = {}
                for row in data:
                    q_dict[row['state']] = row['actions']
                logger.info(f"📂 Q-Table loaded: {len(q_dict)} states")
                return q_dict
        except Exception as e:
            error_logger.error(f"❌ Supabase load error: {e}")
        return {}
    
    def save_q_table(self, state, actions):
        headers = {
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Content-Type": "application/json",
            "Prefer": "resolution=merge-duplicates"
        }
        payload = {"state": state, "actions": actions}
        try:
            requests.post(f"{SUPABASE_URL}/rest/v1/q_table", headers=headers, json=payload, timeout=3)
        except Exception as e:
            error_logger.error(f"❌ Q-Table save error: {e}")
    
    def get_state_key(self):
        return ",".join(list(self.window))
    
    def get_q_action(self, state):
        if state not in self.q_table:
            self.q_table[state] = {"Big": 0.0, "Small": 0.0}
        actions = self.q_table[state]
        if actions["Big"] > actions["Small"]:
            return "Big"
        elif actions["Small"] > actions["Big"]:
            return "Small"
        return None
    
    def get_q_quality(self, state, action):
        if state in self.q_table:
            actions = self.q_table[state]
            total = abs(actions['Big']) + abs(actions['Small'])
            if total > 0:
                return abs(actions[action]) / total
        return 0.0
    
    def update_q_table(self, state, action, reward):
        if state not in self.q_table:
            self.q_table[state] = {"Big": 0.0, "Small": 0.0}
        old_q = self.q_table[state][action]
        new_q = old_q + self.lr * (reward - old_q)
        self.q_table[state][action] = new_q
        self.save_q_table(state, self.q_table[state])
    
    def get_quick_signal(self, recent, state_key, current_step):
        quality_boost = 0.08 if current_step <= 2 else -0.05
        
        pred, quality, pattern_name = self.detector.detect_pattern(recent)
        if pred:
            quality += quality_boost
            if quality >= self.get_min_quality(current_step):
                if pattern_name not in self.pattern_stats:
                    self.pattern_stats[pattern_name] = {'total': 0, 'wins': 0}
                self.pattern_stats[pattern_name]['total'] += 1
                return pred, min(quality, 1.0), f"Pattern: {pattern_name}"
        
        momentum_score = self.detector.get_momentum_score(recent)
        momentum_score += quality_boost * 0.5
        if momentum_score >= 0.65:
            return 'Big', min(momentum_score, 1.0), "Momentum"
        elif momentum_score <= 0.35:
            return 'Small', min(1 - momentum_score, 1.0), "Momentum"
        
        if state_key in self.q_table:
            q_pred = self.get_q_action(state_key)
            if q_pred:
                q_quality = self.get_q_quality(state_key, q_pred)
                q_quality += quality_boost
                if q_quality >= self.get_min_quality(current_step):
                    return q_pred, min(q_quality, 1.0), "Q-Memory"
        
        return None, 0.0, "Waiting"
    
    def get_min_quality(self, current_step):
        return self.quality_thresholds.get(current_step, self.default_threshold)
    
    def should_emit_signal(self, quality, current_step, period):
        if self.is_paused:
            return False
        if self.last_signal_period:
            try:
                if int(period) - int(self.last_signal_period) < self.min_gap:
                    return False
            except:
                pass
        threshold = self.get_min_quality(current_step)
        if self.consecutive_losses >= 2:
            threshold += 0.05
        if self.consecutive_signals >= 3:
            threshold -= 0.03
        return quality >= threshold
    
    def analyze_round(self, period, current_result):
        if self.is_paused:
            return
        
        short_period = str(period)[-4:] if len(str(period)) >= 4 else str(period)
        
        if self.active_prediction and self.last_state:
            predicted = self.active_prediction
            reward = 0
            current_level = self.current_step + 1
            
            if current_level > self.max_martingale_step_reached:
                self.max_martingale_step_reached = current_level
            
            if current_result.lower() == predicted.lower():
                reward = 6.0 - self.current_step if self.current_step <= 2 else 3.0
                self.total_wins += 1
                self.wins_at_step[self.current_step] = self.wins_at_step.get(self.current_step, 0) + 1
                self.consecutive_losses = 0
                if hasattr(self, 'last_pattern') and self.last_pattern in self.pattern_stats:
                    self.pattern_stats[self.last_pattern]['wins'] += 1
                self.current_step = 0
                send_telegram_to_all(f"✅ <b>WIN!</b> Period: {short_period}\n💰 Step {current_level} ({2**(current_level-1)}x) → Reset to 1x")
            else:
                reward = -4.0 - (self.current_step * 0.5)
                self.total_losses += 1
                self.consecutive_losses += 1
                self.current_step += 1
                step_level = self.current_step + 1
                multiplier = self.get_current_multiplier()
                send_telegram_to_all(f"❌ <b>LOSS!</b> Period: {short_period}\n📈 Step {step_level} ({multiplier}x)")
                if self.current_step > 2:
                    send_telegram_to_all(f"⚠️ <b>WARNING!</b> Step exceeded 3x!\nCurrent: Step {self.current_step + 1} ({multiplier}x)\nKeep going until win!")
            
            self.update_q_table(self.last_state, predicted, reward)
            self.active_prediction = None
        
        self.window.append(current_result)
        if len(self.window) < 3:
            return
        
        recent_list = list(self.window)
        state_key = self.get_state_key()
        signal, quality, method = self.get_quick_signal(recent_list, state_key, self.current_step)
        
        if signal and self.should_emit_signal(quality, self.current_step, period):
            self.last_state = state_key
            self.active_prediction = signal
            self.last_step = self.current_step
            self.last_signal_period = period
            self.consecutive_signals += 1
            self.total_signals += 1
            self.signals_at_step[self.current_step] = self.signals_at_step.get(self.current_step, 0) + 1
            self.last_pattern = method.split(":")[-1].strip() if ":" in method else method
            
            current_multiplier = self.get_current_multiplier()
            step_level = self.current_step + 1
            focus_msg = "🎯 FOCUS: Win in 1x-3x zone!" if self.current_step <= 2 else "⚠️ High Step! Be careful!"
            
            msg = (f"⚡ <b>FAST SIGNAL</b> | Period: {short_period}\n\n"
                   f"🎯 Prediction: <b>{signal.upper()}</b>\n"
                   f"📊 Quality: <b>{quality*100:.0f}%</b>\n"
                   f"🔍 Method: <b>{method}</b>\n"
                   f"💰 Step: <b>{step_level} ({current_multiplier}x)</b>\n"
                   f"{focus_msg}\n"
                   f"📈 Win Rate: <b>{self.get_win_rate():.1f}%</b>")
            send_telegram_to_all(msg)
            logger.info(f"📊 Signal: {signal} | Q:{quality:.2f} | {method} | Step:{step_level}")
    
    def get_win_rate(self):
        total = self.total_wins + self.total_losses
        return 0.0 if total == 0 else (self.total_wins / total) * 100

# ==========================================
# Main Bot Runner
# ==========================================

def run_bot():
    agent = FastProAgent()
    
    cmd_thread = threading.Thread(target=poll_telegram_commands)
    cmd_thread.daemon = True
    cmd_thread.start()
    
    logger.info("👑 FastPro Bot Started!")
    logger.info(f"📨 Sending signals to Channel: {CHAT_ID}")
    logger.info(f"👤 Admin: {ADMIN_IDS}")
    
    url = "https://6lotteryapi.com/api/webapi/GetNoaverageEmerdList"
    headers = {
        "accept": "application/json, text/plain, */*",
        "authorization": "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpYXQiOiIxNzg3OTgxNTA5IiwibmJmIjoiMTc4Nzk4MTUwOSIsImV4cCI6IjE3ODc5ODMzMDkiLCJodHRwOi8vc2NoZW1hcy5taWNyb3NvZnQuY29tL3dzLzIwMDgvMDYvaWRlbnRpdHkvY2xhaW1zL2V4cGlyYXRpb24iOiI4LzI5LzIwMjYgMTI6MzE6NDkgUE0iLCJodHRwOi8vc2NoZW1hcy5taWNyb3NvZnQuY29tL3dzLzIwMDgvMDYvaWRlbnRpdHkvY2xhaW1zL3JvbGUiOiJBY2Nlc3NfVG9rZW4iLCJVc2VySWQiOiIxMDEyMjEzIiwiVXNlck5hbWUiOiI5NTk3NDA5MzkzNzAiLCJVc2VyUGhvdG8iOiI5IiwiTmlja05hbWUiOiJUaetsR3lpIiwiQW1vdW50IjoiODcuMzAiLCJJbnRlZ3JhbCI6IjAiLCJMb2dpbk1hcmsiOiJINSIsIkxvZ2luVGltZSI6IjgvMjkvMjAyNiAxMjowMTo0OSBQTSIsIjxvZ2luSVBBZGRyZXNzIjoiNDUuNDEuMTA0LjI0MCIsImRiTnVtYmVyIjoiMCIsIklzdmFsaWRhdG9yIjoiMCIsIktleUNvZGUiOiIzMjMzMiIsIkRva2VuVHlwZSI6IkFjY2Vzc19Ub2tlbiIsIlBob25lVHlwZSI6IjAiLCJVc2VyVHlwZSI6IjAiLCJVc2VyTmFtZTIiOiIuIiwiaXNzIjoiand0SXNzdWVyIiwiYXVkIjoibG90dGVyeVRpY2tldCJ9.ZL0Y9gexUTCsKwWeZhCLAAw8AABEYJt0GnIzIviMG4g",
        "content-type": "application/json;charset=UTF-8",
        "origin": "https://6win598.com",
        "referer": "https://6win598.com/",
        "user-agent": "Mozilla/5.0"
    }
    payload = {
        "pageSize": 10, "pageNo": 1, "typeId": 30, "language": 7,
        "random": "036263f367384d418be07465793c8da8",
        "signature": "55F4FD150F15F090B943374F3C9BE78B",
        "timestamp": 1787981526
    }
    
    last_period = ""
    error_count = 0
    max_errors = 5
    
    while True:
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=3)
            response.raise_for_status()
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
                    agent.analyze_round(current_period, current_result)
                    error_count = 0
        except requests.exceptions.Timeout:
            error_count += 1
            if error_count % 10 == 0:
                logger.warning(f"⚠️ API Timeout ({error_count}x)")
        except requests.exceptions.ConnectionError:
            error_count += 1
            if error_count % 5 == 0:
                logger.error(f"❌ Connection Error ({error_count}x)")
        except Exception as e:
            error_count += 1
            if error_count % 5 == 0:
                error_logger.error(f"❌ Unexpected error: {e}")
        if error_count > max_errors:
            logger.warning(f"⚠️ Too many errors ({error_count}), sleeping 5s...")
            time.sleep(5)
            error_count = 0
        time.sleep(0.5)

# ==========================================
# Main Entry Point
# ==========================================

if __name__ == "__main__":
    bot_thread = threading.Thread(target=run_bot)
    bot_thread.daemon = True
    bot_thread.start()
    
    port = int(os.environ.get("PORT", 10000))
    logger.info(f"🌐 Flask server running on port {port}")
    app.run(host="0.0.0.0", port=port)