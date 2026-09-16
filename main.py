#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
HYBRID V7.0 — Test for signature validity
"""
import os
import time
import math
import json
import sqlite3
import threading
from collections import Counter, defaultdict, deque
from datetime import datetime, timezone
import requests
from flask import Flask, jsonify, render_template_string

# ============================================================
# CONFIG — V7 original (hard-coded for test)
# ============================================================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "8913070806:AAF3rP0zKJtofE-5KVesqcdoHzn7Go0avho")
CHAT_ID = os.getenv("CHAT_ID", "-1004402480797")

API_URL = os.getenv("RESULT_API_URL", "https://6lotteryapi.com/api/webapi/GetNoaverageEmerdList")
API_AUTH = os.getenv("RESULT_API_AUTH", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpYXQiOiIxNzg3OTgxNTA5IiwibmJmIjoiMTc4Nzk4MTUwOSIsImV4cCI6IjE3ODc5ODMzMDkiLCJodHRwOi8vc2NoZW1hcy5taWNyb3NvZnQuY29tL3dzLzIwMDgvMDYvaWRlbnRpdHkvY2xhaW1zL2V4cGlyYXRpb24iOiI4LzI5LzIwMjYgMTI6MzE2NDkgUE0iLCJodHRwOi8vc2NoZW1hcy5taWNyb3NvZnQuY29tL3dzLzIwMDgvMDYvaWRlbnRpdHkvY2xhaW1zL3JvbGUiOiJBY2Nlc3NfVG9rZW4iLCJVc2VySWQiOiIxMDEyMjEzIiwiVXNlck5hbWUiOiI5NTk3NDA5MzkzNzAiLCJVc2VyUGhvdG8iOiI5IiwiTmlja05hbWUiOiJUaGVrR3lpIiwiQW1vdW50IjoiODcuMzAiLCJJbnRlZ3JhbCI6IjAiLCJMb2dpbk1hcmsiOiJINSIsImxvZ2luVGltZSI6IjcvMjkvMjAyNiAxMjowMTo0OSBQTSIsImxvZ2luSVBBZGRyZXNzIjoiNDUuNDEuMTA0LjI0MCIsImRiTnVtYmVyIjoiMCIsIklzdmFsaWRhdG9yIjoiMCIsIktleUNvZGUiOiIzMjMzMiIsImRva2VuVHlwZSI6IjJBY2Nlc3NfVG9rZW4iLCJob25lVHlwZSI6IjAiLCJVc2VyVHlwZSI6IjAiLCJVc2VyTmFtZ2UiOiIuIiwiaXNzIjoiand0SXNzdWVyIiwiYXVkIjoibG90dGVyeVRpY2tldCJ9.ZL0Y9gexUTCsKwWeZhCLAAw8AABEYJt0GnIzIviMG4g")
API_ORIGIN = os.getenv("API_ORIGIN", "https://6win598.com")
API_REFERER = os.getenv("API_REFERER", "https://6win598.com/")

API_TYPE_ID = int(os.getenv("API_TYPE_ID", "30"))
API_LANGUAGE = int(os.getenv("API_LANGUAGE", "7"))
PERIOD_OFFSET = int(os.getenv("PERIOD_OFFSET", "2"))
POLL_SECONDS = float(os.getenv("POLL_SECONDS", "2.0"))
REQUEST_TIMEOUT = float(os.getenv("REQUEST_TIMEOUT", "10"))

DB_PATH = os.getenv("DB_PATH", "hybrid_v7_test.db")

API_RANDOM = os.getenv("API_RANDOM", "036263f367384d418be07465793c8da8")
API_SIGNATURE = os.getenv("API_SIGNATURE", "55F4FD150F15F090B943374F3C9BE78B")

PORT = int(os.getenv("PORT", "8080"))

app = Flask(__name__)
global_state = {}

# ============================================================
# API TEST
# ============================================================

def test_api():
    """Test V7 API call — pure, no state"""
    headers = {
        "accept": "application/json, text/plain, */*",
        "content-type": "application/json;charset=UTF-8",
        "user-agent": "Mozilla/5.0",
    }
    if API_AUTH:
        headers["authorization"] = f"Bearer {API_AUTH}"
    if API_ORIGIN:
        headers["origin"] = API_ORIGIN
    if API_REFERER:
        headers["referer"] = API_REFERER

    payload = {
        "pageSize": 10,
        "pageNo": 1,
        "typeId": API_TYPE_ID,
        "language": API_LANGUAGE,
        "timestamp": int(time.time()),
    }
    if API_RANDOM:
        payload["random"] = API_RANDOM
    if API_SIGNATURE:
        payload["signature"] = API_SIGNATURE

    print("=" * 60, flush=True)
    print(" V7 CODE TEST", flush=True)
    print("=" * 60, flush=True)
    print(f"API_URL: {API_URL}", flush=True)
    print(f"API_TYPE_ID: {API_TYPE_ID}", flush=True)
    print(f"API_AUTH len: {len(API_AUTH)}", flush=True)
    print(f"API_RANDOM: {API_RANDOM}", flush=True)
    print(f"API_SIGNATURE: {API_SIGNATURE}", flush=True)
    print(f"HEADERS: {list(headers.keys())}", flush=True)
    print(f"PAYLOAD: {payload}", flush=True)
    print("-" * 60, flush=True)

    try:
        r = requests.post(API_URL, json=payload, headers=headers, timeout=REQUEST_TIMEOUT)
        print(f"STATUS: {r.status_code}", flush=True)
        print(f"RAW: {r.text[:1000]}", flush=True)

        data = r.json()
        print(f"PARSED: {json.dumps(data, indent=2)[:1000]}", flush=True)

        items = data.get("data", {}).get("list", []) if isinstance(data, dict) else []
        print(f"ITEMS COUNT: {len(items)}", flush=True)
        if items:
            print(f"FIRST ITEM: {items[0]}", flush=True)

        global_state["last_test"] = {
            "status": r.status_code,
            "raw": r.text[:2000],
            "parsed": data,
            "items_count": len(items),
            "first_item": items[0] if items else None,
            "payload_sent": payload,
            "headers_sent": {k: (v[:30] + "..." if len(v) > 30 else v) for k, v in headers.items()},
        }

    except Exception as e:
        print(f"ERROR: {type(e).__name__}: {e}", flush=True)
        import traceback
        traceback.print_exc()
        global_state["last_test"] = {"error": f"{type(e).__name__}: {e}"}

    print("=" * 60, flush=True)


# ============================================================
# TEST ENDPOINTS
# ============================================================

@app.route("/")
def home():
    return render_template_string("""
