import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import datetime
import pytz
from ta.trend import SMAIndicator
from ta.momentum import RSIIndicator
from ta.volatility import AverageTrueRange

# --- CONFIGURATION & THEME ---
st.set_page_config(page_title="Forex AI Sniper Pro", layout="wide", page_icon="🦅")

st.markdown("""
    <style>
    /* BabyPips White Theme */
    [data-testid="stAppViewContainer"] { background-color: #ffffff; color: #333333; }
    [data-testid="stHeader"] { background-color: #ffffff; }
    
    .status-card { padding: 15px; border-radius: 8px; text-align: center; color: white; font-weight: bold; margin-bottom: 5px; }
    .green-bg { background-color: #5da423; } /* London Green */
    .red-bg { background-color: #c60c30; }   /* NY Red */
    .gold-bg { background-color: #e3b128; color: black; } /* Overlap */
    .gray-bg { background-color: #999999; }
    
    .signal-box { border: 2px solid #333; padding: 20px; border-radius: 10px; text-align: center; margin-top: 20px; }
    .buy { background-color: #e6fffa; border-color: #00cc00; color: #006600; }
    .sell { background-color: #fff5f5; border-color: #cc0000; color: #660000; }
    .wait { background-color: #fffbe6; border-color: #cccc00; color: #666600; }
    </style>
    """, unsafe_allow_html=True)

# --- ADVANCED MATH ENGINE (The Brain) ---

def get_nigeria_time():
    return datetime.datetime.now(pytz.timezone('Africa/Lagos'))

def check_market_volatility(data):
    """Mataf Logic: Check if market is dead or alive using ATR."""
    try:
        # Calculate ATR on EURUSD 15m
        high = data["EURUSD=X"]["High"]
        low = data["EURUSD=X"]["Low"]
        close = data["EURUSD=X"]["Close"]
        atr = AverageTrueRange(high, low, close, window=14).average_true_range().iloc[-1]
        
        # Threshold: If ATR is extremely low, market is dead
        if atr < 0.0005: return "LOW (Wait)", False
        return "HIGH (Good)", True
    except:
        return "Unknown", True

def analyze_dxy_trend(data):
    """TradingView Logic: Analyze DXY using SMA and RSI."""
    try:
        close = data["DX-Y.NYB"]["Close"]
        
        # SMA 50 (Trend)
        sma50 = SMAIndicator(close, window=50).sma_indicator().iloc[-1]
        current_price = close.iloc[-1]
        
        # RSI 14 (Momentum)
        rsi = RSIIndicator(close, window=14).rsi().iloc[-1]
        
        trend = "BULLISH" if current_price > sma50 else "BEARISH"
        condition = "Neutral"
        
        if rsi > 70: condition = "Overbought (Risk Reversal)"
        elif rsi < 30: condition = "Oversold (Risk Bounce)"
        else: condition = "Healthy"
        
        return trend, condition, rsi
    except:
        return "Neutral", "Unknown", 50

def calculate_strength_matrix(data):
    """Finviz Logic: Calculate relative strength %."""
    strength = {}
    
    # Base: DXY % Change
    try:
        d_open = data["DX-Y.NYB"]["Open"].iloc[-1]
        d_close = data["DX-Y.NYB"]["Close"].iloc[-1]
        strength['USD'] = ((d_close - d_open) / d_open) * 100
    except: strength['USD'] = 0.0

    pairs = {
        "EUR": "EURUSD=X", "GBP": "GBPUSD=X", "AUD": "AUDUSD=X",
        "JPY": "USDJPY=X", "CAD": "USDCAD=X"
    }
    
    for currency, ticker in pairs.items():
        try:
            op = data[ticker]["Open"].iloc[-1]
            cl = data[ticker]["Close"].iloc[-1]
            change = ((cl - op) / op) * 100
            
            if currency in ["EUR", "GBP", "AUD"]:
                strength[currency] = strength['USD'] + change
            else: # Inverse pairs
                strength[currency] = strength['USD'] - change
        except:
            strength[currency] = 0.0
            
    return strength

# --- MAIN APP ---

st.title("🦅 Forex AI Sniper Pro")
st.markdown("**Integrated Logic: TradingView Trend + Mataf Volatility + Finviz Strength**")

