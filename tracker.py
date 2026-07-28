import yfinance as yf
import pandas as pd
import numpy as np
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

# --- UNIFIED DUAL-STRATEGY CONFIGURATION ---
WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK")
MAX_WORKERS = 10  

HL_FEE_TOTAL = 13.90          
CAPITAL_PER_TRADE = 300.0     
MAX_ALLOWABLE_CASH_RISK = 10.0 

MIN_MARKET_CAP = 2000000.0    
MAX_MARKET_CAP = 1500000000.0 
MAX_DAY_GAIN_PCT = 15.0       
ESTIMATED_SPREAD_DRAG = 0.025 

def get_dynamic_aim_universe():
    logging.info("Drawing live equity universe via TradingView API...")
    url = "https://scanner.tradingview.com/uk/scan"
    payload = {
        "columns": ["name"],
        "filter": [
            {"left": "exchange", "operation": "equal", "right": "LSE"},
            {"left": "type", "operation": "equal", "right": "stock"}
        ]
    }
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    
    for attempt in range(1, 4):
        try:
            response = requests.post(url, json=payload, headers=headers, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            aim_tickers = []
            for row in data.get("data", []):
                ticker = row["d"][0]
                if "." not in ticker and "0o" not in ticker.lower() and "-" not in ticker and "/" not in ticker:
                    aim_tickers.append(f"{ticker}.L")
                    
            aim_tickers = list(set(aim_tickers))
            if aim_tickers:
                logging.info(f"Successfully drew and cleaned {len(aim_tickers)} live securities from TradingView.")
                return aim_tickers
                
        except Exception as e:
            logging.warning(f"Attempt {attempt}/3 failed to draw live registry: {e}")
            if attempt < 3:
                time.sleep(3)
                
    logging.critical("CRITICAL ERROR: All attempts to draw live registry failed. Aborting run.")
    sys.exit(1)

def get_market_benchmark_returns():
    try:
        market = yf.Ticker("^AXX")
        df_mkt = market.history(period="3mo")
        if not df_mkt.empty and len(df_mkt) >= 2:
            return df_mkt['Close'], (df_mkt['Close'].iloc[-1] / df_mkt['Close'].iloc[0]) - 1.0
    except Exception as e:
        logging.warning(f"Failed to fetch market benchmark ^AXX: {e}")
    return None, 0.0

def check_market_regime(df_mkt):
    try:
        if df_mkt is not None and not df_mkt.empty and len(df_mkt) >= 50:
            sma_50 = df_mkt.rolling(window=50).mean().iloc[-1]
            current_val = df_mkt.iloc[-1]
            return current_val >= sma_50
    except Exception:
        pass
    return True

def log_signal_to_csv(ticker, signal_type, current_price, target_sell_price, rsi_val, volume_ratio):
    try:
        file_path = Path("trade_history.csv")
        file_exists = file_path.is_file()
        
        with open(file_path, mode="a", newline="") as f:
            writer = csv.writer(f)
            if not file_exists:
                writer.writerow(["Timestamp", "Ticker", "Signal", "Price", "Target_Sell", "RSI", "Volume_Ratio"])
            
            writer.writerow([pd.Timestamp.utcnow().isoformat(), ticker, signal_type, current_price, target_sell_price, rsi_val, volume_ratio])
    except Exception as e:
        logging.error(f"Failed to log CSV for {ticker}: {e}")

def send_discord_embed(ticker, signal_type, current_price, true_break_even, stop_loss, target_sell_price, ideal_profit, rr_ratio, volume_ratio, turnover, recommended_shares, rsi_val, float_shares, target_profit_pct, color):
    if not WEBHOOK_URL:
        return
        
    yahoo_url = f"https://finance.yahoo.com/quote/{ticker}"
    float_display = f"{float_shares:,.0f}" if float_shares > 0 else "N/A"
    
    embed = {
        "title": f"🎯⚖️ {signal_type}: {ticker}",
        "url": yahoo_url,
        "color": color,
        "description": f"Unified Engine Alert with **{target_profit_pct}% Profit Target** (£300 Sizing).",
        "fields": [
            {"name": "💵 Current Price", "value": f"`{current_price:.2f}p`", "inline": True},
            {"name": "🛡️ True Break-Even", "value": f"`{true_break_even:.2f}p`", "inline": True},
            {"name": "🎯 Target Sell Price", "value": f"`{target_sell_price:.2f}p`", "inline": True},
            {"name": "🛑 Initial Stop", "value": f"`{stop_loss:.2f}p`", "inline": True},
            {"name": "💷 Est. Net Profit", "value": f"`£{ideal_profit:.2f}`", "inline": True},
            {"name": "⚖️ R:R Ratio", "value": f"`1:{rr_ratio:.1f}`", "inline": True},
            {"name": "⚡ RSI (14)", "value": f"`{rsi_val:.1f}`", "inline": True},
            {"name": "📊 Volume Surge", "value": f"`{volume_ratio:.1f}x`", "inline": True},
            {"name": "🧬 Free Float", "value": f"`{float_display}`", "inline": True},
            {"name": "📦 Sized Shares (£10 Risk)", "value": f"`{recommended_shares} shares`", "inline": True}
        ],
        "footer": {"text": f"AIM Unified Dual-Strategy Engine • Active"},
        "timestamp": pd.Timestamp.utcnow().isoformat()
    }
    try:
        requests.post(WEBHOOK_URL, json={"embeds": [embed]}, timeout=5)
    except Exception as e:
        logging.error(f"Discord webhook failed for {ticker}: {e}")

def send_enhanced_summary_digest(scanned_count, buys_found, lottery_found, watch_found, regime_status, top_volume_ticker, top_volume_val, avg_rsi, lowest_caps, lowest_shares):
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
        "title": f"📊 End-of-Day Dual-Strategy Audit Digest",
        "color": 3447003,
        "description": f"Comprehensive multi-threaded session audit completed.",
        "fields": [
            {"name": "🔍 Total Scanned", "value": f"`{scanned_count}`", "inline": True},
            {"name": "🌐 Market Regime", "value": f"`{status_text}`", "inline": True},
            {"name": "📈 Universe Avg RSI", "value": avg_rsi_text, "inline": True},
            {"name": "🚀 Top Volume Leader", "value": top_vol_text, "inline": True},
            {"name": "🚨 Standard Buys", "value": f"`{buys_found}`", "inline": True},
            {"name": "⚡ Lottery Multi-Baggers", "value": f"`{lottery_found}`", "inline": True},
            {"name": "⭐ Watchlist Setups", "value": f"`{watch_found}`", "inline": True},
            {"name": "📉 Top 10 Lowest Market Caps", "value": caps_text, "inline": False},
            {"name": "📊 Top 10 Lowest Shares in Issue", "value": shares_text, "inline": False}
        ],
        "footer": {"text": f"AIM Engine Dual-Strategy • Active"},
        "timestamp": pd.Timestamp.utcnow().isoformat()
    }
    try:
        requests.post(WEBHOOK_URL, json={"embeds": [embed]}, timeout=5)
    except Exception as e:
        logging.error(f"Discord summary webhook failed: {e}")

