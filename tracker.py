import yfinance as yf
import pandas as pd
import requests
import os
import time
import random
from pytickersymbols import PyTickerSymbols

# --- CONFIGURATION & PARAMETERS ---
WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK")
SCAN_MODE = os.getenv("SCAN_MODE", "FULL")

HL_FEE_TOTAL = 13.90          
CAPITAL_PER_TRADE = 300.0     
MIN_DAILY_TURNOVER = 15000.0  
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
    """Checks if the broader AIM market is healthy (Above its 50-day SMA)."""
    try:
        market = yf.Ticker("^AXX")
        df = market.history(period="3mo")
        if not df.empty and len(df) >= 50:
            sma_50 = df['Close'].rolling(window=50).mean().iloc[-1]
            current_val = df['Close'].iloc[-1]
            is_healthy = current_val >= sma_50
            return is_healthy, current_val
    except Exception:
        pass
    return True, 0.0

def send_discord_embed(ticker, signal_type, current_price, true_break_even, stop_loss, target_ceiling, rr_ratio, volume_ratio, turnover, color):
    if not WEBHOOK_URL:
        return
        
    yahoo_url = f"https://finance.yahoo.com/quote/{ticker}"
    
    embed = {
        "title": f"🛡️⚖️ {signal_type} ({SCAN_MODE} SCAN): {ticker}",
        "url": yahoo_url,
        "color": color,
        "description": f"Macro-validated setup for **{ticker}** processed via hourly {SCAN_MODE} mode.",
        "fields": [
            {"name": "💵 Current Price", "value": f"`{current_price:.2f}p`", "inline": True},
            {"name": "🛡️ True Break-Even", "value": f"`{true_break_even:.2f}p`", "inline": True},
            {"name": "🛑 Stop-Loss Level", "value": f"`{stop_loss:.2f}p`", "inline": True},
            {"name": "🎯 Target Ceiling", "value": f"`{target_ceiling:.2f}p`", "inline": True},
            {"name": "⚖️ Risk/Reward Ratio", "value": f"`1:{rr_ratio:.1f}`", "inline": True},
            {"name": "📊 Volume Surge", "value": f"`{volume_ratio:.1f}x avg`", "inline": True},
            {"name": "💷 Daily Turnover", "value": f"`£{turnover:,.0f}`", "inline": True}
        ],
        "footer": {"text": f"AIM Engine V17 • Regime Filter Active"},
        "timestamp": pd.Timestamp.utcnow().isoformat()
    }
    requests.post(WEBHOOK_URL, json={"embeds": [embed]})

def send_summary_digest(scanned_count, buoys_found, watch_found, regime_status):
    if not WEBHOOK_URL:
        return
        
    status_text = "🟢 Bullish (Macro Healthy)" if regime_status else "🔴 Defensive (Macro Bearish)"
    
    embed = {
        "title": f"📊 End-of-Day AIM Market Summary Digest",
        "color": 3447003,
        "description": f"Complete quantitative audit finalized for today's session.",
        "fields": [
            {"name": "🔍 Total Symbols Scanned", "value": f"`{scanned_count}`", "inline": True},
            {"name": "🌐 Market Regime Status", "value": f"`{status_text}`", "inline": True},
            {"name": "🚨 Total Strong Buys Flagged", "value": f"`{buoys_found}`", "inline": True},
            {"name": "⭐ Total Watchlist Setups", "value": f"`{watch_found}`", "inline": True}
        ],
        "footer": {"text": f"AIM Engine V17 • £13.90 Fee & Risk-Managed Model"},
        "timestamp": pd.Timestamp.utcnow().isoformat()
    }
    requests.post(WEBHOOK_URL, json={"embeds": [embed]})

