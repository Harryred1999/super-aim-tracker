import yfinance as yf
import pandas as pd
import requests
import os
import time
import random
from pytickersymbols import PyTickerSymbols

# --- CONFIGURATION & RISK-MANAGED PARAMETERS ---
WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK")
HL_FEE_TOTAL = 13.90          # £6.95 buy + £6.95 sell flat fee
CAPITAL_PER_TRADE = 300.0     # Position size (£300)
MIN_DAILY_TURNOVER = 15000.0  # Liquidity floor (£15k/day)
MIN_VOLUME_MULTIPLIER = 2.2   # Volume surge requirement
ESTIMATED_SPREAD_DRAG = 0.025 # 2.5% spread penalty
MIN_RISK_REWARD_RATIO = 2.0   # Requires reward to be at least 2x the risk

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

def send_discord_embed(ticker, signal_type, current_price, true_break_even, stop_loss, target_ceiling, rr_ratio, volume_ratio, turnover, color):
    if not WEBHOOK_URL:
        return
        
    yahoo_url = f"https://finance.yahoo.com/quote/{ticker}"
    
    embed = {
        "title": f"🛡️⚖️ {signal_type} (Risk Managed): {ticker}",
        "url": yahoo_url,
        "color": color,
        "description": f"Validated setup for **{ticker}** featuring strict risk-to-reward metrics.",
        "fields": [
            {"name": "💵 Current Price", "value": f"`{current_price:.2f}p`", "inline": True},
            {"name": "🛡️ True Break-Even", "value": f"`{true_break_even:.2f}p`", "inline": True},
            {"name": "🛑 Stop-Loss Level", "value": f"`{stop_loss:.2f}p`", "inline": True},
            {"name": "🎯 Target Ceiling", "value": f"`{target_ceiling:.2f}p`", "inline": True},
            {"name": "⚖️ Risk/Reward Ratio", "value": f"`1:{rr_ratio:.1f}`", "inline": True},
            {"name": "📊 Volume Surge", "value": f"`{volume_ratio:.1f}x avg`", "inline": True},
            {"name": "💷 Daily Turnover", "value": f"`£{turnover:,.0f}`", "inline": True}
        ],
        "footer": {"text": f"AIM Risk Engine V15 • £13.90 Fee Model"},
        "timestamp": pd.Timestamp.utcnow().isoformat()
    }
    requests.post(WEBHOOK_URL, json={"embeds": [embed]})

def analyze_stock(ticker):
    try:
        stock = yf.Ticker(ticker)
        df = stock.history(period="6mo")
        
        if df.empty or len(df) < 50:
            return

        # Core Indicators & ATR for Stop Loss sizing
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
            return

        # --- LIQUIDITY & VOLUME GATES ---
        daily_turnover = (today['Volume'] * current_price) / 100
        if daily_turnover < MIN_DAILY_TURNOVER:
            return

        avg_volume = yesterday['Vol_20'] if (yesterday['Vol_20'] and yesterday['Vol_20'] > 0) else 1
        volume_ratio = today['Volume'] / avg_volume
        
        # --- RISK MANAGEMENT & FEE MATH ---
        raw_shares = CAPITAL_PER_TRADE / (current_price / 100)
        fee_per_share_impact = (HL_FEE_TOTAL / raw_shares) * 100
        true_break_even_price = current_price + fee_per_share_impact + (current_price * ESTIMATED_SPREAD_DRAG)
        
        # Define structural stop loss below recent volatility bounds (1.5x ATR)
        stop_loss = current_price - (current_atr * 1.5)
        risk_distance = current_price - stop_loss
        
        # Define target ceiling allowing a 3.5% clear profit buffer above break-even
        target_ceiling = true_break_even_price * 1.035
        reward_distance = target_ceiling - current_price
        
        # Calculate Risk-to-Reward Ratio
        if risk_distance <= 0:
            return
        rr_ratio = reward_distance / risk_distance

        # --- CONVICTION CRITERIA ---
        is_golden_cross = (yesterday['SMA_20'] <= yesterday['SMA_50']) and (today['SMA_20'] > today['SMA_50'])
        is_above_trend = current_price > today['SMA_20']
        
        # Require strict R:R compliance alongside volume and momentum triggers
        if is_golden_cross and is_above_trend and volume_ratio >= MIN_VOLUME_MULTIPLIER and rr_ratio >= MIN_RISK_REWARD_RATIO:
            send_discord_embed(ticker, "STRONG BUY", current_price, true_break_even_price, stop_loss, target_ceiling, rr_ratio, volume_ratio, daily_turnover, 3066993)
        else:
            distance_to_ma = abs(current_price - today['SMA_50']) / today['SMA_50']
            if distance_to_ma <= 0.008 and rr_ratio >= MIN_RISK_REWARD_RATIO:
                send_discord_embed(ticker, "WATCHLIST", current_price, true_break_even_price, stop_loss, target_ceiling, rr_ratio, volume_ratio, daily_turnover, 16776960)

    except Exception:
        pass

if __name__ == "__main__":
    tickers = get_dynamic_aim_universe()
    print(f"Executing Risk-Managed V15 audit across {len(tickers)} symbols...")
    
    for i, ticker in enumerate(tickers):
        analyze_stock(ticker)
        time.sleep(random.uniform(0.3, 0.9))
            
    print("Risk-Managed Audit Complete.")
