import yfinance as yf
import pandas as pd
import requests
import os
import time
import random
import csv
from pathlib import Path
from pytickersymbols import PyTickerSymbols

# --- CONFIGURATION & PARAMETERS ---
WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK")
SCAN_MODE = os.getenv("SCAN_MODE", "FULL")

HL_FEE_TOTAL = 13.90          
CAPITAL_PER_TRADE = 300.0     
MAX_ALLOWABLE_CASH_RISK = 15.0 
MIN_DAILY_TURNOVER = 15000.0  
MIN_MARKET_CAP = 3000000.0    
MIN_VOLUME_MULTIPLIER = 2.2   
ESTIMATED_SPREAD_DRAG = 0.025 
MIN_RISK_REWARD_RATIO = 2.0   

def get_dynamic_aim_universe():
    print("Fetching dynamic market universe...")
    aim_tickers = []
    try:
        stock_data = PyTickerSymbols()
        uk_stocks = stock_data.get_stocks_by_exchange("LSE")
        for stock in uk_stocks:
            for sym_entry in stock.get('symbols', []):
                symbol_str = str(sym_entry.get('symbol', '')).strip().upper()
                if symbol_str.endswith('.L') and symbol_str not in aim_tickers:
                    aim_tickers.append(symbol_str)
        print(f"Successfully loaded {len(aim_tickers)} dynamic LSE/AIM securities.")
    except Exception as e:
        print(f"Error fetching dynamic registry: {e}. Engaging fallback.")
        aim_tickers = ["BOO.L", "FDEV.L", "JET2.L", "IQE.L", "BUR.L", "ASC.L"]
    return aim_tickers

def check_market_regime():
    try:
        market = yf.Ticker("^AXX")
        df = market.history(period="3mo")
        if not df.empty and len(df) >= 50:
            sma_50 = df['Close'].rolling(window=50).mean().iloc[-1]
            current_val = df['Close'].iloc[-1]
            return current_val >= sma_50
    except Exception:
        pass
    return True

def log_signal_to_csv(ticker, signal_type, current_price, rsi_val, volume_ratio):
    file_path = Path("trade_history.csv")
    file_exists = file_path.is_file()
    
    with open(file_path, mode="a", newline="") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(["Timestamp", "Ticker", "Signal", "Price", "RSI", "Volume_Ratio"])
        
        writer.writerow([
            pd.Timestamp.utcnow().isoformat(),
            ticker,
            signal_type,
            current_price,
            rsi_val,
            volume_ratio
        ])

def send_discord_embed(ticker, signal_type, current_price, true_break_even, stop_loss, trailing_stop_target, rr_ratio, volume_ratio, turnover, recommended_shares, rsi_val, color):
    if not WEBHOOK_URL:
        return
        
    yahoo_url = f"https://finance.yahoo.com/quote/{ticker}"
    
    embed = {
        "title": f"🛡️⚖️ {signal_type} ({SCAN_MODE}): {ticker}",
        "url": yahoo_url,
        "color": color,
        "description": f"Pro-Terminal setup for **{ticker}** executed via high-frequency 15-min loop.",
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
        "footer": {"text": f"AIM Engine V21 • Pro-Terminal Algorithmic Edition"},
        "timestamp": pd.Timestamp.utcnow().isoformat()
    }
    requests.post(WEBHOOK_URL, json={"embeds": [embed]})

def send_enhanced_summary_digest(scanned_count, buoys_found, watch_found, regime_status, top_volume_ticker, top_volume_val, avg_rsi):
    if not WEBHOOK_URL:
        return
        
    status_text = "🟢 Bullish (Healthy Trend)" if regime_status else "🔴 Defensive (Bearish Trend)"
    top_vol_text = f"`{top_volume_ticker}` ({top_volume_val:.1f}x avg)" if top_volume_ticker else "`N/A (Filtered)`"
    avg_rsi_text = f"`{avg_rsi:.1f}`" if avg_rsi else "`N/A`"
    
    embed = {
        "title": f"📊 End-of-Day Pro-Terminal Detailed Digest",
        "color": 3447003,
        "description": f"Comprehensive quantitative session audit completed.",
        "fields": [
            {"name": "🔍 Total Scanned", "value": f"`{scanned_count}`", "inline": True},
            {"name": "🌐 Market Regime", "value": f"`{status_text}`", "inline": True},
            {"name": "📈 Universe Avg RSI", "value": avg_rsi_text, "inline": True},
            {"name": "🚀 Top Volume Leader", "value": top_vol_text, "inline": True},
            {"name": "🚨 Strong Buys Flagged", "value": f"`{buoys_found}`", "inline": True},
            {"name": "⭐ Watchlist Setups", "value": f"`{watch_found}`", "inline": True}
        ],
        "footer": {"text": f"AIM Engine V21 • Enhanced Analytics Complete"},
        "timestamp": pd.Timestamp.utcnow().isoformat()
    }
    requests.post(WEBHOOK_URL, json={"embeds": [embed]})

