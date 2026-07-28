import yfinance as yf
import pandas as pd
import requests
import os
import time
import random
import csv
import sys
import logging
import concurrent.futures
from pathlib import Path

# --- ELITE LOGGING SETUP ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler("engine_execution.log"),
        logging.StreamHandler(sys.stdout)
    ]
)

# --- CONFIGURATION & PARAMETERS ---
WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK")
SCAN_MODE = os.getenv("SCAN_MODE", "FULL")
MAX_WORKERS = 10  # Number of concurrent threads for elite speed

HL_FEE_TOTAL = 13.90          
CAPITAL_PER_TRADE = 300.0     
MAX_ALLOWABLE_CASH_RISK = 15.0 
MIN_DAILY_TURNOVER = 15000.0  
MIN_MARKET_CAP = 3000000.0    
MIN_VOLUME_MULTIPLIER = 2.2   
ESTIMATED_SPREAD_DRAG = 0.025 
MIN_RISK_REWARD_RATIO = 2.0   

def get_dynamic_aim_universe():
    logging.info("Drawing live market universe via TradingView API...")
    aim_tickers = []
    try:
        url = "https://scanner.tradingview.com/uk/scan"
        payload = {
            "columns": ["name"],
            "filter": [{"left": "exchange", "operation": "equal", "right": "LSE"}]
        }
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        for row in data.get("data", []):
            ticker = row["d"][0]
            if "." not in ticker: 
                aim_tickers.append(f"{ticker}.L")
                
        logging.info(f"Successfully drew {len(aim_tickers)} live securities.")
        return list(set(aim_tickers))
        
    except Exception as e:
        logging.critical(f"Failed to draw live registry via API ({e}). Aborting run.")
        sys.exit(1)

def check_market_regime():
    try:
        market = yf.Ticker("^AXX")
        df = market.history(period="3mo")
        if not df.empty and len(df) >= 50:
            sma_50 = df['Close'].rolling(window=50).mean().iloc[-1]
            current_val = df['Close'].iloc[-1]
            return current_val >= sma_50
    except Exception as e:
        logging.warning(f"Market regime check failed ({e}). Defaulting to Bullish.")
    return True

def log_signal_to_csv(ticker, signal_type, current_price, rsi_val, volume_ratio):
    file_path = Path("trade_history.csv")
    file_exists = file_path.is_file()
    
    with open(file_path, mode="a", newline="") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(["Timestamp", "Ticker", "Signal", "Price", "RSI", "Volume_Ratio"])
        
        writer.writerow([pd.Timestamp.utcnow().isoformat(), ticker, signal_type, current_price, rsi_val, volume_ratio])

def send_discord_embed(ticker, signal_type, current_price, true_break_even, stop_loss, trailing_stop_target, rr_ratio, volume_ratio, turnover, recommended_shares, rsi_val, color):
    if not WEBHOOK_URL:
        return
        
    yahoo_url = f"https://finance.yahoo.com/quote/{ticker}"
    
    embed = {
        "title": f"🛡️⚖️ {signal_type} ({SCAN_MODE}): {ticker}",
        "url": yahoo_url,
        "color": color,
        "description": f"V23 Elite setup for **{ticker}** executed via asynchronous loop.",
        "fields": [
            {"name": "💵 Current Price", "value": f"`{current_price:.2f}p`", "inline": True},
            {"name": "🛡️ True Break-Even", "value": f"`{true_break_even:.2f}p`", "inline": True},
            {"name": "🛑 Initial Stop", "value": f"`{stop_loss:.2f}p`", "inline": True},
            {"name": "📈 Trailing Target", "value": f"`{trailing_stop_target:.2f}p`", "inline": True},
            {"name": "⚡ RSI (14)", "value": f"`{rsi_val:.1f}`", "inline": True},
            {"name": "⚖️ R:R Ratio", "value": f"`1:{rr_ratio:.1f}`", "inline": True},
            {"name": "📊 Volume Surge", "value": f"`{volume_ratio:.1f}x`", "inline": True},
            {"name": "💷 Daily Turnover", "value": f"`£{turnover:,.0f}`", "inline": True},
            {"name": "📦 Sized Risk (£15)", "value": f"`{recommended_shares} shares`", "inline": True}
        ],
        "footer": {"text": f"AIM Engine V23 • Multi-Threaded Elite Edition"},
        "timestamp": pd.Timestamp.utcnow().isoformat()
    }
    try:
        requests.post(WEBHOOK_URL, json={"embeds": [embed]}, timeout=5)
    except Exception as e:
        logging.error(f"Discord webhook failed for {ticker}: {e}")

