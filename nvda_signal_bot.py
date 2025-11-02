


import yfinance as yf
import pandas as pd
import time
import json
import requests
from datetime import datetime
import os
import csv

# === CONFIG ===
TICKER = "NVDA"
INTERVAL = "5m"
LOOKBACK = "1d"
REFRESH_SEC = 60

# === TELEGRAM CONFIG ===
TELEGRAM_TOKEN = "8487160593:AAGGRKMJsilMTUFCLZ_fRZRd-BzQbwMEdUs"
CHAT_ID = "659539122"

# === FILE PATHS ===
STATUS_FILE = os.path.expanduser("~/Desktop/nvda_status.json")
CSV_FILE = os.path.expanduser("~/Desktop/nvda_signals_log.csv")

# === VARIABILI GLOBALI ===
posizione_aperta = None  # None | dict con info trade
storico_segnali = []

# === CREAZIONE CSV ===
if not os.path.exists(CSV_FILE):
    with open(CSV_FILE, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["Timestamp", "Azione", "Tipo", "Prezzo", "VWAP", "RSI"])

print("🚀 Avvio AI Signal Bot su NVDA (VWAP + RSI + STOP/TAKE)")

def send_telegram_message(msg: str):
    if not TELEGRAM_TOKEN or not CHAT_ID:
        return
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, data={"chat_id": CHAT_ID, "text": msg}, timeout=5)
    except Exception as e:
        print("⚠️ Errore Telegram:", e)

def calcola_rsi(df, period=14):
    delta = df["Close"].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(window=period, min_periods=period).mean()
    avg_loss = loss.rolling(window=period, min_periods=period).mean()
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi

def calcola_vwap(df):
    pv = (df["Close"] * df["Volume"]).cumsum()
    vol_cum = df["Volume"].cumsum()
    return pv / vol_cum

while True:
    try:
        df = yf.download(tickers=TICKER, interval=INTERVAL, period=LOOKBACK, progress=False, auto_adjust=False)
        if df.empty or len(df) < 30:
            print("⏳ In attesa di dati sufficienti...")
            time.sleep(REFRESH_SEC)
            continue

        # Indicatori
        df["EMA20"] = df["Close"].ewm(span=20, adjust=False).mean()
        df["EMA50"] = df["Close"].ewm(span=50, adjust=False).mean()
        df["RSI"] = calcola_rsi(df, period=14).fillna(50)
        df["VWAP"] = calcola_vwap(df)
        df["MediaVol10"] = df["Volume"].rolling(10).mean().fillna(method="backfill")

        # Ultimi valori
        close = df["Close"].iloc[-1].item()
        prev_close = df["Close"].iloc[-2].item()
        vol = df["Volume"].iloc[-1].item()
        vol_avg = df["MediaVol10"].iloc[-1].item()
        ema20 = df["EMA20"].iloc[-1].item()
        ema50 = df["EMA50"].iloc[-1].item()
        rsi = df["RSI"].iloc[-1].item()
        vwap = df["VWAP"].iloc[-1].item()

        segnale = None
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # ==========================
        # 📈 ENTRY SIGNALS
        # ==========================
        if posizione_aperta is None:
            # LONG ENTRY
            if (
                close > prev_close * 1.002
                and vol > vol_avg * 1.3
                and ema20 > ema50
                and close > vwap
                and rsi > 55
            ):
                posizione_aperta = {
                    "tipo": "LONG",
                    "prezzo_entrata": close,
                    "stop": close * 0.99,
                    "target": close * 1.02,
                    "timestamp": now,
                }
                msg = f"📈 ENTRATA LONG NVDA @ {close:.2f} | TP {close*1.02:.2f} | SL {close*0.99:.2f}"
                print(msg)
                send_telegram_message(msg)
                storico_segnali.append({"timestamp": now, "azione": "ENTRATA LONG", "prezzo": close})

            # SHORT ENTRY
            elif (
                close < prev_close * 0.998
                and vol > vol_avg * 1.3
                and ema20 < ema50
                and close < vwap
                and rsi < 45
            ):
                posizione_aperta = {
                    "tipo": "SHORT",
                    "prezzo_entrata": close,
                    "stop": close * 1.01,
                    "target": close * 0.98,
                    "timestamp": now,
                }
                msg = f"🔻 ENTRATA SHORT NVDA @ {close:.2f} | TP {close*0.98:.2f} | SL {close*1.01:.2f}"
                print(msg)
                send_telegram_message(msg)
                storico_segnali.append({"timestamp": now, "azione": "ENTRATA SHORT", "prezzo": close})

        # ==========================
        # 💰 EXIT LOGIC
        # ==========================
        elif posizione_aperta is not None:
            tipo = posizione_aperta["tipo"]
            entry = posizione_aperta["prezzo_entrata"]
            stop = posizione_aperta["stop"]
            target = posizione_aperta["target"]

            chiudi = False
            motivo = ""

            if tipo == "LONG":
                if close <= stop:
                    chiudi, motivo = True, "🛑 STOP LOSS"
                elif close >= target:
                    chiudi, motivo = True, "🎯 TAKE PROFIT"

            elif tipo == "SHORT":
                if close >= stop:
                    chiudi, motivo = True, "🛑 STOP LOSS"
                elif close <= target:
                    chiudi, motivo = True, "🎯 TAKE PROFIT"

            if chiudi:
                msg = f"{motivo} {tipo} NVDA @ {close:.2f} (Entrata {entry:.2f})"
                print(msg)
                send_telegram_message(msg)
                storico_segnali.append({"timestamp": now, "azione": motivo, "tipo": tipo, "prezzo": close})
                posizione_aperta = None  # chiudi trade

        # ==========================
        # SALVATAGGIO FILES
        # ==========================
        with open(STATUS_FILE, "w") as f:
            json.dump({
                "posizione_attuale": posizione_aperta,
                "ultimo_prezzo": close,
                "rsi": rsi,
                "vwap": vwap,
                "timestamp": now,
                "storico": storico_segnali[-200:]
            }, f, indent=2)

        with open(CSV_FILE, "a", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([now, "UPDATE", "LONG" if posizione_aperta else "NONE", f"{close:.2f}", f"{vwap:.2f}", f"{rsi:.1f}"])

    except Exception as e:
        print("⚠️ Errore durante l'esecuzione:", e)

    time.sleep(REFRESH_SEC)

