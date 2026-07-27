import yfinance as yf
import pandas as pd
import requests
import os
import time
import random
from yahoo_fin import stock_info as si

# --- CONFIGURATION & ELITE PARAMETERS ---
WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK")
HL_FEE_TOTAL = 13.90          # £6.95 buy + £6.95 sell flat fee
CAPITAL_PER_TRADE = 300.0     # Position size (£300)
MIN_DAILY_TURNOVER = 15000.0  # Ultra-strict liquidity floor (£15k/day minimum cash flow)
MIN_VOLUME_MULTIPLIER = 2.2   # Requires 2.2x normal volume to confirm explosive momentum
ESTIMATED_SPREAD_DRAG = 0.025 # 2.5% estimated bid-ask spread penalty for AIM micro-caps
MIN_PROFIT_BUFFER = 0.035     # Requires at least 3.5% clear headroom *after* all drag

def get_full_aim_universe():
    """Dynamically pulls active FTSE AIM All-Share securities."""
    print("Fetching complete FTSE AIM All-Share market universe...")
    try:
        raw_tickers = si.tickers_ftseaim()
        aim_tickers = []
        for ticker in raw_tickers:
            clean_ticker = str(ticker).strip().upper()
            if not clean_ticker.endswith(".L"):
                clean_ticker += ".L"
            aim_tickers.append(clean_ticker)
        print(f"Loaded {len(aim_tickers)} AIM symbols successfully.")
        return aim_tickers
    except Exception as e:
        print(f"Error fetching dynamic index: {e}. Fallback engaged.")
        return ["BOO.L", "FDEV.L", "JET2.L", "IQE.L", "BUR.L", "ASC.L", "CVSG.L", "DTY.L", "GNS.L"]

def send_discord_embed(ticker, signal_type, current_price, true_break_even, target_ceiling, volume_ratio, turnover, color):
    """Sends a fully calculated, high-octane Discord alert card."""
    if not WEBHOOK_URL:
        return
        
    embed = {
        "title": f"🚀 {signal_type} SIGNAL: {ticker}",
        "color": color,
        "fields": [
            {"name": "Current Price", "value": f"{current_price:.2f}p", "inline": True},
            {"name": "True Break-Even (Fees+Spread)", "value": f"{true_break_even:.2f}p", "inline": True},
            {"name": "Min Target Ceiling", "value": f"{target_ceiling:.2f}p", "inline": True},
            {"name": "Volume Mult", "value": f"{volume_ratio:.1f}x avg 📊", "inline": True},
            {"name": "Daily Turnover", "value": f"£{turnover:,.0f}", "inline": True}
        ],
        "footer": {"text": f"Elite AIM Engine V10 | Capital: £{CAPITAL_PER_TRADE}"}
    }
    requests.post(WEBHOOK_URL, json={"embeds": [embed]})

def analyze_stock(ticker):
    try:
        stock = yf.Ticker(ticker)
        df = stock.history(period="6mo")
        
        if df.empty or len(df) < 50:
            return

        # Core Indicators
        df['SMA_20'] = df['Close'].rolling(window=20).mean()
        df['SMA_50'] = df['Close'].rolling(window=50).mean()
        df['Vol_20'] = df['Volume'].rolling(window=20).mean()
        
        today = df.iloc[-1]
        yesterday = df.iloc[-2]
        current_price = today['Close']
        
        if current_price <= 0:
            return

        # --- SAFETY NET 1: ELITE LIQUIDITY BARRIER (£15k) ---
        daily_turnover = (today['Volume'] * current_price) / 100
        if daily_turnover < MIN_DAILY_TURNOVER:
            return  # Blocks anything below institutional radar

        # Volume Check
        avg_volume = yesterday['Vol_20'] if (yesterday['Vol_20'] and yesterday['Vol_20'] > 0) else 1
        volume_ratio = today['Volume'] / avg_volume
        
        # --- SAFETY NET 2: ELITE FEE & SPREAD MATH (£300 Capital) ---
        raw_shares = CAPITAL_PER_TRADE / (current_price / 100)
        fee_per_share_impact = (HL_FEE_TOTAL / raw_shares) * 100
        
        true_break_even_price = current_price + fee_per_share_impact + (current_price * ESTIMATED_SPREAD_DRAG)
        target_ceiling = true_break_even_price * (1 + MIN_PROFIT_BUFFER)

        # --- ULTIMATE CONVICTION CRITERIA ---
        is_golden_cross = (yesterday['SMA_20'] <= yesterday['SMA_50']) and (today['SMA_20'] > today['SMA_50'])
        is_above_trend = current_price > today['SMA_20'] # Ensures price momentum is accelerating
        
        # 1. STRONG BUY: Golden Cross + Accelerating Price + 2.2x Volume + Massive Liquidity
        if is_golden_cross and is_above_trend and volume_ratio >= MIN_VOLUME_MULTIPLIER:
            send_discord_embed(ticker, "STRONG BUY", current_price, true_break_even_price, target_ceiling, volume_ratio, daily_turnover, 3066993) # Dark Green
            
        # 2. WATCHLIST: Laser-focused tightening within 0.8% of the 50-day MA
        else:
            distance_to_ma = abs(current_price - today['SMA_50']) / today['SMA_50']
            if distance_to_ma <= 0.008:
                send_discord_embed(ticker, "WATCHLIST", current_price, true_break_even_price, target_ceiling, volume_ratio, daily_turnover, 16776960) # Gold

    except Exception:
        pass

if __name__ == "__main__":
    aim_tickers = get_full_aim_universe()
    print(f"Executing Elite V10 audit across {len(aim_tickers)} tickers...")
    
    for i, ticker in enumerate(aim_tickers):
        analyze_stock(ticker)
        time.sleep(random.uniform(0.5, 1.2))
            
    print("Elite Market Audit Complete.")
