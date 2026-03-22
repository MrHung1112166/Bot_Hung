import yfinance as yf
import pandas as pd
import time
import requests
from datetime import datetime
import os

# ====== CONFIG ======
SYMBOLS = ["HPG.VN","DGC.VN","VIC.VN","NVL.VN","BSR.VN","ACB.VN","VCB.VN","BID.VN","BCM.VN","BVH.VN","CTG.VN","FPT.VN","GAS.VN","GVR.VN","HDB.VN","MBB.VN","MSN.VN","MSH.VN","MWG.VN","PLX.VN","POW.VN","SAB.VN","SHB.VN","TCB.VN","TPB.VN","VHM.VN","VIB.VN","VNM.VN","VRE.VN"]

TOKEN = os.getenv("TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

RSI_PERIOD = 14
RSI_OVERBOUGHT = 70
RSI_OVERSOLD = 30

SCAN_INTERVAL = 300  # 5 phút

# ====== STATE ======
last_signals = {}
last_scan_time = 0
last_report_time = {"11": None, "14": None}
update_id = None
running = True

# ====== TELEGRAM ======
def send_telegram(msg):
    try:
        url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
        requests.post(url, data={"chat_id": CHAT_ID, "text": msg})
    except Exception as e:
        print("Telegram error:", e)

def get_updates(offset=None):
    try:
        url = f"https://api.telegram.org/bot{TOKEN}/getUpdates"
        params = {"timeout": 10, "offset": offset}
        res = requests.get(url, params=params)
        return res.json()
    except:
        return {"result": []}

# ====== INDICATORS ======
def compute_rsi(series, period=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

# ====== SIGNAL ======
def get_signal(symbol):
    try:
        data = yf.download(symbol, period="3mo", interval="1d", progress=False)

        if isinstance(data.columns, pd.MultiIndex):
            data.columns = data.columns.droplevel(1)

        data['MA20'] = data['Close'].rolling(20).mean()
        data['MA50'] = data['Close'].rolling(50).mean()
        data['RSI'] = compute_rsi(data['Close'], RSI_PERIOD)

        data = data.dropna()
        if len(data) < 2:
            return None, None, None

        prev = data.iloc[-2]
        curr = data.iloc[-1]

        signal = None
        rsi_signal = None

        if prev['MA20'] < prev['MA50'] and curr['MA20'] > curr['MA50']:
            signal = "BUY"
        elif prev['MA20'] > prev['MA50'] and curr['MA20'] < curr['MA50']:
            signal = "SELL"

        if curr['MA20'] > curr['MA50'] and curr['RSI'] < RSI_OVERBOUGHT:
            rsi_signal = "BUY_RSI"
        elif curr['MA20'] < curr['MA50'] and curr['RSI'] > RSI_OVERSOLD:
            rsi_signal = "SELL_RSI"

        return signal, rsi_signal, curr

    except Exception as e:
        print("Data error:", e)
        return None, None, None

# ====== COMMAND ======
def handle_command(text):
    global running

    if text == "/start":
        send_telegram("🤖 Bot ONLINE")

    elif text == "/status":
        send_telegram("🟢 RUNNING" if running else "🔴 STOPPED")

    elif text == "/run":
        running = True
        send_telegram("🚀 Started")

    elif text == "/stop":
        running = False
        send_telegram("⛔ Stopped")

    elif text == "/price":
        msg = "📊 PRICE:\n"
        for sym in SYMBOLS:
            _, _, data = get_signal(sym)
            if data is not None:
                msg += f"{sym}: {round(data['Close'],2)} | RSI {round(data['RSI'],1)}\n"
        send_telegram(msg)

    elif text == "/overview":
        msg = "📊 OVERVIEW:\n"
        for sym in SYMBOLS:
            signal, rsi_signal, data = get_signal(sym)
            if data is not None:
                msg += f"{sym}: {signal or '-'} | RSI {round(data['RSI'],1)}\n"
        send_telegram(msg)

    elif text == "/scan":
        scan_market(send_all=True)

    else:
        send_telegram("❓ Unknown command")

# ====== SCAN ======
def scan_market(send_all=False):
    global last_signals

    messages = []

    for sym in SYMBOLS:
        signal, rsi_signal, data = get_signal(sym)
        if data is None:
            continue

        price = data['Close']
        rsi = data['RSI']

        if signal and last_signals.get(sym) != signal:
            messages.append(f"{sym} | {signal} | {round(price,2)} | RSI {round(rsi,1)}")
            last_signals[sym] = signal

        if rsi_signal and last_signals.get(sym+"_RSI") != rsi_signal:
            messages.append(f"{sym} | {rsi_signal} | RSI {round(rsi,1)}")
            last_signals[sym+"_RSI"] = rsi_signal

        if send_all:
            messages.append(f"{sym}: {round(price,2)} | RSI {round(rsi,1)}")

    if messages:
        send_telegram("\n".join(messages))

# ====== TIME ======
def is_market_open(now):
    return now.weekday() < 5 and 9 <= now.hour < 15

# ====== MAIN ======
def run_bot():
    global update_id, last_scan_time, last_report_time

    send_telegram("🤖 Bot started")

    updates = get_updates()
    if updates["result"]:
        update_id = updates["result"][-1]["update_id"] + 1

    while True:
        try:
            now = datetime.now()

            # ===== TELEGRAM =====
            updates = get_updates(update_id)
            for item in updates["result"]:
                update_id = item["update_id"] + 1
                if "message" in item:
                    text = item["message"].get("text", "")
                    handle_command(text)

            # ===== MARKET LOGIC =====
            if running:
                if is_market_open(now):
                    if time.time() - last_scan_time > SCAN_INTERVAL:
                        scan_market()
                        last_scan_time = time.time()
                else:
                    hour = now.strftime("%H")

                    if hour == "11" and last_report_time["11"] != now.date():
                        scan_market(send_all=True)
                        last_report_time["11"] = now.date()

                    if hour == "14" and last_report_time["14"] != now.date():
                        scan_market(send_all=True)
                        last_report_time["14"] = now.date()

            time.sleep(10)

        except Exception as e:
            print("ERROR:", e)
            time.sleep(60)

# ====== RUN ======
if __name__ == "__main__":
    run_bot()
