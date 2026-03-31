import yfinance as yf
import pandas as pd
import time
import requests
from datetime import datetime
import os
import traceback

# ====== CONFIG ======
SYMBOLS = [
    "HPG.VN","DGC.VN","VIC.VN","NVL.VN","BSR.VN","ACB.VN","VCB.VN","BID.VN",
    "BCM.VN","BVH.VN","CTG.VN","FPT.VN","GAS.VN","GVR.VN","HDB.VN","MBB.VN",
    "MSN.VN","MSH.VN","MWG.VN","PLX.VN","POW.VN","SAB.VN","SHB.VN","TCB.VN",
    "TPB.VN","VHM.VN","VIB.VN","VNM.VN","VRE.VN","PC1.VN","TNG.VN","DCM.VN",
    "DPM.VN","MWG.VN","ANV.VN","PAC.VN","GMD.VN","VGC.VN","PLX.VN","SAB.VN",
    "KBC.VN","DXS.VN","SZC.VN","SSI.VN","VND.VN","HCM.VN","VCI.VN","VIX.VN",
    "REE.VN","GEX.VN","HDG.VN","CII.VN","DIG.VN","NLG.VN","PDR.VN","SCR.VN",
    "CEO.VN","IDC.VN","NT2.VN","PPC.VN","BWE.VN","TDM.VN","FRT.VN","DGW.VN",
    "PET.VN","COM.VN","VSC.VN","HAH.VN","PVT.VN","VIP.VN","CSV.VN","LAS.VN",
    "BMP.VN","NTP.VN","ACL.VN","VHC.VN","IDI.VN","PAN.VN","BAF.VN","DBC.VN",
    "STB.VN","EIB.VN","OCB.VN","LPB.VN","CII.VN"
]

TOKEN = os.getenv("TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

RSI_PERIOD = 14
SCAN_INTERVAL = 900  # 15 phút (giảm tải)

# ====== CACHE ======
cache = {}
cache_time = {}
CACHE_TTL = 600  # 10 phút

# ====== STATE ======
last_signals = {}
last_scan_time = 0
last_report_time = {"11": None, "14": None}
update_id = None
running = True

# ====== DEBUG ======
print("=== BOT STARTING ===")
print("TOKEN:", TOKEN)
print("CHAT_ID:", CHAT_ID)

# ====== TELEGRAM ======
def send_telegram(msg):
    try:
        if not TOKEN or not CHAT_ID:
            print("Missing TOKEN or CHAT_ID")
            return

        url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
        requests.post(url, data={"chat_id": CHAT_ID, "text": msg}, timeout=10)

    except Exception as e:
        print("Telegram error:", e)


def get_updates(offset=None):
    try:
        if not TOKEN:
            return {"result": []}

        url = f"https://api.telegram.org/bot{TOKEN}/getUpdates"
        params = {"timeout": 10, "offset": offset}
        res = requests.get(url, params=params, timeout=15)
        return res.json()

    except Exception as e:
        print("GetUpdates error:", e)
        return {"result": []}


# ====== INDICATORS ======
def compute_rsi(series):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(RSI_PERIOD).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(RSI_PERIOD).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))


# ====== DATA ======
def get_signal(symbol):
    try:
        now = time.time()

        # ===== CACHE =====
        if symbol in cache and now - cache_time[symbol] < CACHE_TTL:
            return cache[symbol]

        # ===== FETCH =====
        data = yf.download(
            symbol,
            period="3mo",
            interval="1d",
            progress=False,
            threads=False
        )

        if data is None or data.empty:
            return None, None

        if isinstance(data.columns, pd.MultiIndex):
            data.columns = data.columns.droplevel(1)

        data['MA20'] = data['Close'].rolling(20).mean()
        data['MA50'] = data['Close'].rolling(50).mean()
        data['RSI'] = compute_rsi(data['Close'])

        data = data.dropna()
        if len(data) < 2:
            return None, None

        prev = data.iloc[-2]
        curr = data.iloc[-1]

        signal = None

        if prev['MA20'] < prev['MA50'] and curr['MA20'] > curr['MA50']:
            signal = "BUY"
        elif prev['MA20'] > prev['MA50'] and curr['MA20'] < curr['MA50']:
            signal = "SELL"

        result = (signal, curr)

        cache[symbol] = result
        cache_time[symbol] = now

        return result

    except Exception as e:
        print("YF ERROR:", e)

        if "rate" in str(e).lower():
            print("Rate limit hit → sleep 60s")
            time.sleep(60)

        return None, None


# ====== FORMAT ======
def format_data(sym, data, signal=None):
    return f"{sym} | {signal or '-'} | {round(data['Close'],2)} | RSI {round(data['RSI'],1)} | MA20 {round(data['MA20'],2)} | MA50 {round(data['MA50'],2)}"


# ====== COMMAND ======
def handle_command(text):
    global running

    print("Command:", text)

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
        msgs = []
        for sym in SYMBOLS:
            _, data = get_signal(sym)
            if data is not None:
                msgs.append(format_data(sym, data))
        send_telegram("\n".join(msgs))

    elif text == "/overview":
        msgs = []
        for sym in SYMBOLS:
            signal, data = get_signal(sym)
            if data is not None:
                msgs.append(format_data(sym, data, signal))
        send_telegram("\n".join(msgs))

    elif text == "/scan":
        scan_market(force=True)

    elif text == "/update":
        send_telegram("🔄 Updating...")
        scan_market(force=True)

    else:
        send_telegram("❓ Unknown command")


# ====== SCAN ======
def scan_market(force=False):
    global last_signals

    msgs = []

    for sym in SYMBOLS:
        time.sleep(1.5)  # chống rate limit

        signal, data = get_signal(sym)
        if data is None:
            continue

        if force:
            msgs.append(format_data(sym, data, signal))
            continue

        if signal and last_signals.get(sym) != signal:
            msgs.append(format_data(sym, data, signal))
            last_signals[sym] = signal

    if msgs:
        send_telegram("\n".join(msgs))


# ====== TIME ======
def is_market_open(now):
    return now.weekday() < 5 and 9 <= now.hour < 15


# ====== MAIN ======
def run_bot():
    global update_id, last_scan_time, last_report_time

    print("=== BOT LOOP STARTED ===")
    send_telegram("🤖 Bot started")

    updates = get_updates()
    if updates["result"]:
        update_id = updates["result"][-1]["update_id"] + 1

    while True:
        try:
            print(f"Loop at {datetime.now()}")

            now = datetime.now()

            # TELEGRAM
            updates = get_updates(update_id)
            for item in updates["result"]:
                update_id = item["update_id"] + 1
                if "message" in item:
                    handle_command(item["message"].get("text", ""))

            # AUTO MODE
            if running:
                if is_market_open(now):
                    if time.time() - last_scan_time > SCAN_INTERVAL:
                        scan_market()
                        last_scan_time = time.time()
                else:
                    hour = now.strftime("%H")

                    if hour == "11" and last_report_time["11"] != now.date():
                        scan_market(force=True)
                        last_report_time["11"] = now.date()

                    if hour == "14" and last_report_time["14"] != now.date():
                        scan_market(force=True)
                        last_report_time["14"] = now.date()

            time.sleep(10)

        except Exception:
            print("CRASH:", traceback.format_exc())
            time.sleep(10)


# ====== RUN ======
if __name__ == "__main__":
    while True:
        try:
            run_bot()
        except Exception:
            print("RESTARTING...", traceback.format_exc())
            time.sleep(5)
