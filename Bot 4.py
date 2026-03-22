import yfinance as yf
import pandas as pd
import time
import requests
from datetime import datetime
import os

# ====== CONFIG ======
SYMBOLS = ["HPG.VN", "DGC.VN"]   # thêm mã tại đây
INTERVAL = "1d"

# Telegram (set trong Render ENV)
TOKEN = os.getenv("TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

# Trading params
RSI_PERIOD = 14
RSI_OVERBOUGHT = 70
RSI_OVERSOLD = 30

# ====== STATE ======
running = True
last_signals = {}
update_id = None

# ====== TELEGRAM ======
def send_telegram(msg):
    try:
        url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
        requests.post(url, data={"chat_id": CHAT_ID, "text": msg})
    except:
        print("Telegram send error")

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
        data = yf.download(symbol, period="3mo", interval=INTERVAL)

        if isinstance(data.columns, pd.MultiIndex):
            data.columns = data.columns.droplevel(1)

        data['MA20'] = data['Close'].rolling(20).mean()
        data['MA50'] = data['Close'].rolling(50).mean()
        data['RSI'] = compute_rsi(data['Close'], RSI_PERIOD)

        data = data.dropna()

        prev = data.iloc[-2]
        curr = data.iloc[-1]

        signal = None
        rsi_signal = None

        # MA crossover
        if prev['MA20'] < prev['MA50'] and curr['MA20'] > curr['MA50']:
            signal = "BUY"

        elif prev['MA20'] > prev['MA50'] and curr['MA20'] < curr['MA50']:
            signal = "SELL"

        # RSI filter riêng
        if curr['MA20'] > curr['MA50'] and curr['RSI'] < RSI_OVERBOUGHT:
            rsi_signal = "BUY_RSI"

        elif curr['MA20'] < curr['MA50'] and curr['RSI'] > RSI_OVERSOLD:
            rsi_signal = "SELL_RSI"

        return signal, rsi_signal, curr

    except Exception as e:
        print("Error:", e)
        return None, None, None

# ====== COMMAND HANDLER ======
def handle_command(text):
    global running

    if text == "/start":
        send_telegram("🤖 Bot ONLINE")

    elif text == "/help":
        send_telegram("""
📌 COMMAND LIST:
/start - start bot
/status - trạng thái
/run - chạy bot
/stop - dừng bot
/price - xem giá tất cả mã
/scan - scan ngay lập tức
""")

    elif text == "/status":
        status = "🟢 RUNNING" if running else "🔴 STOPPED"
        send_telegram(status)

    elif text == "/run":
        running = True
        send_telegram("🚀 Bot started")

    elif text == "/stop":
        running = False
        send_telegram("⛔ Bot stopped")

    elif text == "/price":
        msg = "📊 PRICE CHECK:\n"
        for sym in SYMBOLS:
            _, _, data = get_signal(sym)
            if data is not None:
                msg += f"{sym}: {round(data['Close'],2)} | RSI {round(data['RSI'],1)}\n"
        send_telegram(msg)

    elif text == "/scan":
        scan_market()

    else:
        send_telegram("❓ Unknown command")

# ====== SCAN FUNCTION ======
def scan_market():
    global last_signals

    for sym in SYMBOLS:
        signal, rsi_signal, data = get_signal(sym)

        if data is None:
            continue

        price = data['Close']
        ma20 = data['MA20']
        ma50 = data['MA50']
        rsi = data['RSI']
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # MA signal
        if signal and last_signals.get(sym) != signal:
            msg = f"""
📊 {sym}
⏰ {now}

🔥 SIGNAL: {signal}
💰 Price: {round(price,2)}

MA20: {round(ma20,2)}
MA50: {round(ma50,2)}
RSI: {round(rsi,1)}
"""
            send_telegram(msg)
            last_signals[sym] = signal

        # RSI signal riêng
        if rsi_signal:
            msg = f"""
📊 {sym}

⚡ RSI FILTER SIGNAL: {rsi_signal}
RSI: {round(rsi,1)}
"""
            send_telegram(msg)

# ====== MAIN LOOP ======
def run_bot():
    global update_id

    send_telegram("🤖 Bot started (Render)")

    # init update_id tránh spam cũ
    updates = get_updates()
    if updates["result"]:
        update_id = updates["result"][-1]["update_id"] + 1

    while True:
        try:
            # ===== đọc Telegram =====
            updates = get_updates(update_id)

            for item in updates["result"]:
                update_id = item["update_id"] + 1

                if "message" in item:
                    text = item["message"].get("text", "")
                    print("Command:", text)
                    handle_command(text)

            # ===== chạy scan =====
            if running:
                scan_market()

            now = datetime.now()

# giờ giao dịch: 9h - 15h
if 9 <= now.hour < 15:
    sleep_time = 180   # 3 phút
else:
    sleep_time = 1800  # 30 phút

time.sleep(sleep_time)

        except Exception as e:
            print("MAIN LOOP ERROR:", e)
            time.sleep(1800)

# ====== RUN ======
if __name__ == "__main__":
    run_bot()