# 1. TIME & SESSION PANEL
t = get_nigeria_time()
h = t.hour
if 14 <= h < 17: s_name, s_css = "🔥 KILL ZONE", "gold-bg"
elif 9 <= h < 14: s_name, s_css = "🇬🇧 LONDON OPEN", "green-bg"
elif 17 <= h < 22: s_name, s_css = "🇺🇸 NEW YORK OPEN", "red-bg"
else: s_name, s_css = "😴 ASIAN / CLOSED", "gray-bg"

c1, c2, c3 = st.columns(3)
c1.markdown(f"### 🇳🇬 Lagos: {t.strftime('%H:%M')}")
c2.markdown(f'<div class="status-card {s_css}">{s_name}</div>', unsafe_allow_html=True)
# Forex Factory Link (Safest Way)
c3.link_button("📅 Check News (ForexFactory)", "https://www.forexfactory.com/calendar")

st.divider()

# 2. THE SCANNER
if st.button("🔍 RUN DEEP SCAN (All Data Sources)", type="primary", use_container_width=True):
    with st.spinner('Calculating DXY Trend... Measuring Volatility... Ranking Strength...'):
        
        # FETCH DATA (1 Day, 15m intervals for precision)
        tickers = ["EURUSD=X", "GBPUSD=X", "USDJPY=X", "AUDUSD=X", "USDCAD=X", "DX-Y.NYB"]
        data = yf.download(tickers, period="5d", interval="15m", group_by='ticker', progress=False)
        
        # A. MATAF CHECK (Volatility)
        vol_status, is_active = check_market_volatility(data)
        
        # B. TRADINGVIEW CHECK (Trend)
        dxy_trend, dxy_cond, dxy_rsi = analyze_dxy_trend(data)
        
        # C. FINVIZ CHECK (Strength)
        scores = calculate_strength_matrix(data)
        sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        strongest, s_val = sorted_scores[0]
        weakest, w_val = sorted_scores[-1]
        
        # --- DISPLAY RESULTS ---
        
        # 1. Market Health
        m1, m2, m3 = st.columns(3)
        m1.metric("Mataf Volatility", vol_status)
        m2.metric("TradingView DXY Trend", dxy_trend, dxy_cond)
        m3.metric("DXY RSI", f"{dxy_rsi:.1f}")
        
        # 2. The Verdict
        if not is_active:
            st.warning("⛔ MARKET IS SLEEPING (Low Volatility). Wait for London/NY Open.")
        else:
            # Generate Pair Name
            pair_map = {"USDJPY": "USDJPY", "EURUSD": "EURUSD", "GBPUSD": "GBPUSD", "USDCAD": "USDCAD", "AUDUSD": "AUDUSD"}
            
            # Logic for Pair Name
            raw_pair = f"{strongest}{weakest}"
            action = "BUY"
            
            # Correction for inverse logic
            if strongest == "USD" and weakest == "EUR": 
                final_pair = "EURUSD"; action = "SELL"
            elif strongest == "USD" and weakest == "GBP": 
                final_pair = "GBPUSD"; action = "SELL"
            elif strongest == "USD" and weakest == "AUD": 
                final_pair = "AUDUSD"; action = "SELL"
            elif strongest == "JPY" and weakest == "USD":
                final_pair = "USDJPY"; action = "SELL"
            elif strongest == "CAD" and weakest == "USD":
                final_pair = "USDCAD"; action = "SELL"
            else:
                final_pair = raw_pair
            
            # DXY Confirmation Filter
            confirmation = "✅ APPROVED"
            if "USD" in final_pair:
                if action == "BUY" and "USD" == strongest and dxy_trend == "BEARISH": confirmation = "⚠️ RISKY (DXY Divergence)"
                if action == "SELL" and "USD" == strongest and dxy_trend == "BULLISH": confirmation = "⚠️ RISKY (DXY Divergence)"

            # FINAL SIGNAL BOX
            css_class = "buy" if action == "BUY" else "sell"
            
            st.markdown(f"""
            <div class="signal-box {css_class}">
                <h2>AI SIGNAL: {action} {final_pair}</h2>
                <p>Strongest: {strongest} ({s_val:.2f}%) | Weakest: {weakest} ({w_val:.2f}%)</p>
                <p><b>Confirmation:</b> {confirmation}</p>
            </div>
            """, unsafe_allow_html=True)
            
            # Chart
            st.bar_chart(pd.DataFrame.from_dict(scores, orient='index', columns=['Strength']))

else:
    st.info("Tap the button to run the Pro Algorithm.")