def send_enhanced_summary_digest(scanned_count, buoys_found, watch_found, regime_status, top_volume_ticker, top_volume_val, avg_rsi, lowest_caps, lowest_shares):
    if not WEBHOOK_URL:
        return
        
    status_text = "🟢 Bullish (Healthy Trend)" if regime_status else "🔴 Defensive (Bearish Trend)"
    top_vol_text = f"`{top_volume_ticker}` ({top_volume_val:.1f}x avg)" if top_volume_ticker else "`N/A (Filtered)`"
    avg_rsi_text = f"`{avg_rsi:.1f}`" if avg_rsi else "`N/A`"

    caps_lines = [f"`{rank:2d}.` **{t}** — £{cap:,.0f}" for rank, (t, cap) in enumerate(lowest_caps, 1)]
    caps_text = "\n".join(caps_lines) if caps_lines else "`No data collected`"

    shares_lines = [f"`{rank:2d}.` **{t}** — {int(shs):,} shares" for rank, (t, shs) in enumerate(lowest_shares, 1)]
    shares_text = "\n".join(shares_lines) if shares_lines else "`No data collected`"
    
    embed = {
        "title": f"📊 End-of-Day Elite V23 Detailed Digest",
        "color": 3447003,
        "description": f"Comprehensive asynchronous session audit completed.",
        "fields": [
            {"name": "🔍 Total Scanned", "value": f"`{scanned_count}`", "inline": True},
            {"name": "🌐 Market Regime", "value": f"`{status_text}`", "inline": True},
            {"name": "📈 Universe Avg RSI", "value": avg_rsi_text, "inline": True},
            {"name": "🚀 Top Volume Leader", "value": top_vol_text, "inline": True},
            {"name": "🚨 Strong Buys Flagged", "value": f"`{buoys_found}`", "inline": True},
            {"name": "⭐ Watchlist Setups", "value": f"`{watch_found}`", "inline": True},
            {"name": "📉 Top 10 Lowest Market Caps", "value": caps_text, "inline": False},
            {"name": "📊 Top 10 Lowest Shares in Issue", "value": shares_text, "inline": False}
        ],
        "footer": {"text": f"AIM Engine V23 • Market Structure Tables Complete"},
        "timestamp": pd.Timestamp.utcnow().isoformat()
    }
    try:
        requests.post(WEBHOOK_URL, json={"embeds": [embed]}, timeout=5)
    except Exception as e:
        logging.error(f"Discord summary webhook failed: {e}")

