import yfinance as yf
import pandas as pd
import time
import requests
from datetime import datetime

# ====== CONFIG ======
SYMBOLS = ["HPG.VN", "DGC.VN"]   # thêm mã tại đây
INTERVAL = "1d"

# Telegram
TOKEN = "YOUR_NEW_TOKEN"
CHAT_ID = "YOUR_CHAT_ID"

# ====== STATE ======
running = True
last_signals = {}
update_id = None

# ====== TELEGRAM ======
def send_telegram(msg):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    try:
        requests.post(url, data={"chat_id": CHAT_ID, "text": msg})
    except:
        pass

def get_updates(offset=None):
    url = f"https://api.telegram.org/bot{TOKEN}/getUpdates"
    params = {"timeout": 100}
    if offset:
        params["offset"] = offset
    try:
        res = requests.get(url, params=params)
        return res.json()
    except:
        return {}

# ====== RSI ======
def compute_rsi(series, period=14):
    delta = series.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = -delta.clip(upper=0).rolling(period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

# ====== SIGNAL ======
def get_signal(symbol):
    try:
        data = yf.download(symbol, period="3mo", interval=INTERVAL, progress=False)

        if data.empty:
            return None

        if isinstance(data.columns, pd.MultiIndex):
            data.columns = data.columns.droplevel(1)

        data['MA20'] = data['Close'].rolling(20).mean()
        data['MA50'] = data['Close'].rolling(50).mean()
        data['RSI'] = compute_rsi(data['Close'])

        data = data.dropna()

        prev = data.iloc[-2]
        curr = data.iloc[-1]

        signal = None
        rsi_note = None

        # ===== CROSS =====
        if prev['MA20'] < prev['MA50'] and curr['MA20'] > curr['MA50']:
            signal = "BUY"
        elif prev['MA20'] > prev['MA50'] and curr['MA20'] < curr['MA50']:
            signal = "SELL"

        # ===== RSI FILTER =====
        if signal == "BUY" and curr['RSI'] < 70:
            rsi_note = "RSI OK (<70)"
        elif signal == "SELL" and curr['RSI'] > 30:
            rsi_note = "RSI OK (>30)"
        else:
            rsi_note = "RSI WARNING"

        return {
            "symbol": symbol,
            "signal": signal,
            "price": round(curr['Close'], 2),
            "ma20": round(curr['MA20'], 2),
            "ma50": round(curr['MA50'], 2),
            "rsi": round(curr['RSI'], 2),
            "rsi_note": rsi_note
        }

    except Exception as e:
        print("Error:", symbol, e)
        return None

# ====== COMMAND HANDLER ======
def handle_command(text):
    global running

    if text == "/start":
        send_telegram("🤖 Bot online")

    elif text == "/status":
        status = "🟢 RUNNING" if running else "🔴 STOPPED"
        send_telegram(f"Status: {status}")

    elif text == "/run":
        running = True
        send_telegram("🚀 Bot started")

    elif text == "/stop":
        running = False
        send_telegram("⛔ Bot stopped")

    elif text == "/price":
        msg = "📊 MARKET SNAPSHOT\n\n"

        for symbol in SYMBOLS:
            result = get_signal(symbol)
            if result:
                msg += f"{symbol}\n"
                msg += f"Price: {result['price']}\n"
                msg += f"MA20: {result['ma20']} | MA50: {result['ma50']}\n"
                msg += f"RSI: {result['rsi']}\n\n"

        send_telegram(msg)

    elif text == "/list":
        send_telegram(f"📌 Symbols: {', '.join(SYMBOLS)}")

    else:
        send_telegram("❓ Unknown command")

# ====== MAIN LOOP ======
def run_bot():
    global update_id, last_signals

    send_telegram("🤖 Bot started")

    while True:
        try:
            # ===== READ TELEGRAM =====
            updates = get_updates(update_id)

            for item in updates.get("result", []):
                update_id = item["update_id"] + 1

                if "message" not in item:
                    continue

                message = item["message"]

                if "text" not in message:
                    continue

                text = message["text"].strip()
                print("CMD:", text)

                handle_command(text)

            # ===== SIGNAL SCAN =====
            if running:
                now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                for symbol in SYMBOLS:
                    result = get_signal(symbol)

                    if not result or not result["signal"]:
                        continue

                    prev_signal = last_signals.get(symbol)

                    if result["signal"] != prev_signal:
                        msg = f"""
📊 {symbol}
⏰ {now}

🔥 SIGNAL: {result['signal']}
💰 Price: {result['price']}

MA20: {result['ma20']}
MA50: {result['ma50']}
RSI: {result['rsi']}
"""
                        send_telegram(msg)

                        # ===== RSI MESSAGE =====
                        send_telegram(f"{symbol} → {result['rsi_note']}")

                        last_signals[symbol] = result["signal"]

            time.sleep(10)

        except Exception as e:
            print("MAIN ERROR:", e)
            time.sleep(10)

# ====== RUN ======
if __name__ == "__main__":
    run_bot()