<!doctype html>
<html><head><meta charset="utf-8"><title>V7 TEST</title>
<style>
body{background:#0f172a;color:#f8fafc;font-family:monospace;padding:20px;margin:0}
h1{color:#22d3ee}.card{background:#1e293b;padding:16px;border-radius:10px;margin-bottom:14px}
pre{white-space:pre-wrap;word-wrap:break-word;background:#0a0f1e;padding:12px;border-radius:6px;max-height:600px;overflow:auto}
.ok{color:#4ade80}.fail{color:#f87171}.warn{color:#facc15}
</style></head><body>
<h1>🧪 V7 API TEST</h1>
<div class="card">
<h3>Config</h3>
<pre>API_URL: {{ config.API_URL }}
API_TYPE_ID: {{ config.API_TYPE_ID }}
API_AUTH_LEN: {{ config.API_AUTH_LEN }}
API_RANDOM: {{ config.API_RANDOM }}
API_SIGNATURE: {{ config.API_SIGNATURE }}</pre>
</div>

{% if test %}
<div class="card">
<h3>Last Test</h3>
{% if test.error %}
<p class="fail">ERROR: {{ test.error }}</p>
{% else %}
<p>Status: <b class="{{ 'ok' if test.status == 200 else 'fail' }}">{{ test.status }}</b></p>
<p>Items: <b class="{{ 'ok' if test.items_count > 0 else 'fail' }}">{{ test.items_count }}</b></p>
<p>Payload: {{ test.payload_sent }}</p>
<p>Headers: {{ test.headers_sent }}</p>
<h4>Raw Response:</h4>
<pre>{{ test.raw }}</pre>
{% if test.first_item %}
<h4>First Item:</h4>
<pre>{{ test.first_item }}</pre>
{% endif %}
{% endif %}
</div>
{% endif %}

<div class="card">
<h3>Actions</h3>
<p><a href="/run" style="color:#22d3ee">▶️ Run API Test</a></p>
<p><a href="/api/test" style="color:#22d3ee">📊 JSON Test</a></p>
</div>
</body></html>
""", config={
        "API_URL": API_URL,
        "API_TYPE_ID": API_TYPE_ID,
        "API_AUTH_LEN": len(API_AUTH),
        "API_RANDOM": API_RANDOM,
        "API_SIGNATURE": API_SIGNATURE,
    }, test=global_state.get("last_test"))


@app.route("/run")
def run_test():
    test_api()
    return "<meta http-equiv='refresh' content='0;url=/'>Run complete. <a href='/'>Back</a>"


@app.route("/api/test")
def api_test():
    test_api()
    return jsonify(global_state.get("last_test", {}))


@app.route("/api/status")
def api_status():
    return jsonify({
        "config": {
            "API_URL": API_URL,
            "API_TYPE_ID": API_TYPE_ID,
            "API_AUTH_LEN": len(API_AUTH),
            "API_RANDOM": API_RANDOM,
            "API_SIGNATURE": API_SIGNATURE,
        },
        "last_test": global_state.get("last_test"),
    })


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":
    print("=" * 60, flush=True)
    print(" HYBRID V7 TEST", flush=True)
    print("=" * 60, flush=True)

    # Auto-run API test at startup
    test_api()

    # Start poll loop that re-tests every 60 sec
    def loop():
        while True:
            time.sleep(60)
            test_api()

    threading.Thread(target=loop, daemon=True).start()

    print(f"[FLASK] Starting on port {PORT}", flush=True)
    app.run(host="0.0.0.0", port=PORT, debug=False)