def analyze_stock(ticker):
    metrics = {}
    try:
        stock = yf.Ticker(ticker)
        info = stock.info or {}
        market_cap = info.get('marketCap', 0) or 0
        shares_outstanding = info.get('sharesOutstanding', 0) or 0

        df = stock.history(period="6mo")
        if df.empty or len(df) < 50:
            return None, metrics, ticker

        current_price = df['Close'].iloc[-1]
        
        if not shares_outstanding and market_cap > 0 and current_price > 0:
            shares_outstanding = market_cap / (current_price / 100.0)

        metrics = {"market_cap": market_cap, "shares_outstanding": shares_outstanding}

        # Vectorized calculations for speed
        df['SMA_20'] = df['Close'].rolling(window=20).mean()
        df['SMA_50'] = df['Close'].rolling(window=50).mean()
        df['Vol_20'] = df['Volume'].rolling(window=20).mean()
        
        df['High_Low'] = df['High'] - df['Low']
        df['High_Close'] = abs(df['High'] - df['Close'].shift())
        df['Low_Close'] = abs(df['Low'] - df['Close'].shift())
        df['TR'] = df[['High_Low', 'High_Close', 'Low_Close']].max(axis=1)
        df['ATR_14'] = df['TR'].rolling(window=14).mean()
        
        # Elite Metric: Approximation of VWAP for recent trend
        df['Typical_Price'] = (df['High'] + df['Low'] + df['Close']) / 3
        df['VWAP_14'] = (df['Typical_Price'] * df['Volume']).rolling(window=14).sum() / df['Volume'].rolling(window=14).sum()

        delta = df['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        df['RSI_14'] = 100 - (100 / (1 + rs))

        today = df.iloc[-1]
        yesterday = df.iloc[-2]
        
        if current_price <= 0 or pd.isna(today['ATR_14']) or pd.isna(today['RSI_14']):
            return None, metrics, ticker

        metrics["rsi"] = today['RSI_14']
        avg_volume = yesterday['Vol_20'] if (yesterday['Vol_20'] and yesterday['Vol_20'] > 0) else 1
        volume_ratio = today['Volume'] / avg_volume
        metrics["volume_ratio"] = volume_ratio

        if market_cap and market_cap < MIN_MARKET_CAP:
            return None, metrics, ticker

        daily_turnover = (today['Volume'] * current_price) / 100
        if daily_turnover < MIN_DAILY_TURNOVER:
            return None, metrics, ticker

        raw_shares = CAPITAL_PER_TRADE / (current_price / 100)
        fee_per_share_impact = (HL_FEE_TOTAL / raw_shares) * 100
        true_break_even_price = current_price + fee_per_share_impact + (current_price * ESTIMATED_SPREAD_DRAG)
        
        stop_loss = current_price - (today['ATR_14'] * 1.5)
        risk_distance_pence = current_price - stop_loss
        trailing_stop_target = true_break_even_price + (today['ATR_14'] * 2.5)
        
        if risk_distance_pence <= 0:
            return None, metrics, ticker
            
        rr_ratio = (trailing_stop_target - current_price) / risk_distance_pence
        risk_per_share_gbp = risk_distance_pence / 100.0
        recommended_shares = max(1, int(MAX_ALLOWABLE_CASH_RISK / risk_per_share_gbp) if risk_per_share_gbp > 0 else 0)

        df_weekly = df.resample('W').agg({'Close': 'last'})
        df_weekly['EMA_10'] = df_weekly['Close'].ewm(span=10, adjust=False).mean()
        weekly_trend_ok = len(df_weekly) >= 10 and df_weekly['Close'].iloc[-1] >= df_weekly['EMA_10'].iloc[-1]

        # Institutional checks
        is_golden_cross = (yesterday['SMA_20'] <= yesterday['SMA_50']) and (today['SMA_20'] > today['SMA_50'])
        is_above_trend = current_price > today['SMA_20']
        is_above_vwap = current_price > today['VWAP_14'] # Elite Filter
        rsi_healthy = 55.0 <= today['RSI_14'] <= 75.0

        if is_golden_cross and is_above_trend and is_above_vwap and weekly_trend_ok and rsi_healthy and volume_ratio >= MIN_VOLUME_MULTIPLIER and rr_ratio >= MIN_RISK_REWARD_RATIO:
            return ("BUY", current_price, true_break_even_price, stop_loss, trailing_stop_target, rr_ratio, volume_ratio, daily_turnover, recommended_shares, today['RSI_14']), metrics, ticker
            
        elif SCAN_MODE == "FULL":
            distance_to_ma = abs(current_price - today['SMA_50']) / today['SMA_50']
            if distance_to_ma <= 0.008 and is_above_vwap and weekly_trend_ok and rsi_healthy and rr_ratio >= MIN_RISK_REWARD_RATIO:
                return ("WATCH", current_price, true_break_even_price, stop_loss, trailing_stop_target, rr_ratio, volume_ratio, daily_turnover, recommended_shares, today['RSI_14']), metrics, ticker

    except Exception:
        pass
        
    # Introduce tiny random jitter to prevent YFinance from blocking concurrent requests
    time.sleep(random.uniform(0.1, 0.4)) 
    return None, metrics, ticker

if __name__ == "__main__":
    tickers = get_dynamic_aim_universe()
    market_is_healthy = check_market_regime()
    logging.info(f"Executing V23 Elite audit in [{SCAN_MODE}] mode across {len(tickers)} symbols...")

    buoys_found = 0
    watch_found = 0
    scanned_successfully = 0
    rsi_accumulator = []
    highest_vol_ratio = 0.0
    top_vol_ticker = None
    all_market_caps = []
    all_shares_data = []

    # Elite Multi-Threading Execution Block
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(analyze_stock, ticker): ticker for ticker in tickers}
        
        for future in concurrent.futures.as_completed(futures):
            result, metrics, ticker = future.result()
            
            if metrics:
                if metrics.get("rsi"):
                    scanned_successfully += 1
                    rsi_accumulator.append(metrics["rsi"])
                    
                    if metrics.get("volume_ratio", 0) > highest_vol_ratio:
                        highest_vol_ratio = metrics["volume_ratio"]
                        top_vol_ticker = ticker
                    
                if metrics.get("market_cap", 0) > 0:
                    all_market_caps.append((ticker, metrics["market_cap"]))
                    
                if metrics.get("shares_outstanding", 0) > 0:
                    all_shares_data.append((ticker, metrics["shares_outstanding"]))

            if result:
                sig_type, cur_p, t_be, s_l, t_t, rr, v_rat, turnover, rec_shares, rsi_v = result
                log_signal_to_csv(ticker, sig_type, cur_p, rsi_v, v_rat)
                logging.info(f"Signal Generated: {sig_type} for {ticker}")
                
                if sig_type == "BUY":
                    buoys_found += 1
                    if market_is_healthy:
                        send_discord_embed(ticker, "STRONG BUY", cur_p, t_be, s_l, t_t, rr, v_rat, turnover, rec_shares, rsi_v, 3066993)
                elif sig_type == "WATCH":
                    watch_found += 1
                    send_discord_embed(ticker, "WATCHLIST", cur_p, t_be, s_l, t_t, rr, v_rat, turnover, rec_shares, rsi_v, 16776960)

    if SCAN_MODE == "FULL":
        avg_rsi = sum(rsi_accumulator) / len(rsi_accumulator) if rsi_accumulator else 0.0
        if not top_vol_ticker and rsi_accumulator:
            top_vol_ticker = "N/A (Filtered)"
            highest_vol_ratio = 0.0
            
        all_market_caps.sort(key=lambda x: x[1])
        all_shares_data.sort(key=lambda x: x[1])
            
        send_enhanced_summary_digest(scanned_successfully, buoys_found, watch_found, market_is_healthy, top_vol_ticker, highest_vol_ratio, avg_rsi, all_market_caps[:10], all_shares_data[:10])

    logging.info(f"Elite Audit Complete. Successfully analyzed {scanned_successfully} records.")