def analyze_stock(ticker):
    try:
        stock = yf.Ticker(ticker)
        df = stock.history(period="6mo")
        
        if df.empty or len(df) < 50:
            return None

        df['SMA_20'] = df['Close'].rolling(window=20).mean()
        df['SMA_50'] = df['Close'].rolling(window=50).mean()
        df['Vol_20'] = df['Volume'].rolling(window=20).mean()
        
        df['High_Low'] = df['High'] - df['Low']
        df['High_Close'] = abs(df['High'] - df['Close'].shift())
        df['Low_Close'] = abs(df['Low'] - df['Close'].shift())
        df['TR'] = df[['High_Low', 'High_Close', 'Low_Close']].max(axis=1)
        df['ATR_14'] = df['TR'].rolling(window=14).mean()
        
        today = df.iloc[-1]
        yesterday = df.iloc[-2]
        current_price = today['Close']
        current_atr = today['ATR_14']
        
        if current_price <= 0 or pd.isna(current_atr):
            return None

        daily_turnover = (today['Volume'] * current_price) / 100
        if daily_turnover < MIN_DAILY_TURNOVER:
            return None

        avg_volume = yesterday['Vol_20'] if (yesterday['Vol_20'] and yesterday['Vol_20'] > 0) else 1
        volume_ratio = today['Volume'] / avg_volume
        
        raw_shares = CAPITAL_PER_TRADE / (current_price / 100)
        fee_per_share_impact = (HL_FEE_TOTAL / raw_shares) * 100
        true_break_even_price = current_price + fee_per_share_impact + (current_price * ESTIMATED_SPREAD_DRAG)
        
        stop_loss = current_price - (current_atr * 1.5)
        risk_distance = current_price - stop_loss
        target_ceiling = true_break_even_price * 1.035
        reward_distance = target_ceiling - current_price
        
        if risk_distance <= 0:
            return None
        rr_ratio = reward_distance / risk_distance

        is_golden_cross = (yesterday['SMA_20'] <= yesterday['SMA_50']) and (today['SMA_20'] > today['SMA_50'])
        is_above_trend = current_price > today['SMA_20']
        
        if is_golden_cross and is_above_trend and volume_ratio >= MIN_VOLUME_MULTIPLIER and rr_ratio >= MIN_RISK_REWARD_RATIO:
            return ("BUY", current_price, true_break_even_price, stop_loss, target_ceiling, rr_ratio, volume_ratio, daily_turnover)
            
        elif SCAN_MODE == "FULL":
            distance_to_ma = abs(current_price - today['SMA_50']) / today['SMA_50']
            if distance_to_ma <= 0.008 and rr_ratio >= MIN_RISK_REWARD_RATIO:
                return ("WATCH", current_price, true_break_even_price, stop_loss, target_ceiling, rr_ratio, volume_ratio, daily_turnover)

    except Exception:
        pass
    return None

if __name__ == "__main__":
    tickers = get_dynamic_aim_universe()
    market_is_healthy, market_val = check_market_regime()
    print(f"Executing V17 audit in [{SCAN_MODE}] mode across {len(tickers)} symbols...")
    print(f"Macro Market Health Status: {'HEALTHY' * market_is_healthy or 'DEFENSIVE'}")

    buoys_found = 0
    watch_found = 0

    for ticker in tickers:
        result = analyze_stock(ticker)
        if result:
            sig_type, cur_p, t_be, s_l, t_c, rr, v_rat, turnover = result
            if sig_type == "BUY":
                buoys_found += 1
                if market_is_healthy:
                    send_discord_embed(ticker, "STRONG BUY", cur_p, t_be, s_l, t_c, rr, v_rat, turnover, 3066993)
                else:
                    print(f"Suppressed BUY for {ticker} due to bearish macro market regime.")
            elif sig_type == "WATCH":
                watch_found += 1
                send_discord_embed(ticker, "WATCHLIST", cur_p, t_be, s_l, t_c, rr, v_rat, turnover, 16776960)
                
        time.sleep(random.uniform(0.2, 0.6))
            
    if SCAN_MODE == "FULL":
        send_summary_digest(len(tickers), buoys_found, watch_found, market_is_healthy)

    print(f"Audit Complete for Mode: {SCAN_MODE}")
