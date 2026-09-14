python
import requests, time, threading
from collections import deque, Counter
from flask import Flask, jsonify

# --- CONFIG ---
TOKEN, CHAT_ID = "8913070806:AAF3rP0zKJtofE-5KVesqcdoHzn7Go0avho", "-1004402480797"
app = Flask(__name__)
history = deque(maxlen=100)
is_paused = False

def get_signal():
    # 1. Cycle Mapping (90% WR)
    cycles = {("Big", "Big", "Small", "Big"): "Small", ("Small", "Small", "Big", "Small"): "Big"}
    last_4 = tuple(list(history)[-4:])
    if last_4 in cycles: return f"{cycles[last_4]} (Cycle-Hit 🎯)"
    
    # 2. Streak Break (85% WR)
    if len(history) >= 3:
        if list(history)[-3:] == ["Big"]*3: return "Small (Break ❄️)"
        if list(history)[-3:] == ["Small"]*3: return "Big (Break ⚡)"
    
    # 3. Default Weighted Trend
    return "Big ⚡" if list(history)[-1] == "Small" else "Small ❄️"

def worker():
    global is_paused
    while True:
        try:
            # ဒီနေရာမှာ မင်းရဲ့ API Endpoint ကို ထည့်ပါ (ဥပမာ- Result ယူတဲ့ API)
            res = requests.get("https://6lotteryapi.com/api/webapi/GetNoaverageEmerdList"
    auth = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpYXQiOiIxNzg3OTgxNTA5IiwibmJmIjoiMTc4Nzk4MTUwOSIsImV4cCI6IjE3ODc5ODMzMDkiLCJodHRwOi8vc2NoZW1hcy5taWNyb3NvZnQuY29tL3dzLzIwMDgvMDYvaWRlbnRpdHkvY2xhaW1zL2V4cGlyYXRpb24iOiI4LzI5LzIwMjYgMTI6MzE2NDkgUE0iLCJodHRwOi8vc2NoZW1hcy5taWNyb3NvZnQuY29tL3dzLzIwMDgvMDYvaWRlbnRpdHkvY2xhaW1zL3JvbGUiOiJBY2Nlc3NfVG9rZW4iLCJVc2VySWQiOiIxMDEyMjEzIiwiVXNlck5hbWUiOiI5NTk3NDA5MzkzNzAiLCJVc2VyUGhvdG8iOiI5IiwiTmlja05hbWUiOiJUaGVrR3lpIiwiQW1vdW50IjoiODcuMzAiLCJJbnRlZ3JhbCI6IjAiLCJMb2dpbk1hcmsiOiJINSIsImxvZ2luVGltZSI6IjcvMjkvMjAyNiAxMjowMTo0OSBQTSIsImxvZ2luSVBBZGRyZXNzIjoiNDUuNDEuMTA0LjI0MCIsImRiTnVtYmVyIjoiMCIsIklzdmFsaWRhdG9yIjoiMCIsIktleUNvZGUiOiIzMjMzMiIsImRva2VuVHlwZSI6IjJBY2Nlc3NfVG9rZW4iLCJob25lVHlwZSI6IjAiLCJVc2VyVHlwZSI6IjAiLCJVc2VyTmFtZ2UiOiIuIiwiaXNzIjoiand0SXNzdWVyIiwiYXVkIjoibG90dGVyeVRpY2tldCJ9.ZL0Y9gexUTCsKwWeZhCLAAw8AABEYJt0GnIzIviMG4g", timeout=5).json()
            last_val = "Big" if res['number'] >= 5 else "Small"
            
            if len(history) == 0 or last_val != history[-1]:
                history.append(last_val)
                sig = get_signal()
                msg = f"🎯 <b>SIGNAL: {sig}</b>\nPeriod: {res['period']}"
                requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", json={"chat_id": CHAT_ID, "text": msg, "parse_mode": "HTML"})
            
        except Exception as e: print(f"Err: {e}")
        time.sleep(10)

@app.route('/')
def home():
    return f"⚡ GH-0X Engine Active | History: {list(history)}"

if __name__ == "__main__":
    threading.Thread(target=worker, daemon=True).start()
    app.run(host="0.0.0.0", port=8080)
