import yfinance as yf
import pandas as pd
import time
import requests
from datetime import datetime

# ===== CONFIG =====
SYMBOLS = ["HPG.VN", "DGC.VN", "FPT.VN","BSR.VN","PVD.VN","PVT.VN","VIC.VN"]
INTERVAL = "1d"

TOKEN = "8749505514:AAFvhujZ-MI1K4TFD6PrqlNGLIcIC0hU5xU"
CHAT_ID = "1356499572"

# RSI
RSI_PERIOD = 14
RSI_OVERBOUGHT = 70
RSI_OVERSOLD = 30

# ===== STATE =====
running = True
update_id = None
last_signal = {}
last_rsi_signal = {}
data_cache = {}
last_update_time = 0

# ===== TELEGRAM =====
def send_telegram(msg):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    requests.post(url, data={"chat_id": CHAT_ID, "text": msg})

def get_updates(offset=None):
    url = f"https://api.telegram.org/bot{TOKEN}/getUpdates"
    params = {"timeout": 10, "offset": offset}
    return requests.get(url, params=params).json()

# ===== RSI =====
def compute_rsi(series, period=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

# ===== DATA =====
def fetch_data(symbol):
    try:
        data = yf.download(symbol, period="3mo", interval=INTERVAL, progress=False)

        if isinstance(data.columns, pd.MultiIndex):
            data.columns = data.columns.droplevel(1)

        data['MA20'] = data['Close'].rolling(20).mean()
        data['MA50'] = data['Close'].rolling(50).mean()
        data['RSI'] = compute_rsi(data['Close'], RSI_PERIOD)

        data = data.dropna()

        if len(data) > 0:
            data_cache[symbol] = data

    except:
        pass

def update_all_data():
    global last_update_time
    for symbol in SYMBOLS:
        fetch_data(symbol)
        time.sleep(1)
    last_update_time = time.time()

# ===== SIGNAL =====
def get_signal(symbol):
    data = data_cache.get(symbol)

    if data is None or len(data) < 2:
        return None, None, None, None, None, None

    prev = data.iloc[-2]
    curr = data.iloc[-1]

    signal = None
    rsi_signal = None

    # MA CROSS
    if prev['MA20'] < prev['MA50'] and curr['MA20'] > curr['MA50']:
        signal = "BUY"
    elif prev['MA20'] > prev['MA50'] and curr['MA20'] < curr['MA50']:
        signal = "SELL"

    # RSI FILTER
    if curr['MA20'] > curr['MA50'] and curr['RSI'] < RSI_OVERBOUGHT:
        rsi_signal = "BUY (RSI OK)"
    elif curr['MA20'] < curr['MA50'] and curr['RSI'] > RSI_OVERSOLD:
        rsi_signal = "SELL (RSI OK)"

    return signal, rsi_signal, curr['Close'], curr['MA20'], curr['MA50'], curr['RSI']

# ===== COMMAND =====
def handle_command(text):
    global running

    parts = text.split()

    # START
    if text == "/start":
        send_telegram("🤖 Bot online")

    # STATUS
    elif text == "/status":
        send_telegram(f"Status: {'🟢 RUNNING' if running else '🔴 STOPPED'}")

    # RUN / STOP
    elif text == "/run":
        running = True
        send_telegram("🚀 Bot started")

    elif text == "/stop":
        running = False
        send_telegram("⛔ Bot stopped")

    # FORCE UPDATE
    elif text == "/update":
        send_telegram("🔄 Updating data...")
        update_all_data()
        send_telegram("✅ Update done")

    # PRICE ALL
    elif text == "/price":
        msg = "📊 PRICE LIST\n\n"

        for symbol in SYMBOLS:
            _, _, price, ma20, ma50, rsi = get_signal(symbol)

            if price:
                msg += f"{symbol}\n"
                msg += f"Price: {round(price,2)}\n"
                msg += f"MA20: {round(ma20,2)} | MA50: {round(ma50,2)}\n"
                msg += f"RSI: {round(rsi,2)}\n\n"
            else:
                msg += f"{symbol}: no data\n\n"

        send_telegram(msg)

    # PRICE 1 STOCK
    elif parts[0] == "/price" and len(parts) == 2:
        symbol = parts[1]

        _, _, price, ma20, ma50, rsi = get_signal(symbol)

        if price:
            send_telegram(f"""
📊 {symbol}

💰 Price: {round(price,2)}
MA20: {round(ma20,2)}
MA50: {round(ma50,2)}
RSI: {round(rsi,2)}
""")
        else:
            send_telegram("❌ No data")

    # SCAN
    elif text == "/scan":
        msg = "🔍 SCAN RESULT\n\n"
        found = False

        for symbol in SYMBOLS:
            signal, rsi_signal, *_ = get_signal(symbol)

            if signal:
                msg += f"{symbol}: {signal}\n"
                found = True

            if rsi_signal:
                msg += f"{symbol}: {rsi_signal}\n"
                found = True

        if not found:
            msg += "No signal"

        send_telegram(msg)

    # OVERVIEW (QUAN TRỌNG)
    elif text == "/overview":
        msg = "📊 MARKET OVERVIEW\n\n"

        for symbol in SYMBOLS:
            signal, rsi_signal, price, ma20, ma50, rsi = get_signal(symbol)

            if price:
                trend = "UP" if ma20 > ma50 else "DOWN"

                msg += f"{symbol}\n"
                msg += f"Price: {round(price,2)}\n"
                msg += f"Trend: {trend}\n"
                msg += f"RSI: {round(rsi,2)}\n"

                if signal:
                    msg += f"Signal: {signal}\n"
                elif rsi_signal:
                    msg += f"RSI Signal: {rsi_signal}\n"

                msg += "\n"

        send_telegram(msg)

    else:
        send_telegram("❓ Unknown command")

# ===== MAIN =====
def run_bot():
    global update_id

    send_telegram("🚀 Bot started (PRO VERSION)")
    update_all_data()

    while True:
        try:
            # TELEGRAM
            updates = get_updates(update_id)

            for item in updates["result"]:
                update_id = item["update_id"] + 1

                if "message" in item:
                    handle_command(item["message"]["text"])

            # AUTO UPDATE mỗi 60s
            if time.time() - last_update_time > 60:
                update_all_data()

            # AUTO SIGNAL
            if running:
                for symbol in SYMBOLS:
                    signal, rsi_signal, price, *_ = get_signal(symbol)

                    if signal and last_signal.get(symbol) != signal:
                        send_telegram(f"🔥 {symbol}: {signal} @ {round(price,2)}")
                        last_signal[symbol] = signal

                    if rsi_signal and last_rsi_signal.get(symbol) != rsi_signal:
                        send_telegram(f"➡️ {symbol}: {rsi_signal}")
                        last_rsi_signal[symbol] = rsi_signal

                    time.sleep(1)

            time.sleep(5)

        except Exception as e:
            print("Error:", e)
            time.sleep(5)

# ===== RUN =====
if __name__ == "__main__":
    run_bot()