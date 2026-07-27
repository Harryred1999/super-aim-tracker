import yfinance as yf
import pandas as pd
import requests
import os
import time
import random
from pytickersymbols import PyTickerSymbols

# --- CONFIGURATION & ELITE PARAMETERS ---
WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK")
HL_FEE_TOTAL = 13.90          # £6.95 buy + £6.95 sell flat fee
CAPITAL_PER_TRADE = 300.0     # Position size (£300)
MIN_DAILY_TURNOVER = 15000.0  # Ultra-strict liquidity floor (£15k/day minimum cash flow)
MIN_VOLUME_MULTIPLIER = 2.2   # Requires 2.2x normal volume to confirm explosive momentum
ESTIMATED_SPREAD_DRAG = 0.025 # 2.5% estimated bid-ask spread penalty for AIM micro-caps
MIN_PROFIT_BUFFER = 0.035     # Requires at least 3.5% clear headroom *after* all drag

def get_dynamic_aim_universe():
    """
    Dynamically loads the full London Stock Exchange and AIM universe 
    programmatically using pytickersymbols, eliminating hardcoded lists.
    """
    print("Fetching dynamic market universe...")
    aim_tickers = []
    try:
        stock_data = PyTickerSymbols()
        uk_stocks = stock_data.get_stocks_by_exchange("LSE")
        
        for stock in uk_stocks:
            symbols = stock.get('symbols', [])
            for sym_entry in symbols:
                symbol_str = str(sym_entry.get('symbol', '')).strip().upper()
                if symbol_str.endswith('.L'):
                    if symbol_str not in aim_tickers:
                        aim_tickers.append(symbol_str)
                        
        print(f"Successfully loaded {len(aim_tickers)} dynamic LSE/AIM securities.")
    except Exception as e:
        print(f"Error fetching dynamic registry: {e}. Engaging safety fallback list.")
        aim_tickers = [
            "BOO.L", "FDEV.L", "JET2.L", "IQE.L", "BUR.L", "ASC.L", "CVSG.L", "DTY.L", 
            "GNS.L", "ANGS.L", "TRB.L", "SCS.L", "KOD.L", "HE1.L", "PREM.L", "SAV.L",
            "POW.L", "UJO.L", "CLNR.L", "ARBA.L", "AAZ.L", "EMH.L", "SRT.L", "SFOR.L"
        ]
        
    return aim_tickers

def send_discord_embed(ticker, signal_type, current_price, true_break_even, target_ceiling, volume_ratio, turnover, color):
    """Sends a clean, user-friendly Discord alert card with direct chart links."""
    if not WEBHOOK_URL:
        return
        
    yahoo_url = f"https://finance.yahoo.com/quote/{ticker}"
    
    embed = {
        "title": f"🔥 {signal_type}: {ticker}",
        "url": yahoo_url,
        "color": color,
        "description": f"Click the title above to view live charts for **{ticker}** on Yahoo Finance.",
        "fields": [
            {"name": "💵 Current Price", "value": f"`{current_price:.2f}p`", "inline": True},
            {"name": "🛡️ True Break-Even", "value": f"`{true_break_even:.2f}p`", "inline": True},
            {"name": "🎯 Min Target Ceiling", "value": f"`{target_ceiling:.2f}p`", "inline": True},
            {"name": "📊 Volume Surge", "value": f"`{volume_ratio:.1f}x avg`", "inline": True},
            {"name": "💷 Daily Turnover", "value": f"`£{turnover:,.0f}`", "inline": True},
            {"name": "💼 Position Size", "value": f"`£{CAPITAL_PER_TRADE}`", "inline": True}
        ],
        "footer": {"text": f"AIM Dynamic Elite V13 • Hargreaves Lansdown Fee Model (£13.90)"},
        "timestamp": pd.Timestamp.utcnow().isoformat()
    }
    
    requests.post(WEBHOOK_URL, json={"embeds": [embed]})

def analyze_stock(ticker):
    try:
        stock = yf.Ticker(ticker)
        df = stock.history(period="6mo")
        
        if df.empty or len(df) < 50:
            return

        df['SMA_20'] = df['Close'].rolling(window=20).mean()
        df['SMA_50'] = df['Close'].rolling(window=50).mean()
        df['Vol_20'] = df['Volume'].rolling(window=20).mean()
        
        today = df.iloc[-1]
        yesterday = df.iloc[-2]
        current_price = today['Close']
        
        if current_price <= 0:
            return

        daily_turnover = (today['Volume'] * current_price) / 100
        if daily_turnover < MIN_DAILY_TURNOVER:
            return

        avg_volume = yesterday['Vol_20'] if (yesterday['Vol_20'] and yesterday['Vol_20'] > 0) else 1
        volume_ratio = today['Volume'] / avg_volume
        
        raw_shares = CAPITAL_PER_TRADE / (current_price / 100)
        fee_per_share_impact = (HL_FEE_TOTAL / raw_shares) * 100
        
        true_break_even_price = current_price + fee_per_share_impact + (current_price * ESTIMATED_SPREAD_DRAG)
        target_ceiling = true_break_even_price * (1 + MIN_PROFIT_BUFFER)

        is_golden_cross = (yesterday['SMA_20'] <= yesterday['SMA_50']) and (today['SMA_20'] > today['SMA_50'])
        is_above_trend = current_price > today['SMA_20']
        
        if is_golden_cross and is_above_trend and volume_ratio >= MIN_VOLUME_MULTIPLIER:
            send_discord_embed(ticker, "STRONG BUY", current_price, true_break_even_price, target_ceiling, volume_ratio, daily_turnover, 3066993)
        else:
            distance_to_ma = abs(current_price - today['SMA_50']) / today['SMA_50']
            if distance_to_ma <= 0.008:
                send_discord_embed(ticker, "WATCHLIST", current_price, true_break_even_price, target_ceiling, volume_ratio, daily_turnover, 16776960)

    except Exception:
        pass

if __name__ == "__main__":
    tickers = get_dynamic_aim_universe()
    print(f"Executing Dynamic V13 audit across {len(tickers)} symbols...")
    
    for i, ticker in enumerate(tickers):
        analyze_stock(ticker)
        time.sleep(random.uniform(0.3, 0.9))
            
    print("Market Audit Complete.")
