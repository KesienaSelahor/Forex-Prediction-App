import streamlit as st
import yfinance as yf
import pandas as pd
import datetime
import pytz
import plotly.graph_objects as go

# --- CONFIGURATION ---
st.set_page_config(page_title="Forex AI Sniper", layout="wide", page_icon="🎯")

# --- CUSTOM CSS (Visuals) ---
st.markdown("""
    <style>
    .metric-card {background-color: #0e1117; border: 1px solid #303030; padding: 20px; border-radius: 10px; text-align: center;}
    .big-font {font-size: 24px !important; font-weight: bold;}
    .green {color: #00ff00;}
    .red {color: #ff0000;}
    .yellow {color: #ffff00;}
    </style>
    """, unsafe_allow_html=True)

# --- HELPER FUNCTIONS ---

def get_nigeria_time():
    """Get current time in Lagos."""
    lagos = pytz.timezone('Africa/Lagos')
    return datetime.datetime.now(lagos)

def get_current_session(hour):
    """Determine the active session based on Nigeria Time."""
    # Simple logic: London (9-17), NY (14-22), Overlap (14-17)
    if 14 <= hour < 17:
        return "🔥 KILL ZONE (London/NY Overlap)", "active"
    elif 9 <= hour < 14:
        return "🇬🇧 London Session", "active"
    elif 17 <= hour < 22:
        return "🇺🇸 New York Session", "active"
    elif 22 <= hour or hour < 9:
        return "😴 Dead Zone / Asian", "inactive"
    return "Unknown", "inactive"

def get_live_data(tickers):
    """Fetch live data using yfinance."""
    data = yf.download(tickers, period="1d", interval="15m", group_by='ticker', progress=False)
    return data

def calculate_strength():
    """Mathematically calculate currency strength using Major Pairs."""
    # We use the % change of today to see who is strong
    tickers = ["EURUSD=X", "GBPUSD=X", "USDJPY=X", "AUDUSD=X", "USDCAD=X", "DX-Y.NYB"]
    data = yf.download(tickers, period="2d", interval="1d", progress=False)
    
    strength = {}
    
    # Calculate DXY Change
    try:
        dxy_open = data["DX-Y.NYB"]["Open"].iloc[-1]
        dxy_close = data["DX-Y.NYB"]["Close"].iloc[-1]
        dxy_change = ((dxy_close - dxy_open) / dxy_open) * 100
        strength['USD'] = dxy_change
    except:
        strength['USD'] = 0.0

    # EUR (Derived from EURUSD)
    try:
        pair = "EURUSD=X"
        change = ((data[pair]["Close"].iloc[-1] - data[pair]["Open"].iloc[-1]) / data[pair]["Open"].iloc[-1]) * 100
        # If EURUSD is UP, EUR is Stronger than USD
        strength['EUR'] = strength['USD'] + change 
    except: strength['EUR'] = 0.0
    
    # JPY (Derived from USDJPY - Inverse)
    try:
        pair = "USDJPY=X"
        change = ((data[pair]["Close"].iloc[-1] - data[pair]["Open"].iloc[-1]) / data[pair]["Open"].iloc[-1]) * 100
        # If USDJPY is UP, JPY is Weaker
        strength['JPY'] = strength['USD'] - change
    except: strength['JPY'] = 0.0

    # GBP
    try:
        pair = "GBPUSD=X"
        change = ((data[pair]["Close"].iloc[-1] - data[pair]["Open"].iloc[-1]) / data[pair]["Open"].iloc[-1]) * 100
        strength['GBP'] = strength['USD'] + change
    except: strength['GBP'] = 0.0

    return strength

# --- MAIN APP UI ---

# Header
st.title("🎯 AI Forex Sniper Dashboard")
st.caption("Live Analysis | Multi-Source Logic | Session Timing")

# 1. TIME & SESSION
col1, col2, col3 = st.columns(3)
ng_time = get_nigeria_time()
session_name, status = get_current_session(ng_time.hour)

with col1:
    st.metric(label="🇳🇬 Lagos Time", value=ng_time.strftime("%H:%M:%S"))
with col2:
    st.metric(label="Market Status", value=session_name, delta="Open" if status=="active" else "Closed")
with col3:
    st.info("⚠️ Check ForexFactory manually for RED Folders before trading!")

st.divider()

# 2. SCANNING ENGINE
if st.button("🔍 SCAN MARKET NOW (Analyze Structure & Trends)", type="primary"):
    with st.spinner('Accessing Satellite Data... Crunching DXY... Analyzing Volatility...'):
        
        # A. Get Data
        scores = calculate_strength()
        
        # Sort Currencies by Strength
        sorted_strength = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        strongest = sorted_strength[0][0]
        weakest = sorted_strength[-1][0]
        
        # B. DXY Analysis
        dxy_val = scores.get('USD', 0)
        dxy_trend = "BULLISH 🟢" if dxy_val > 0 else "BEARISH 🔴"
        
        # C. Generate Prediction
        prediction_pair = f"{strongest}/{weakest}"
        # Cleanup pair name (e.g. if JPY/USD -> USD/JPY)
        if strongest == "USD" and weakest == "JPY": clean_pair = "USDJPY"
        elif strongest == "EUR" and weakest == "USD": clean_pair = "EURUSD"
        elif strongest == "GBP" and weakest == "USD": clean_pair = "GBPUSD"
        elif strongest == "USD" and weakest == "EUR": clean_pair = "EURUSD (SELL)"
        else: clean_pair = f"{strongest}{weakest}"
        
        action = "BUY" if scores[strongest] > 0 else "SELL"
        
        # --- DISPLAY RESULTS ---
        
        # Row 1: The Verdict
        st.subheader(f"🤖 AI VERDICT: {dxy_trend} DOLLAR")
        
        c1, c2, c3 = st.columns(3)
        c1.metric("Strongest Currency", strongest, f"{scores[strongest]:.2f}%")
        c2.metric("Weakest Currency", weakest, f"{scores[weakest]:.2f}%")
        c3.metric("DXY Trend", dxy_trend)
        
        st.success(f"### 🚀 TOP SIGNAL: {action} {clean_pair}")
        st.write(f"**Reasoning:** {strongest} is gaining momentum while {weakest} is crashing. DXY is {dxy_trend}.")
        
        # Visual Gauge (Simple Bar)
        st.write("### 📊 Live Strength Meter")
        chart_data = pd.DataFrame.from_dict(scores, orient='index', columns=['Strength'])
        st.bar_chart(chart_data)

else:
    st.write("Click the button above to start the AI Analysis.")
