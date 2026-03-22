import yfinance as yf
import pandas as pd
import time
import requests
from datetime import datetime
import os

# ====== CONFIG ======
SYMBOLS = ["HPG.VN", "DGC.VN","VIC.VN","NVL.VN","BSR.VN","ACB.VN","VCB.VN","BID.VN","BCM.VN","BVH.VN","CTG.VN","FPT.VN","GAS.VN","GVR.VN","HDB.VN","MBB.VN","MSN.VN","MSH.VN","MWG.VN","PLX.VN","POW.VN","SAB.VN","SHB.VN","TCB.VN","TPB.VN","VHM.VN","VIB.VN","VNM.VN","VRE.VN"]
INTERVAL = "1d"

TOKEN = os.getenv("TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

RSI_PERIOD = 14
RSI_OVERBOUGHT = 70
RSI_OVERSOLD = 30

SCAN_INTERVAL = 300  # 5 minutes

# ====== STATE ======
last_signals = {}
last_scan_time = 0
last_report_time = {"11": None, "14": None}

# ====== TELEGRAM ======
def send_telegram(msg):
    try:
        url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
        requests.post(url, data={"chat_id": CHAT_ID, "text": msg})
    except Exception as e:
        print("Telegram error:", e)

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
        data = yf.download(symbol, period="3mo", interval=INTERVAL, progress=False)

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

        # MA crossover
        if prev['MA20'] < prev['MA50'] and curr['MA20'] > curr['MA50']:
            signal = "BUY"
        elif prev['MA20'] > prev['MA50'] and curr['MA20'] < curr['MA50']:
            signal = "SELL"

        # RSI filter
        if curr['MA20'] > curr['MA50'] and curr['RSI'] < RSI_OVERBOUGHT:
            rsi_signal = "BUY_RSI"
        elif curr['MA20'] < curr['MA50'] and curr['RSI'] > RSI_OVERSOLD:
            rsi_signal = "SELL_RSI"

        return signal, rsi_signal, curr

    except Exception as e:
        print("Data error:", e)
        return None, None, None

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
        now = datetime.now().strftime("%Y-%m-%d %H:%M")

        # ===== SIGNAL ONLY =====
        if signal and last_signals.get(sym) != signal:
            msg = f"{sym} | {signal} | {round(price,2)} | RSI {round(rsi,1)}"
            messages.append(msg)
            last_signals[sym] = signal

        if rsi_signal and last_signals.get(sym+"_RSI") != rsi_signal:
            msg = f"{sym} | {rsi_signal} | RSI {round(rsi,1)}"
            messages.append(msg)
            last_signals[sym+"_RSI"] = rsi_signal

        # ===== FORCE REPORT (off-market) =====
        if send_all:
            msg = f"{sym}: {round(price,2)} | RSI {round(rsi,1)}"
            messages.append(msg)

    if messages:
        send_telegram("\n".join(messages))

# ====== TIME CHECK ======
def is_market_open(now):
    return now.weekday() < 5 and 9 <= now.hour < 15

# ====== MAIN LOOP ======
def run_bot():
    global last_scan_time, last_report_time

    send_telegram("🤖 Bot started")

    while True:
        try:
            now = datetime.now()

            # ===== MARKET HOURS =====
            if is_market_open(now):
                if time.time() - last_scan_time > SCAN_INTERVAL:
                    print("Scanning market...")
                    scan_market(send_all=False)
                    last_scan_time = time.time()

            # ===== OFF MARKET REPORT =====
            else:
                hour = now.strftime("%H")

                # 11h report
                if hour == "11" and last_report_time["11"] != now.date():
                    print("11h report")
                    scan_market(send_all=True)
                    last_report_time["11"] = now.date()

                # 14h report
                if hour == "14" and last_report_time["14"] != now.date():
                    print("14h report")
                    scan_market(send_all=True)
                    last_report_time["14"] = now.date()

            # ===== SLEEP CONTROL =====
            time.sleep(10)

        except Exception as e:
            print("ERROR:", e)
            time.sleep(60)

# ====== RUN ======
if __name__ == "__main__":
    run_bot()