def analyze_stock(ticker):
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        market_cap = info.get('marketCap', 0)
        if market_cap and market_cap < MIN_MARKET_CAP:
            return None, None

        df = stock.history(period="6mo")
        if df.empty or len(df) < 50:
            return None, None

        df['SMA_20'] = df['Close'].rolling(window=20).mean()
        df['SMA_50'] = df['Close'].rolling(window=50).mean()
        df['Vol_20'] = df['Volume'].rolling(window=20).mean()
        
        df['High_Low'] = df['High'] - df['Low']
        df['High_Close'] = abs(df['High'] - df['Close'].shift())
        df['Low_Close'] = abs(df['Low'] - df['Close'].shift())
        df['TR'] = df[['High_Low', 'High_Close', 'Low_Close']].max(axis=1)
        df['ATR_14'] = df['TR'].rolling(window=14).mean()
        
        delta = df['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        df['RSI_14'] = 100 - (100 / (1 + rs))

        today = df.iloc[-1]
        yesterday = df.iloc[-2]
        current_price = today['Close']
        current_atr = today['ATR_14']
        current_rsi = today['RSI_14']
        
        if current_price <= 0 or pd.isna(current_atr) or pd.isna(current_rsi):
            return None, None

        daily_turnover = (today['Volume'] * current_price) / 100
        if daily_turnover < MIN_DAILY_TURNOVER:
            return None, None

        avg_volume = yesterday['Vol_20'] if (yesterday['Vol_20'] and yesterday['Vol_20'] > 0) else 1
        volume_ratio = today['Volume'] / avg_volume
        
        metrics = {
            "rsi": current_rsi,
            "volume_ratio": volume_ratio
        }

        raw_shares = CAPITAL_PER_TRADE / (current_price / 100)
        fee_per_share_impact = (HL_FEE_TOTAL / raw_shares) * 100
        true_break_even_price = current_price + fee_per_share_impact + (current_price * ESTIMATED_SPREAD_DRAG)
        
        stop_loss = current_price - (current_atr * 1.5)
        risk_distance_pence = current_price - stop_loss
        trailing_stop_target = true_break_even_price + (current_atr * 2.5)
        reward_distance = trailing_stop_target - current_price
        
        if risk_distance_pence <= 0:
            return None, metrics
        rr_ratio = reward_distance / risk_distance_pence

        risk_per_share_gbp = risk_distance_pence / 100.0
        recommended_shares = int(MAX_ALLOWABLE_CASH_RISK / risk_per_share_gbp) if risk_per_share_gbp > 0 else 0
        if recommended_shares < 1:
            recommended_shares = 1

        df_weekly = df.resample('W').agg({'Close': 'last'})
        df_weekly['EMA_10'] = df_weekly['Close'].ewm(span=10, adjust=False).mean()
        weekly_trend_ok = len(df_weekly) >= 10 and df_weekly['Close'].iloc[-1] >= df_weekly['EMA_10'].iloc[-1]

        is_golden_cross = (yesterday['SMA_20'] <= yesterday['SMA_50']) and (today['SMA_20'] > today['SMA_50'])
        is_above_trend = current_price > today['SMA_20']
        rsi_healthy = 55.0 <= current_rsi <= 75.0

        if is_golden_cross and is_above_trend and weekly_trend_ok and rsi_healthy and volume_ratio >= MIN_VOLUME_MULTIPLIER and rr_ratio >= MIN_RISK_REWARD_RATIO:
            return ("BUY", current_price, true_break_even_price, stop_loss, trailing_stop_target, rr_ratio, volume_ratio, daily_turnover, recommended_shares, current_rsi), metrics
            
        elif SCAN_MODE == "FULL":
            distance_to_ma = abs(current_price - today['SMA_50']) / today['SMA_50']
            if distance_to_ma <= 0.008 and weekly_trend_ok and rsi_healthy and rr_ratio >= MIN_RISK_REWARD_RATIO:
                return ("WATCH", current_price, true_break_even_price, stop_loss, trailing_stop_target, rr_ratio, volume_ratio, daily_turnover, recommended_shares, current_rsi), metrics

    except Exception:
        pass
    return None, None

if __name__ == "__main__":
    tickers = get_dynamic_aim_universe()
    market_is_healthy = check_market_regime()
    print(f"Executing V21 Pro-Terminal audit in [{SCAN_MODE}] mode across {len(tickers)} symbols...")

    buoys_found = 0
    watch_found = 0
    scanned_successfully = 0
    rsi_accumulator = []
    highest_vol_ratio = 0.0
    top_vol_ticker = None

    for ticker in tickers:
        result, metrics = analyze_stock(ticker)
        
        if metrics and metrics.get("rsi"):
            scanned_successfully += 1
            rsi_accumulator.append(metrics["rsi"])
            if metrics["volume_ratio"] > highest_vol_ratio:
                highest_vol_ratio = metrics["volume_ratio"]
                top_vol_ticker = ticker

        if result:
            sig_type, cur_p, t_be, s_l, t_t, rr, v_rat, turnover, rec_shares, rsi_v = result
            log_signal_to_csv(ticker, sig_type, cur_p, rsi_v, v_rat)
            
            if sig_type == "BUY":
                buoys_found += 1
                if market_is_healthy:
                    send_discord_embed(ticker, "STRONG BUY", cur_p, t_be, s_l, t_t, rr, v_rat, turnover, rec_shares, rsi_v, 3066993)
            elif sig_type == "WATCH":
                watch_found += 1
                send_discord_embed(ticker, "WATCHLIST", cur_p, t_be, s_l, t_t, rr, v_rat, turnover, rec_shares, rsi_v, 16776960)
                
        time.sleep(random.uniform(0.1, 0.3))
            
    if SCAN_MODE == "FULL":
        avg_rsi = sum(rsi_accumulator) / len(rsi_accumulator) if rsi_accumulator else 0.0
        
        if not top_vol_ticker and rsi_accumulator:
            top_vol_ticker = "N/A (Filtered)"
            highest_vol_ratio = 0.0
            
        send_enhanced_summary_digest(scanned_successfully, buoys_found, watch_found, market_is_healthy, top_vol_ticker, highest_vol_ratio, avg_rsi)

    print(f"Pro-Terminal Detailed Audit Complete for Mode: {SCAN_MODE}")
