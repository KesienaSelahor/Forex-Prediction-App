import streamlit as st
import yfinance as yf
import pandas as pd
import datetime
import pytz

# --- CONFIGURATION (Force Light Theme Logic) ---
st.set_page_config(
    page_title="Forex AI Sniper", 
    layout="wide", 
    page_icon="🎯",
    initial_sidebar_state="collapsed"
)

# --- CUSTOM CSS (BabyPips Style: White BG, Specific Colors) ---
st.markdown("""
    <style>
    /* Force White Background */
    [data-testid="stAppViewContainer"] {
        background-color: #ffffff;
        color: #000000;
    }
    [data-testid="stHeader"] {
        background-color: #ffffff;
    }
    
    /* BabyPips Style Cards */
    .session-card {
        padding: 20px;
        border-radius: 10px;
        text-align: center;
        font-weight: bold;
        color: white;
        margin-bottom: 10px;
    }
    .london { background-color: #5da423; } /* BabyPips Green */
    .newyork { background-color: #c60c30; } /* BabyPips Red */
    .tokyo { background-color: #3d85c6; }   /* BabyPips Blue */
    .overlap { background-color: #e3b128; color: black; } /* Gold */
    .closed { background-color: #999999; }
    
    .metric-box {
        background-color: #f7f7f7;
        border: 1px solid #e0e0e0;
        border-radius: 8px;
        padding: 15px;
        text-align: center;
    }
    h1, h2, h3 { color: #333333; }
    </style>
    """, unsafe_allow_html=True)

# --- FUNCTIONS ---

def get_nigeria_time():
    lagos = pytz.timezone('Africa/Lagos')
    return datetime.datetime.now(lagos)

def get_current_session_style(hour):
    # Returns: (Title, Status, CSS_Class)
    if 14 <= hour < 17: 
        return "🔥 KILL ZONE (London/NY Overlap)", "ACTIVE", "overlap"
    elif 9 <= hour < 14: 
        return "🇬🇧 London Session", "OPEN", "london"
    elif 17 <= hour < 22: 
        return "🇺🇸 New York Session", "OPEN", "newyork"
    elif 22 <= hour or hour < 9: 
        return "😴 Market Closed / Asian", "QUIET", "closed"
    return "Unknown", "Inactive", "closed"

def calculate_strength():
    # Fetch data
    tickers = ["EURUSD=X", "GBPUSD=X", "USDJPY=X", "AUDUSD=X", "USDCAD=X", "DX-Y.NYB"]
    data = yf.download(tickers, period="2d", interval="1d", progress=False)
    
    strength = {}
    
    # Helper for % change
    def get_change(pair):
        try:
            close = data[pair]["Close"].iloc[-1]
            open_ = data[pair]["Open"].iloc[-1]
            return ((close - open_) / open_) * 100
        except: return 0.0

    # 1. USD Strength (DXY)
    try:
        dxy_open = data["DX-Y.NYB"]["Open"].iloc[-1]
        dxy_close = data["DX-Y.NYB"]["Close"].iloc[-1]
        strength['USD'] = ((dxy_close - dxy_open) / dxy_open) * 100
    except: strength['USD'] = 0.0

    # 2. Derive others
    strength['EUR'] = strength['USD'] + get_change("EURUSD=X")
    strength['GBP'] = strength['USD'] + get_change("GBPUSD=X")
    strength['AUD'] = strength['USD'] + get_change("AUDUSD=X")
    strength['JPY'] = strength['USD'] - get_change("USDJPY=X")
    strength['CAD'] = strength['USD'] - get_change("USDCAD=X")

    return strength

def get_smart_signal(strong, weak):
    # Translator Logic
    if "USD" in strong and "EUR" in weak: return "SELL EURUSD"
    if "EUR" in strong and "USD" in weak: return "BUY EURUSD"
    
    if "USD" in strong and "GBP" in weak: return "SELL GBPUSD"
    if "GBP" in strong and "USD" in weak: return "BUY GBPUSD"
    
    if "USD" in strong and "JPY" in weak: return "BUY USDJPY"
    if "JPY" in strong and "USD" in weak: return "SELL USDJPY"
    
    # Generic fallback
    return f"BUY {strong}{weak}"

# --- APP LAYOUT ---

st.title("🎯 AI Forex Sniper Dashboard")
st.markdown("**Live Analysis | Multi-Source Logic**")

# Time & Session Display
ng_time = get_nigeria_time()
s_name, s_status, s_class = get_current_session_style(ng_time.hour)

c1, c2 = st.columns(2)

with c1:
    st.markdown(f"""
    <div class="metric-box">
        <h3>🇳🇬 Lagos Time</h3>
        <h2>{ng_time.strftime("%H:%M:%S")}</h2>
    </div>
    """, unsafe_allow_html=True)

with c2:
    st.markdown(f"""
    <div class="session-card {s_class}">
        <h3>{s_name}</h3>
        <h2>{s_status}</h2>
    </div>
    """, unsafe_allow_html=True)

st.divider()

# Scan Button
if st.button("🔍 SCAN MARKET NOW", type="primary", use_container_width=True):
    with st.spinner('Accessing Market Data...'):
        
        scores = calculate_strength()
        
        # Sort
        sorted_strength = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        strongest = sorted_strength[0][0]
        weakest = sorted_strength[-1][0]
        
        signal_text = get_smart_signal(strongest, weakest)
        
        st.success(f"### 🚀 TOP SIGNAL: {signal_text}")
        
        # Metrics
        m1, m2 = st.columns(2)
        m1.metric("Strongest Currency", strongest, f"{scores[strongest]:.2f}%")
        m2.metric("Weakest Currency", weakest, f"{scores[weakest]:.2f}%")
        
        # Chart
        st.write("### 📊 Currency Strength Meter")
        df = pd.DataFrame.from_dict(scores, orient='index', columns=['% Strength'])
        st.bar_chart(df)

else:
    st.info("Click the button above to calculate Live Strength.")