def analyze_stock(ticker, market_3m_return):
    metrics = {}
    try:
        stock = yf.Ticker(ticker)
        info = stock.info or {}
        
        quote_type = info.get('quoteType', 'EQUITY')
        if quote_type and quote_type.upper() != 'EQUITY':
            return None, metrics, ticker

        market_cap = info.get('marketCap', 0) or 0
        
        if market_cap < MIN_MARKET_CAP or market_cap > MAX_MARKET_CAP:
            return None, metrics, ticker

        shares_outstanding = info.get('sharesOutstanding', 0) or 0
        float_shares = info.get('floatShares', 0) or 0

        df = stock.history(period="3mo")
        if df.empty or len(df) < 50:
            df = stock.history(period="6mo")
        
        if df.empty or len(df) < 50:
            return None, metrics, ticker

        current_price = df['Close'].iloc[-1]
        today_volume = df['Volume'].iloc[-1]

        if pd.isna(current_price) or current_price <= 0 or pd.isna(today_volume) or today_volume <= 0:
            return None, metrics, ticker
        
        if not shares_outstanding and market_cap > 0 and current_price > 0:
            shares_outstanding = market_cap / (current_price / 100.0)

        metrics = {"market_cap": market_cap, "shares_outstanding": shares_outstanding}

        df['SMA_20'] = df['Close'].rolling(window=20).mean()
        df['SMA_50'] = df['Close'].rolling(window=50).mean()
        df['Vol_20'] = df['Volume'].rolling(window=20).mean()
        
        df['High_Low'] = df['High'] - df['Low']
        df['High_Close'] = abs(df['High'] - df['Close'].shift())
        df['Low_Close'] = abs(df['Low'] - df['Close'].shift())
        df['TR'] = df[['High_Low', 'High_Close', 'Low_Close']].max(axis=1)
        df['ATR_14'] = df['TR'].rolling(window=14).mean()
        
        df['Typical_Price'] = (df['High'] + df['Low'] + df['Close']) / 3
        df['VWAP_14'] = (df['Typical_Price'] * df['Volume']).rolling(window=14).sum() / df['Volume'].rolling(window=14).sum()

        df['OBV'] = (np.sign(df['Close'].diff()) * df['Volume']).fillna(0).cumsum()

        delta = df['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        df['RSI_14'] = 100 - (100 / (1 + rs))

        today = df.iloc[-1]
        yesterday = df.iloc[-2]
        
        if pd.isna(today['ATR_14']) or pd.isna(today['RSI_14']) or yesterday['Close'] <= 0:
            return None, metrics, ticker

        daily_gain_pct = ((current_price - yesterday['Close']) / yesterday['Close']) * 100.0
        if daily_gain_pct > MAX_DAY_GAIN_PCT:
            return None, metrics, ticker

        metrics["rsi"] = today['RSI_14']
        avg_volume = yesterday['Vol_20'] if (yesterday['Vol_20'] and yesterday['Vol_20'] > 0) else 1
        volume_ratio = today['Volume'] / avg_volume
        metrics["volume_ratio"] = volume_ratio

        daily_turnover = (today['Volume'] * current_price) / 100
        
        raw_shares = CAPITAL_PER_TRADE / (current_price / 100)
        fee_per_share_impact = (HL_FEE_TOTAL / raw_shares) * 100 if raw_shares > 0 else 0
        
        df_weekly = df.resample('W').agg({'Close': 'last'})
        df_weekly['EMA_10'] = df_weekly['Close'].ewm(span=10, adjust=False).mean()
        weekly_trend_ok = len(df_weekly) >= 10 and df_weekly['Close'].iloc[-1] >= df_weekly['EMA_10'].iloc[-1]

        is_golden_cross = (yesterday['SMA_20'] <= yesterday['SMA_50']) and (today['SMA_20'] > today['SMA_50'])
        is_above_trend = current_price > today['SMA_20']
        is_above_vwap = current_price > today['VWAP_14']
        rsi_healthy = 48.0 <= today['RSI_14'] <= 75.0
        obv_accumulating = len(df) >= 4 and df['OBV'].iloc[-1] > df['OBV'].iloc[-4]
        stock_3m_return = (df['Close'].iloc[-1] / df['Close'].iloc[0]) - 1.0
        relative_strength_ok = stock_3m_return > market_3m_return

        # ==========================================
        # CHECK 1: LOTTERY / MULTI-BAGGER CRITERIA
        # ==========================================
        is_micro_cap = market_cap <= 25000000.0
        low_float = float_shares <= 50000000.0 if float_shares > 0 else True
        massive_volume = volume_ratio >= 3.0

        if is_micro_cap and low_float and massive_volume and is_above_vwap and rsi_healthy:
            target_profit_pct = 50.0  
            true_break_even_price = current_price + fee_per_share_impact + (current_price * ESTIMATED_SPREAD_DRAG)
            target_sell_price = true_break_even_price * (1.0 + (target_profit_pct / 100.0))
            stop_loss = current_price - (today['ATR_14'] * 2.0) 
            risk_distance_pence = current_price - stop_loss
            
            if risk_distance_pence > 0:
                reward_distance_pence = target_sell_price - current_price
                rr_ratio = reward_distance_pence / risk_distance_pence
                risk_per_share_gbp = risk_distance_pence / 100.0
                recommended_shares = max(1, int(MAX_ALLOWABLE_CASH_RISK / risk_per_share_gbp))
                ideal_profit_gbp = (recommended_shares * (target_sell_price - true_break_even_price)) / 100.0
                
                return ("LOTTERY", current_price, true_break_even_price, stop_loss, target_sell_price, ideal_profit_gbp, rr_ratio, volume_ratio, daily_turnover, recommended_shares, today['RSI_14'], float_shares, target_profit_pct), metrics, ticker

        # ==========================================
        # CHECK 2: STANDARD MOMENTUM BUY CRITERIA
        # ==========================================
        if market_cap >= 5000000.0 and daily_turnover >= 10000.0:
            target_profit_pct = 15.0
            true_break_even_price = current_price + fee_per_share_impact + (current_price * ESTIMATED_SPREAD_DRAG)
            target_sell_price = true_break_even_price * (1.0 + (target_profit_pct / 100.0))
            stop_loss = current_price - (today['ATR_14'] * 1.5)
            risk_distance_pence = current_price - stop_loss
            
            if risk_distance_pence > 0:
                reward_distance_pence = target_sell_price - current_price
                rr_ratio = reward_distance_pence / risk_distance_pence
                risk_per_share_gbp = risk_distance_pence / 100.0
                recommended_shares = max(1, int(MAX_ALLOWABLE_CASH_RISK / risk_per_share_gbp))
                ideal_profit_gbp = (recommended_shares * (target_sell_price - true_break_even_price)) / 100.0

                if is_golden_cross and is_above_trend and is_above_vwap and obv_accumulating and relative_strength_ok and weekly_trend_ok and rsi_healthy and volume_ratio >= 1.3 and rr_ratio >= 1.8:
                    return ("BUY", current_price, true_break_even_price, stop_loss, target_sell_price, ideal_profit_gbp, rr_ratio, volume_ratio, daily_turnover, recommended_shares, today['RSI_14'], float_shares, target_profit_pct), metrics, ticker
            
            # ==========================================
            # CHECK 3: WATCHLIST CRITERIA
            # ==========================================
            distance_to_ma = abs(current_price - today['SMA_50']) / today['SMA_50']
            if distance_to_ma <= 0.015 and is_above_vwap and obv_accumulating and relative_strength_ok and weekly_trend_ok and rsi_healthy and rr_ratio >= 1.8:
                return ("WATCH", current_price, true_break_even_price, stop_loss, target_sell_price, ideal_profit_gbp, rr_ratio, volume_ratio, daily_turnover, recommended_shares, today['RSI_14'], float_shares, target_profit_pct), metrics, ticker

    except Exception:
        pass
        
    time.sleep(random.uniform(0.1, 0.3)) 
    return None, metrics, ticker

if __name__ == "__main__":
    tickers = get_dynamic_aim_universe()
    df_mkt_series, market_3m_return = get_market_benchmark_returns()
    market_is_healthy = check_market_regime(df_mkt_series)
    
    logging.info(f"Executing Dual-Strategy AIM audit across {len(tickers)} symbols...")

    buys_found = 0
    lottery_found = 0
    watch_found = 0
    scanned_successfully = 0
    rsi_accumulator = []
    highest_vol_ratio = 0.0
    top_vol_ticker = None
    all_market_caps = []
    all_shares_data = []

    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(analyze_stock, ticker, market_3m_return): ticker for ticker in tickers}
        
        for future in concurrent.futures.as_completed(futures):
            try:
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
                    sig_type, cur_p, t_be, s_l, t_sell, ideal_prof, rr, v_rat, turnover, rec_shares, rsi_v, float_shs, target_pct = result
                    log_signal_to_csv(ticker, sig_type, cur_p, t_sell, rsi_v, v_rat)
                    logging.info(f"Signal Generated: {sig_type} for {ticker} (Net Profit: £{ideal_prof:.2f})")
                    
                    if sig_type == "BUY":
                        buys_found += 1
                        if market_is_healthy:
                            send_discord_embed(ticker, "STRONG BUY", cur_p, t_be, s_l, t_sell, ideal_prof, rr, v_rat, turnover, rec_shares, rsi_v, float_shs, target_pct, 3066993)
                    elif sig_type == "LOTTERY":
                        lottery_found += 1
                        if market_is_healthy:
                            send_discord_embed(ticker, "⚡ LOTTERY MULTI-BAGGER", cur_p, t_be, s_l, t_sell, ideal_prof, rr, v_rat, turnover, rec_shares, rsi_v, float_shs, target_pct, 15158332)
                    elif sig_type == "WATCH":
                        watch_found += 1
                        send_discord_embed(ticker, "WATCHLIST", cur_p, t_be, s_l, t_sell, ideal_prof, rr, v_rat, turnover, rec_shares, rsi_v, float_shs, target_pct, 16776960)
            except Exception as thread_err:
                logging.debug(f"Error handling future result: {thread_err}")

    avg_rsi = sum(rsi_accumulator) / len(rsi_accumulator) if rsi_accumulator else 0.0
    if not top_vol_ticker and rsi_accumulator:
        top_vol_ticker = "N/A (Filtered)"
        highest_vol_ratio = 0.0
        
    all_market_caps.sort(key=lambda x: x[1])
    all_shares_data.sort(key=lambda x: x[1])
        
    send_enhanced_summary_digest(scanned_successfully, buys_found, lottery_found, watch_found, market_is_healthy, top_vol_ticker, highest_vol_ratio, avg_rsi, all_market_caps[:10], all_shares_data[:10])

    logging.info(f"Dual-Strategy Audit Complete. Successfully analyzed {scanned_successfully} records.")
