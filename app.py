import streamlit as st
import yfinance as yf
import pandas as pd
import datetime
import pytz

# --- CONFIGURATION ---
st.set_page_config(page_title="Forex AI Sniper", layout="wide", page_icon="🎯")

# --- CUSTOM CSS ---
st.markdown("""
    <style>
    .metric-card {background-color: #0e1117; border: 1px solid #303030; padding: 20px; border-radius: 10px; text-align: center;}
    </style>
    """, unsafe_allow_html=True)

# --- FUNCTIONS ---

def get_nigeria_time():
    lagos = pytz.timezone('Africa/Lagos')
    return datetime.datetime.now(lagos)

def get_current_session(hour):
    if 14 <= hour < 17: return "🔥 KILL ZONE (London/NY Overlap)", "active"
    elif 9 <= hour < 14: return "🇬🇧 London Session", "active"
    elif 17 <= hour < 22: return "🇺🇸 New York Session", "active"
    elif 22 <= hour or hour < 9: return "😴 Dead Zone / Asian", "inactive"
    return "Unknown", "inactive"

def calculate_strength():
    # Fetch 2 days of data to compare Close vs Open
    tickers = ["EURUSD=X", "GBPUSD=X", "USDJPY=X", "AUDUSD=X", "USDCAD=X", "DX-Y.NYB"]
    data = yf.download(tickers, period="2d", interval="1d", progress=False)
    
    strength = {}
    
    try:
        # USD Strength (DXY)
        dxy_open = data["DX-Y.NYB"]["Open"].iloc[-1]
        dxy_close = data["DX-Y.NYB"]["Close"].iloc[-1]
        strength['USD'] = ((dxy_close - dxy_open) / dxy_open) * 100
    except: strength['USD'] = 0.0

    # Calculate others relative to USD
    def get_change(pair):
        try:
            return ((data[pair]["Close"].iloc[-1] - data[pair]["Open"].iloc[-1]) / data[pair]["Open"].iloc[-1]) * 100
        except: return 0.0

    # Direct Pairs (XXX/USD) -> If Pair goes UP, XXX is Stronger
    strength['EUR'] = strength['USD'] + get_change("EURUSD=X")
    strength['GBP'] = strength['USD'] + get_change("GBPUSD=X")
    strength['AUD'] = strength['USD'] + get_change("AUDUSD=X")

    # Inverse Pairs (USD/XXX) -> If Pair goes UP, XXX is Weaker
    strength['JPY'] = strength['USD'] - get_change("USDJPY=X")
    strength['CAD'] = strength['USD'] - get_change("USDCAD=X")

    return strength

def get_smart_signal(strong, weak):
    # Standard Forex Pairs Logic
    # 1. USD Pairs
    if "USD" in strong and "EUR" in weak: return "SELL EURUSD"
    if "EUR" in strong and "USD" in weak: return "BUY EURUSD"
    
    if "USD" in strong and "GBP" in weak: return "SELL GBPUSD"
    if "GBP" in strong and "USD" in weak: return "BUY GBPUSD"
    
    if "USD" in strong and "JPY" in weak: return "BUY USDJPY"
    if "JPY" in strong and "USD" in weak: return "SELL USDJPY"

    if "USD" in strong and "CAD" in weak: return "BUY USDCAD"
    if "CAD" in strong and "USD" in weak: return "SELL USDCAD"
    
    # 2. Cross Pairs (Simple concatenation)
    return f"BUY {strong}{weak}"

# --- APP LAYOUT ---

st.title("🎯 AI Forex Sniper Dashboard")
st.caption("v2.0 | Auto-Translation | Live Strength")

col1, col2 = st.columns(2)
ng_time = get_nigeria_time()
session_name, status = get_current_session(ng_time.hour)

with col1:
    st.metric(label="🇳🇬 Lagos Time", value=ng_time.strftime("%H:%M:%S"))
with col2:
    st.metric(label="Market Status", value=session_name, delta="Open" if status=="active" else "Closed")

st.divider()

if st.button("🔍 SCAN MARKET NOW", type="primary"):
    with st.spinner('Accessing Market Data...'):
        
        scores = calculate_strength()
        
        # Sort
        sorted_strength = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        strongest = sorted_strength[0][0]
        weakest = sorted_strength[-1][0]
        
        # Smart Signal
        signal_text = get_smart_signal(strongest, weakest)
        
        # Display
        c1, c2 = st.columns(2)
        c1.metric("Strongest Currency", strongest, f"{scores[strongest]:.2f}%")
        c2.metric("Weakest Currency", weakest, f"{scores[weakest]:.2f}%")
        
        st.success(f"### 🚀 TOP SIGNAL: {signal_text}")
        
        # Chart
        st.write("### 📊 Strength Meter")
        df = pd.DataFrame.from_dict(scores, orient='index', columns=['% Strength'])
        st.bar_chart(df)

else:
    st.info("Click the button to scan.")
